"""Views for the Forest Resource Monitoring System."""
import csv
import json
import logging
import math
from datetime import datetime, timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.db.models import Count, Q
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from . import calculations, services
from .forms import MeasurementForm, SignUpForm
from .models import County, Measurement, SubCounty, Tree, TreeEvent, TreeSpecies
from .selectors import get_scorecard
from .spatial import find_trees_within, in_kenya

logger = logging.getLogger(__name__)

PAGE_SIZE = 25


# ---------------------------------------------------------------------------
# Small helpers
# ---------------------------------------------------------------------------
def _to_int(value):
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _to_float(value):
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _to_date(value):
    try:
        return datetime.strptime(value, '%Y-%m-%d').date()
    except (TypeError, ValueError):
        return None


def _csv_safe(value):
    """Stop spreadsheet programs from running a cell that starts like a formula."""
    text = '' if value is None else str(value)
    return "'" + text if text[:1] in ('=', '+', '-', '@') else text


def page_not_found(request, exception=None):
    return render(request, '404.html', status=404)


# ---------------------------------------------------------------------------
# Public pages
# ---------------------------------------------------------------------------
def index(request):
    card = get_scorecard()
    return render(request, 'momanyi/index.html', {
        'summary': card.summary,
        'county_count': Tree.objects.order_by().values('county').distinct().count(),
        'contributor_count': len(card.contributors),
        'top_contributors': card.contributors[:3],
    })


def about(request):
    return render(request, 'momanyi/about.html')


def methodology(request):
    return render(request, 'momanyi/methodology.html', {
        'carbon_fraction': calculations.CARBON_FRACTION,
        'co2_per_carbon': calculations.CO2_PER_CARBON,
        'o2_per_co2': calculations.O2_PER_CO2,
        'default_density': calculations.DEFAULT_WOOD_DENSITY,
        'root_shoot': calculations.DEFAULT_ROOT_SHOOT,
        'defaults': calculations.GrowthParams(),
        'species_total': TreeSpecies.objects.count(),
        'species_missing_density': TreeSpecies.objects.filter(wood_density__isnull=True).count(),
        'rank_verified_only': settings.RFMS_RANK_VERIFIED_ONLY,
    })


# ---------------------------------------------------------------------------
# Registration
# ---------------------------------------------------------------------------
def _register_tree_from_post(request):
    """Validate the form and save the tree. Returns the Tree, or None after adding messages."""
    data = request.POST

    species = TreeSpecies.objects.filter(pk=_to_int(data.get('species'))).first()
    county = County.objects.filter(pk=_to_int(data.get('county'))).first()
    subcounty = (
        SubCounty.objects.filter(pk=_to_int(data.get('subcounty')), county=county).first()
        if county else None
    )
    lat = _to_float(data.get('latitude'))
    lng = _to_float(data.get('longitude'))
    planting_raw = (data.get('planting_date') or '').strip()
    planting_date = _to_date(planting_raw) if planting_raw else None
    dbh_raw = (data.get('initial_dbh') or '').strip()
    height_raw = (data.get('initial_height') or '').strip()
    dbh = _to_float(dbh_raw) if dbh_raw else None
    height = _to_float(height_raw) if height_raw else None

    problems = []
    if not species:
        problems.append('Please select a valid tree species.')
    if not county:
        problems.append('Please select a valid county.')
    elif not subcounty:
        problems.append('Please select a sub-county that belongs to the chosen county.')
    if lat is None or lng is None:
        problems.append('Please set valid coordinates for the tree.')
    if planting_raw and planting_date is None:
        problems.append('The planting date is not a valid date.')
    if dbh_raw and dbh is None:
        problems.append('The trunk diameter must be a number.')
    if height_raw and height is None:
        problems.append('The height must be a number.')
    if height is not None and dbh is None:
        problems.append('Enter the trunk diameter as well as the height.')

    plot_name = (data.get('plot_name') or '').strip()
    contributor_name = (data.get('contributor_name') or '').strip()
    if not plot_name:
        problems.append('Please enter the field or plot name.')
    if not contributor_name:
        problems.append('Please enter the contributor name.')
    if data.get('forest_category') not in dict(Tree.FOREST_CATEGORY_CHOICES):
        problems.append('Please select a forest category.')
    if data.get('tree_status') not in dict(Tree.TREE_STATUS_CHOICES):
        problems.append('Please select the tree status.')
    if data.get('contributor_type') not in dict(Tree.CONTRIBUTOR_TYPE_CHOICES):
        problems.append('Please select the contributor type.')

    if problems:
        for text in problems:
            messages.error(request, text)
        return None

    tree = Tree(
        species=species, county=county, subcounty=subcounty,
        latitude=f'{lat:.6f}', longitude=f'{lng:.6f}',
        plot_name=plot_name,
        forest_category=data['forest_category'],
        tree_status=data['tree_status'],
        contributor_type=data['contributor_type'],
        contributor_name=contributor_name,
        planting_date=planting_date,
        registered_by=request.user,
    )
    measurement = None
    if dbh is not None:
        measurement = Measurement(
            tree=tree, measured_on=timezone.localdate(), dbh_cm=dbh,
            height_m=height, measured_by=request.user)

    try:
        tree.full_clean()
        if measurement:
            measurement.full_clean(exclude=['tree'])
    except ValidationError as exc:
        for text in exc.messages:
            messages.error(request, text)
        return None

    with transaction.atomic():
        tree.save()
        TreeEvent.objects.create(
            tree=tree, event_type='registered', user=request.user, note='Registered through the website')
        if measurement:
            measurement.tree = tree
            measurement.save()
            TreeEvent.objects.create(
                tree=tree, event_type='measured', user=request.user, note=f'DBH {dbh:g} cm at registration')
    return tree


