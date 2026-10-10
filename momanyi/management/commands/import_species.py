import csv
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from momanyi.models import TreeSpecies

NUMBER_FIELDS = (
    'wood_density', 'growth_dbh_max_cm', 'growth_dbh_k',
    'growth_height_max_m', 'growth_height_k', 'growth_shape',
)
TEXT_FIELDS = ('scientific_name', 'density_source', 'growth_source')


class Command(BaseCommand):
    help = ('Create or update tree species from a CSV file. Blank cells leave the existing '
            'value untouched. Default file: momanyi/data/species_seed.csv')

    def add_arguments(self, parser):
        parser.add_argument('--file', help='Path to a CSV file')

    @transaction.atomic
    def handle(self, *args, **options):
        default = Path(__file__).resolve().parents[2] / 'data' / 'species_seed.csv'
        path = Path(options['file']) if options.get('file') else default
        if not path.exists():
            raise CommandError(f'File not found: {path}')

        created = updated = 0
        with path.open(newline='', encoding='utf-8-sig') as handle:
            for line_no, row in enumerate(csv.DictReader(handle), start=2):
                name = (row.get('name') or '').strip()
                if not name:
                    continue

                values = {}
                for field in TEXT_FIELDS:
                    if (row.get(field) or '').strip():
                        values[field] = row[field].strip()
                for field in NUMBER_FIELDS:
                    raw = (row.get(field) or '').strip()
                    if raw:
                        try:
                            values[field] = float(raw)
                        except ValueError:
                            raise CommandError(f'Line {line_no}: {field} must be a number, got {raw!r}')

                species, was_created = TreeSpecies.objects.update_or_create(name=name, defaults=values)
                created += was_created
                updated += not was_created

        self.stdout.write(self.style.SUCCESS(f'Species imported: {created} created, {updated} updated.'))
        missing = TreeSpecies.objects.filter(wood_density__isnull=True).count()
        if missing:
            self.stdout.write(self.style.WARNING(
                f'{missing} species have no wood density yet and use the default. '
                'Fill in wood_density and density_source in the CSV or admin.'))
