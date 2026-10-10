from django.core.management.base import BaseCommand
from django.db import transaction

from momanyi.data.kenya_locations import KENYA_LOCATIONS
from momanyi.models import County, SubCounty


class Command(BaseCommand):
    help = "Load Kenya's counties and sub-counties. Safe to run more than once."

    @transaction.atomic
    def handle(self, *args, **options):
        counties_added = 0
        subs_added = 0

        for county_name, sub_names in KENYA_LOCATIONS.items():
            county = County.objects.filter(name__iexact=county_name).first()
            if county is None:
                county = County.objects.create(name=county_name)
                counties_added += 1

            for sub_name in sub_names:
                if not SubCounty.objects.filter(county=county, name__iexact=sub_name).exists():
                    SubCounty.objects.create(county=county, name=sub_name)
                    subs_added += 1

        self.stdout.write(self.style.SUCCESS(
            f'Added {counties_added} counties and {subs_added} sub-counties. '
            f'Totals now: {County.objects.count()} counties, {SubCounty.objects.count()} sub-counties.'))