@login_required
def tree_registration(request):
    if request.method == 'POST':
        tree = _register_tree_from_post(request)
        if tree:
            messages.success(
                request,
                f'Tree {tree.tree_id} registered successfully for {tree.contributor_name}.')
            return redirect('tree_detail', tree_id=tree.tree_id)

    posted = request.POST if request.method == 'POST' else {}
    return render(request, 'momanyi/tree_registration.html', {
        'species': TreeSpecies.objects.all(),
        'counties': County.objects.all(),
        'posted': posted,
        'today': timezone.localdate(),
        'default_contributor': request.user.get_full_name() or request.user.username,
    })


@require_POST
def check_coordinate_availability(request):
    """AJAX: is this spot free? Used by the Validate button on the registration page."""
    if not request.user.is_authenticated:
        return JsonResponse({'available': False, 'status': 'error',
                             'message': 'Please log in again.'}, status=401)
    try:
        payload = json.loads(request.body or b'{}')
    except ValueError:
        return JsonResponse({'available': False, 'status': 'error',
                             'message': 'Invalid request.'}, status=400)

    lat = _to_float(payload.get('latitude'))
    lng = _to_float(payload.get('longitude'))
    if lat is None or lng is None:
        return JsonResponse({'available': False, 'status': 'error',
                             'message': 'Coordinates are required and must be numbers.'})
    if not in_kenya(lat, lng):
        return JsonResponse({'available': False, 'status': 'warning',
                             'message': 'These coordinates are outside Kenya.'})

    nearby = find_trees_within(lat, lng, settings.RFMS_NEARBY_WARNING_M)
    if nearby:
        tree, distance = nearby[0]
        if distance <= settings.RFMS_DUPLICATE_RADIUS_M:
            return JsonResponse({
                'available': False, 'status': 'error', 'tree_id': tree.tree_id,
                'distance': round(distance, 2),
                'message': f'Tree {tree.tree_id} already exists at this location.'})
        return JsonResponse({
            'available': True, 'status': 'warning', 'nearest_distance': round(distance, 1),
            'message': f'Location available. The nearest tree is {distance:.1f} m away.'})

    return JsonResponse({'available': True, 'status': 'success',
                         'message': 'Location available for registration.'})


@require_GET
def get_subcounties(request):
    county_id = _to_int(request.GET.get('county_id'))
    if county_id is None:
        return JsonResponse({'subcounties': []})
    subs = SubCounty.objects.filter(county_id=county_id).order_by('name')
    return JsonResponse({'subcounties': [{'id': s.id, 'name': s.name} for s in subs]})


# ---------------------------------------------------------------------------
# Tree detail and measurements
# ---------------------------------------------------------------------------
def _can_edit(user, tree):
    return user.is_authenticated and (user.is_staff or tree.registered_by_id == user.id)


def tree_detail(request, tree_id):
    tree = get_object_or_404(
        Tree.objects.select_related('species', 'county', 'subcounty', 'registered_by')
        .prefetch_related('measurements', 'events'),
        tree_id=tree_id)
    can_edit = _can_edit(request.user, tree)
    return render(request, 'momanyi/tree_detail.html', {
        'tree': tree,
        'result': services.evaluate_tree(tree, today=timezone.localdate()),
        'measurements': tree.measurements.all(),
        'events': tree.events.select_related('user')[:15],
        'can_edit': can_edit,
        'form': MeasurementForm(initial={'measured_on': timezone.localdate()}) if can_edit else None,
    })


