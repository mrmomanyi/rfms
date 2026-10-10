"""
Scorecard logic: turns trees into carbon, oxygen, rankings and summaries.

This file has no Django imports. It works on any objects that have the same
attributes as the Tree model, so it can be tested without a database.
The output is plain dictionaries and numbers, which are safe to cache.
"""
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date

from . import calculations as calc

PLANTED_CATEGORIES = ('afforestation', 'reafforestation')
FORECAST_YEARS = 5
DAYS_PER_YEAR = 365.25
DAYS_PER_MONTH = 30.44

CATEGORY_LABELS = {
    'afforestation': 'Afforestation',
    'reafforestation': 'Reafforestation',
    'existing': 'Existing forest',
}


# ---------------------------------------------------------------------------
# One tree
# ---------------------------------------------------------------------------
def _as_date(value):
    """datetime -> date. date -> date. None -> None."""
    if value is None:
        return None
    return value.date() if hasattr(value, 'date') else value


def tree_age_years(tree, today):
    """Return (age in years or None, where the age came from)."""
    planted = getattr(tree, 'planting_date', None)
    if planted:
        return max((today - planted).days / DAYS_PER_YEAR, 0.0), 'planting date'
    if tree.forest_category in PLANTED_CATEGORIES:
        registered = _as_date(tree.registration_date)
        if registered:
            return max((today - registered).days / DAYS_PER_YEAR, 0.0), 'registration date'
    return None, 'unknown'


def evaluate_tree(tree, today=None, forecast_years=FORECAST_YEARS):
    """Work out carbon, oxygen and a forecast for one tree, as a plain dict."""
    today = today or date.today()
    species = tree.species
    wood_density = getattr(species, 'wood_density', None)
    params = species.growth_params() if hasattr(species, 'growth_params') else calc.GrowthParams()

    measurements = sorted(
        tree.measurements.all(),
        key=lambda m: (m.measured_on, getattr(m, 'pk', None) or 0),
        reverse=True,
    )
    latest = measurements[0] if measurements else None
    age, age_basis = tree_age_years(tree, today)
    verified = getattr(tree, 'verification_status', '') == 'verified'
    counts_as_removal = tree.forest_category in PLANTED_CATEGORIES

    row = {
        'tree_id': tree.tree_id,
        'species': species.name,
        'county': getattr(getattr(tree, 'county', None), 'name', ''),
        'subcounty': getattr(getattr(tree, 'subcounty', None), 'name', ''),
        'plot_name': tree.plot_name,
        'contributor': tree.contributor_name,
        'contributor_type': tree.contributor_type,
        'category': tree.forest_category,
        'category_label': CATEGORY_LABELS.get(tree.forest_category, tree.forest_category),
        'verification': getattr(tree, 'verification_status', 'pending'),
        'verified': verified,
        'counts_as_removal': counts_as_removal,
        'age_years': round(age, 1) if age is not None else None,
        'age_basis': age_basis,
        'uses_default_density': wood_density is None,
        'needs_measurement': False,
        'method': None,
        'dbh_cm': None,
        'height_m': None,
        'co2e_kg': None,
        'oxygen_kg': None,
        'annual_co2e_kg': None,
        'confidence': None,
        'forecast': [],
        'last_measured': latest.measured_on if latest else None,
    }

    if latest is None and age is None:
        # An existing tree with no known age and no measurement cannot be estimated honestly.
        row['needs_measurement'] = True
        return row

    if latest is not None:
        months = max((today - latest.measured_on).days / DAYS_PER_MONTH, 0.0)
        carbon = calc.tree_carbon(
            age or 0.0, dbh_cm=latest.dbh_cm, height_m=latest.height_m,
            wood_density=wood_density, params=params,
            months_since_measured=months, verified=verified)
        effective_age = age if age is not None else calc.age_from_dbh(latest.dbh_cm, params)
    else:
        carbon = calc.tree_carbon(
            age, wood_density=wood_density, params=params, verified=verified)
        effective_age = age

    forecast = calc.forecast_co2e(
        effective_age, years=forecast_years, current=carbon,
        wood_density=wood_density, params=params)

    row.update({
        'method': carbon.method,
        'dbh_cm': carbon.dbh_cm,
        'height_m': carbon.height_m,
        'co2e_kg': carbon.co2e_kg,
        'oxygen_kg': carbon.oxygen_kg,
        'annual_co2e_kg': round(forecast[1] - forecast[0], 1) if len(forecast) > 1 else 0.0,
        'confidence': carbon.confidence,
        'forecast': forecast,
    })
    return row


# ---------------------------------------------------------------------------
# Many trees
# ---------------------------------------------------------------------------
@dataclass
class Scorecard:
    summary: dict = field(default_factory=dict)
    rows: list = field(default_factory=list)
    by_species: list = field(default_factory=list)
    by_county: list = field(default_factory=list)
    contributors: list = field(default_factory=list)
    forecast_labels: list = field(default_factory=list)
    forecast_removal_kg: list = field(default_factory=list)
    rank_verified_only: bool = False


def _safe_div(a, b):
    return a / b if b else 0.0


