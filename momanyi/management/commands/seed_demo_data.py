import random
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from momanyi.models import County, Measurement, SubCounty, Tree, TreeSpecies

DEMO_PREFIX = 'DEMO - '

# (latitude, longitude, county name) base points; trees are laid out on a grid around each
SITES = [
    (-0.3031, 36.0800, 'Nakuru'),
    (-1.0332, 37.0693, 'Kiambu'),
    (-0.4167, 36.9500, 'Nyeri'),
    (-0.5167, 37.2833, 'Kirinyaga'),
    (-1.2921, 36.8219, 'Nairobi City'),
    (0.5143, 35.2698, 'Uasin Gishu'),
]
PEOPLE = [
    ('Amina Wanjiru', 'individual'), ('Green Hills School', 'institution'),
    ('Peter Otieno', 'individual'), ('Kijani Youth Group', 'organization'),
    ('Grace Chebet', 'individual'), ('Mwangaza Academy', 'institution'),
]


class Command(BaseCommand):
    help = ('Create sample trees so the dashboards have something to show. '
            'Every demo tree has a plot name starting with "DEMO - ". Use --purge to remove them.')

    def add_arguments(self, parser):
        parser.add_argument('--count', type=int, default=60, help='Number of trees (default 60)')
        parser.add_argument('--purge', action='store_true', help='Delete all demo trees and exit')

    @transaction.atomic
    def handle(self, *args, **options):
        if options['purge']:
            deleted, _ = Tree.objects.filter(plot_name__startswith=DEMO_PREFIX).delete()
            self.stdout.write(self.style.SUCCESS(f'Removed demo data ({deleted} records).'))
            return

        species = list(TreeSpecies.objects.all())
        if not species:
            raise CommandError('No species found. Run: python manage.py import_species')
        if not County.objects.exists():
            raise CommandError('No counties found. Run: python manage.py load_kenya_locations')

        rng = random.Random(42)
        today = timezone.localdate()
        created = 0

        for i in range(options['count']):
            lat0, lng0, county_name = SITES[i % len(SITES)]
            county = County.objects.filter(name=county_name).first()
            sub = SubCounty.objects.filter(county=county).first() if county else None
            if not county or not sub:
                continue

            # A 4 m grid keeps every tree well clear of its neighbours
            row, col = divmod(i // len(SITES), 8)
            lat = round(lat0 + row * 0.00004, 6)
            lng = round(lng0 + col * 0.00004, 6)

            name, kind = rng.choice(PEOPLE)
            category = rng.choices(['afforestation', 'reafforestation', 'existing'], [6, 3, 1])[0]
            age_days = rng.randint(120, 365 * 7)
            tree = Tree.objects.create(
                species=rng.choice(species),
                county=county, subcounty=sub,
                latitude=f'{lat:.6f}', longitude=f'{lng:.6f}',
                plot_name=f'{DEMO_PREFIX}Block {rng.choice("ABCDE")}',
                forest_category=category,
                tree_status='alive' if rng.random() > 0.12 else 'dead',
                planting_date=today - timedelta(days=age_days) if category != 'existing' else None,
                contributor_type=kind, contributor_name=name,
                verification_status=rng.choice(['verified', 'pending', 'pending']),
            )
            if category == 'existing' or rng.random() < 0.5:
                years = max(age_days / 365, 1)
                Measurement.objects.create(
                    tree=tree, measured_on=today - timedelta(days=rng.randint(10, 300)),
                    dbh_cm=round(min(4 + years * rng.uniform(2.0, 5.0) + (25 if category == 'existing' else 0), 90), 1),
                    height_m=round(min(2 + years * rng.uniform(0.8, 2.2) + (6 if category == 'existing' else 0), 40), 1),
                )
            created += 1

        self.stdout.write(self.style.SUCCESS(
            f'Created {created} demo trees. Remove them later with: python manage.py seed_demo_data --purge'))