@login_required
@require_POST
def add_measurement(request, tree_id):
    tree = get_object_or_404(Tree, tree_id=tree_id)
    if not _can_edit(request.user, tree):
        messages.error(request, 'Only the person who registered this tree, or staff, can add measurements.')
        return redirect('tree_detail', tree_id=tree.tree_id)

    form = MeasurementForm(request.POST)
    if form.is_valid():
        measurement = form.save(commit=False)
        measurement.tree = tree
        measurement.measured_by = request.user
        measurement.save()
        TreeEvent.objects.create(
            tree=tree, event_type='measured', user=request.user,
            note=f'DBH {measurement.dbh_cm:g} cm')
        messages.success(request, 'Measurement saved. The carbon estimate now uses it.')
    else:
        for errors in form.errors.values():
            for text in errors:
                messages.error(request, text)
    return redirect('tree_detail', tree_id=tree.tree_id)


# ---------------------------------------------------------------------------
# Dashboards
# ---------------------------------------------------------------------------
def dashboard(request):
    total = Tree.objects.count()
    alive = Tree.objects.filter(tree_status='alive').count()
    dead = Tree.objects.filter(tree_status='dead').count()
    week_ago = timezone.now() - timedelta(days=7)

    county_stats = (
        Tree.objects.values('county__name')
        .annotate(total=Count('id'),
                  alive=Count('id', filter=Q(tree_status='alive')),
                  dead=Count('id', filter=Q(tree_status='dead')))
        .order_by('-total')[:15]
    )
    species_stats = (
        Tree.objects.values('species__name').annotate(total=Count('id')).order_by('-total')[:10]
    )
    review = dict(
        Tree.objects.values_list('verification_status').annotate(n=Count('id')).order_by())

    return render(request, 'momanyi/dashboard.html', {
        'total_trees': total,
        'alive_trees': alive,
        'dead_trees': dead,
        'recent_trees': Tree.objects.filter(registration_date__gte=week_ago).count(),
        'survival_rate': round(100 * alive / total) if total else 0,
        'verified_count': review.get('verified', 0),
        'pending_count': review.get('pending', 0),
        'county_stats': county_stats,
        'species_stats': species_stats,
        'latest_trees': Tree.objects.select_related('species', 'county', 'subcounty')[:10],
    })


def _filter_rows(rows, params):
    """Apply the search box and drop-downs on the tree tables."""
    q = (params.get('q') or '').strip().lower()
    species = params.get('species') or ''
    method = params.get('method') or ''
    verification = params.get('verification') or ''
    out = []
    for r in rows:
        if q and q not in f"{r['tree_id']} {r['species']} {r['contributor']} {r['county']}".lower():
            continue
        if species and r['species'] != species:
            continue
        if method == 'needs' and not r['needs_measurement']:
            continue
        if method in ('measured', 'modelled') and r['method'] != method:
            continue
        if verification and r['verification'] != verification:
            continue
        out.append(r)
    return out


def _table_context(request, rows, card):
    filtered = _filter_rows(rows, request.GET)
    page = Paginator(filtered, PAGE_SIZE).get_page(request.GET.get('page'))
    query = request.GET.copy()
    query.pop('page', None)
    return {
        'page_obj': page,
        'filtered_count': len(filtered),
        'species_options': [s['name'] for s in card.by_species],
        'filters': {
            'q': request.GET.get('q', ''), 'species': request.GET.get('species', ''),
            'method': request.GET.get('method', ''), 'verification': request.GET.get('verification', ''),
        },
        'query_string': query.urlencode(),
    }


def carbon_score_view(request):
    card = get_scorecard()
    top_species = card.by_species[:8]
    chart_data = {
        'species': {
            'labels': [s['name'] for s in top_species],
            'values': [round(s['co2e_kg'] / 1000, 2) for s in top_species],
        },
        'forecast': {
            'labels': card.forecast_labels,
            'values': [round(v / 1000, 2) for v in card.forecast_removal_kg],
        },
        'split': {
            'labels': ['Planted (counts as removal)', 'Existing forest (stock only)'],
            'values': [round(card.summary['removal_co2e_kg'] / 1000, 2),
                       round(card.summary['existing_co2e_kg'] / 1000, 2)],
        },
    }
    context = {
        'summary': card.summary,
        'chart_data': chart_data,
        'by_species': card.by_species[:8],
        'top_contributors': card.contributors[:10],
        'forecast_labels': card.forecast_labels,
        'forecast_values': card.forecast_removal_kg,
        'rank_verified_only': card.rank_verified_only,
        'today': timezone.localdate(),
    }
    context.update(_table_context(request, card.rows, card))
    return render(request, 'momanyi/carbon_score.html', context)