def build_scorecard(trees, today=None, rank_verified_only=False, forecast_years=FORECAST_YEARS):
    """Evaluate every tree and roll the results up into totals and rankings."""
    today = today or date.today()
    rows = [evaluate_tree(t, today, forecast_years) for t in trees]
    counted = [r for r in rows if r['co2e_kg'] is not None]
    removal = [r for r in counted if r['counts_as_removal']]
    existing = [r for r in counted if not r['counts_as_removal']]
    measured = [r for r in counted if r['method'] == 'measured']
    verified = [r for r in counted if r['verified']]

    forecast_total = [0.0] * (forecast_years + 1)
    for r in removal:
        for i, value in enumerate(r['forecast']):
            forecast_total[i] += value

    summary = {
        'trees_total': len(rows),
        'trees_counted': len(counted),
        'needs_measurement': len(rows) - len(counted),
        'measured_trees': len(measured),
        'measured_share': round(100 * _safe_div(len(measured), len(counted))),
        'verified_trees': len(verified),
        'verified_share': round(100 * _safe_div(len(verified), len(counted))),
        'stock_co2e_kg': round(sum(r['co2e_kg'] for r in counted), 1),
        'removal_co2e_kg': round(sum(r['co2e_kg'] for r in removal), 1),
        'existing_co2e_kg': round(sum(r['co2e_kg'] for r in existing), 1),
        'oxygen_kg': round(sum(r['oxygen_kg'] for r in counted), 1),
        'oxygen_removal_kg': round(sum(r['oxygen_kg'] for r in removal), 1),
        'annual_removal_co2e_kg': round(sum(r['annual_co2e_kg'] for r in removal), 1),
        'avg_co2e_per_tree_kg': round(_safe_div(sum(r['co2e_kg'] for r in counted), len(counted)), 1),
        'avg_confidence': round(_safe_div(sum(r['confidence'] for r in counted), len(counted))),
        'default_density_trees': sum(1 for r in counted if r['uses_default_density']),
        'removal_trees': len(removal),
        'existing_trees': len(existing),
    }

    # --- species -----------------------------------------------------------
    species = defaultdict(lambda: {'trees': 0, 'co2e_kg': 0.0, 'oxygen_kg': 0.0})
    for r in counted:
        s = species[r['species']]
        s['trees'] += 1
        s['co2e_kg'] += r['co2e_kg']
        s['oxygen_kg'] += r['oxygen_kg']
    by_species = sorted(
        ({'name': name, 'trees': v['trees'], 'co2e_kg': round(v['co2e_kg'], 1),
          'oxygen_kg': round(v['oxygen_kg'], 1),
          'avg_co2e_kg': round(_safe_div(v['co2e_kg'], v['trees']), 1)}
         for name, v in species.items()),
        key=lambda s: -s['co2e_kg'])

    # --- counties ----------------------------------------------------------
    counties = defaultdict(lambda: {'trees': 0, 'co2e_kg': 0.0, 'removal_co2e_kg': 0.0})
    for r in counted:
        c = counties[r['county'] or 'Unknown']
        c['trees'] += 1
        c['co2e_kg'] += r['co2e_kg']
        if r['counts_as_removal']:
            c['removal_co2e_kg'] += r['co2e_kg']
    by_county = sorted(
        ({'name': name, 'trees': v['trees'], 'co2e_kg': round(v['co2e_kg'], 1),
          'removal_co2e_kg': round(v['removal_co2e_kg'], 1)}
         for name, v in counties.items()),
        key=lambda c: (-c['removal_co2e_kg'], -c['trees']))

    # --- contributors ------------------------------------------------------
    ranked_source = [r for r in counted if r['verified']] if rank_verified_only else counted
    people = {}
    for r in ranked_source:
        name = (r['contributor'] or 'Unknown contributor').strip()
        key = (name.lower(), r['contributor_type'])
        p = people.setdefault(key, {
            'name': name, 'type': r['contributor_type'], 'trees': 0, 'planted_trees': 0,
            'verified_trees': 0, 'co2e_kg': 0.0, 'removal_co2e_kg': 0.0, 'oxygen_kg': 0.0,
            'counties': set(),
        })
        p['trees'] += 1
        p['planted_trees'] += 1 if r['counts_as_removal'] else 0
        p['verified_trees'] += 1 if r['verified'] else 0
        p['co2e_kg'] += r['co2e_kg']
        p['oxygen_kg'] += r['oxygen_kg']
        if r['counts_as_removal']:
            p['removal_co2e_kg'] += r['co2e_kg']
        if r['county']:
            p['counties'].add(r['county'])

    contributors = sorted(
        ({'name': p['name'], 'type': p['type'], 'trees': p['trees'],
          'planted_trees': p['planted_trees'], 'verified_trees': p['verified_trees'],
          'co2e_kg': round(p['co2e_kg'], 1),
          'removal_co2e_kg': round(p['removal_co2e_kg'], 1),
          'oxygen_kg': round(p['oxygen_kg'], 1),
          'county_count': len(p['counties'])}
         for p in people.values()),
        key=lambda p: (-p['removal_co2e_kg'], -p['trees'], p['name'].lower()))
    for position, person in enumerate(contributors, start=1):
        person['rank'] = position

    return Scorecard(
        summary=summary,
        rows=sorted(rows, key=lambda r: (r['co2e_kg'] is None, -(r['co2e_kg'] or 0))),
        by_species=by_species,
        by_county=by_county,
        contributors=contributors,
        forecast_labels=['Now'] + [f'Year {i}' for i in range(1, forecast_years + 1)],
        forecast_removal_kg=[round(v, 1) for v in forecast_total],
        rank_verified_only=rank_verified_only,
    )