def oxygen_index_view(request):
    card = get_scorecard()
    rows = sorted(card.rows, key=lambda r: -(r['oxygen_kg'] or 0))
    top_species = sorted(card.by_species, key=lambda s: -s['oxygen_kg'])[:8]
    top_people = sorted(card.contributors, key=lambda p: -p['oxygen_kg'])[:10]
    chart_data = {
        'oxygen_species': {
            'labels': [s['name'] for s in top_species],
            'values': [round(s['oxygen_kg'] / 1000, 2) for s in top_species],
        },
    }
    context = {
        'summary': card.summary,
        'chart_data': chart_data,
        'by_species': top_species,
        'top_contributors': top_people,
        'today': timezone.localdate(),
    }
    context.update(_table_context(request, rows, card))
    return render(request, 'momanyi/oxygen_index.html', context)


def rankings(request):
    card = get_scorecard()
    kind = request.GET.get('type', 'all')
    people = card.contributors
    if kind in ('individual', 'institution', 'organization'):
        people = [p for p in people if p['type'] == kind]
    # re-number after filtering so the table starts at 1
    people = [dict(p, rank=i) for i, p in enumerate(people, start=1)]

    counties = card.by_county
    return render(request, 'momanyi/rankings.html', {
        'kind': kind,
        'people': people[:50],
        'max_removal': max([p['removal_co2e_kg'] for p in people], default=0),
        'counties': counties[:15],
        'max_county': max([c['removal_co2e_kg'] for c in counties], default=0),
        'rank_verified_only': card.rank_verified_only,
        'summary': card.summary,
    })


def forest_map(request):
    return render(request, 'momanyi/forest_map.html', {
        'summary': get_scorecard().summary,
    })


# ---------------------------------------------------------------------------
# Data endpoints
# ---------------------------------------------------------------------------
@require_GET
def tree_data_api(request):
    """GeoJSON of all trees for the map. Contributor names are deliberately left out."""
    trees = (
        Tree.objects.filter(is_active=True)
        .exclude(verification_status='rejected')
        .select_related('species', 'county')
    )
    features = [{
        'type': 'Feature',
        'geometry': {'type': 'Point', 'coordinates': [float(t.longitude), float(t.latitude)]},
        'properties': {
            'tree_id': t.tree_id,
            'species': t.species.name,
            'county': t.county.name,
            'status': t.tree_status,
            'verification': t.verification_status,
            'category': t.forest_category,
        },
    } for t in trees]
    return JsonResponse({'type': 'FeatureCollection', 'features': features})


@staff_member_required
def export_trees_csv(request):
    """Every tree with its calculated values, for staff only."""
    trees = (
        Tree.objects.select_related('species', 'county', 'subcounty', 'registered_by')
        .prefetch_related('measurements')
    )
    today = timezone.localdate()
    response = HttpResponse(content_type='text/csv')
    response['Content-Disposition'] = f'attachment; filename="rfms-trees-{today.isoformat()}.csv"'
    writer = csv.writer(response)
    writer.writerow([
        'tree_id', 'species', 'county', 'subcounty', 'plot', 'latitude', 'longitude',
        'category', 'status', 'verification', 'contributor_type', 'contributor',
        'planting_date', 'registered_on', 'method', 'dbh_cm', 'height_m',
        'co2e_kg', 'oxygen_kg', 'annual_co2e_kg', 'confidence'])
    for tree in trees:
        r = services.evaluate_tree(tree, today=today)
        writer.writerow([_csv_safe(v) for v in (
            tree.tree_id, tree.species.name, tree.county.name, tree.subcounty.name, tree.plot_name,
            tree.latitude, tree.longitude, tree.forest_category, tree.tree_status,
            tree.verification_status, tree.contributor_type, tree.contributor_name,
            tree.planting_date or '', timezone.localtime(tree.registration_date).date().isoformat(),
            r['method'] or '', r['dbh_cm'] if r['dbh_cm'] is not None else '',
            r['height_m'] if r['height_m'] is not None else '',
            r['co2e_kg'] if r['co2e_kg'] is not None else '',
            r['oxygen_kg'] if r['oxygen_kg'] is not None else '',
            r['annual_co2e_kg'] if r['annual_co2e_kg'] is not None else '',
            r['confidence'] if r['confidence'] is not None else '')])
    return response


# ---------------------------------------------------------------------------
# Accounts
# ---------------------------------------------------------------------------
def signup(request):
    if request.user.is_authenticated:
        return redirect('tree_registration')

    if request.method == 'POST':
        form = SignUpForm(request.POST)
        if form.is_valid():
            user = form.save()
            login(request, user)
            messages.success(request, f'Welcome, {user.first_name}! Your account has been created.')
            return redirect('tree_registration')
    else:
        form = SignUpForm()
    return render(request, 'registration/signup.html', {'form': form})
