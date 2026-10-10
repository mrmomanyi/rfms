"""Model rules. Needs the Django test runner: python manage.py test"""
from datetime import timedelta

from django.core.cache import cache
from django.core.exceptions import ValidationError
from django.test import TestCase
from django.utils import timezone

from momanyi.models import County, Measurement, SubCounty, Tree, TreeSpecies


def make_tree(species, county, sub, lat='-0.303100', lng='36.080000', **extra):
    fields = dict(
        species=species, county=county, subcounty=sub, latitude=lat, longitude=lng,
        plot_name='Block A', forest_category='afforestation', tree_status='alive',
        contributor_type='individual', contributor_name='Amina Wanjiru')
    fields.update(extra)
    return Tree(**fields)


class TreeRuleTests(TestCase):

    def setUp(self):
        cache.clear()
        self.county = County.objects.create(name='Nakuru')
        self.other_county = County.objects.create(name='Kiambu')
        self.sub = SubCounty.objects.create(county=self.county, name='Njoro')
        self.other_sub = SubCounty.objects.create(county=self.other_county, name='Limuru')
        self.species = TreeSpecies.objects.create(name='Grevillea')

    def test_valid_tree_passes(self):
        tree = make_tree(self.species, self.county, self.sub)
        tree.full_clean()
        tree.save()
        self.assertTrue(tree.tree_id.startswith('TREE-'))

    def test_subcounty_must_belong_to_county(self):
        tree = make_tree(self.species, self.county, self.other_sub)
        with self.assertRaises(ValidationError) as ctx:
            tree.full_clean()
        self.assertIn('subcounty', ctx.exception.message_dict)

    def test_coordinates_must_be_in_kenya(self):
        tree = make_tree(self.species, self.county, self.sub, lat='51.500000', lng='-0.120000')
        with self.assertRaises(ValidationError):
            tree.full_clean()

    def test_trees_closer_than_one_metre_are_rejected(self):
        make_tree(self.species, self.county, self.sub).save()
        twin = make_tree(self.species, self.county, self.sub, lat='-0.303101')   # about 0.1 m away
        with self.assertRaises(ValidationError):
            twin.full_clean()

    def test_trees_further_apart_are_accepted(self):
        make_tree(self.species, self.county, self.sub).save()
        neighbour = make_tree(self.species, self.county, self.sub, lat='-0.303120')  # about 2 m away
        neighbour.full_clean()

    def test_a_tree_does_not_clash_with_itself_when_edited(self):
        tree = make_tree(self.species, self.county, self.sub)
        tree.save()
        tree.plot_name = 'Block B'
        tree.full_clean()

    def test_planting_date_cannot_be_in_the_future(self):
        tree = make_tree(self.species, self.county, self.sub,
                         planting_date=timezone.localdate() + timedelta(days=3))
        with self.assertRaises(ValidationError) as ctx:
            tree.full_clean()
        self.assertIn('planting_date', ctx.exception.message_dict)

    def test_planted_categories_count_as_removal(self):
        self.assertTrue(make_tree(self.species, self.county, self.sub).counts_as_removal)
        self.assertFalse(make_tree(self.species, self.county, self.sub,
                                   forest_category='existing').counts_as_removal)


class MeasurementTests(TestCase):

    def setUp(self):
        cache.clear()
        county = County.objects.create(name='Nakuru')
        sub = SubCounty.objects.create(county=county, name='Njoro')
        species = TreeSpecies.objects.create(name='Grevillea')
        self.tree = make_tree(species, county, sub)
        self.tree.save()

    def test_diameter_must_be_positive(self):
        m = Measurement(tree=self.tree, dbh_cm=0)
        with self.assertRaises(ValidationError):
            m.full_clean()

    def test_future_date_rejected(self):
        m = Measurement(tree=self.tree, dbh_cm=12, measured_on=timezone.localdate() + timedelta(days=1))
        with self.assertRaises(ValidationError):
            m.full_clean()

    def test_newest_measurement_comes_first(self):
        today = timezone.localdate()
        Measurement.objects.create(tree=self.tree, dbh_cm=10, measured_on=today - timedelta(days=100))
        Measurement.objects.create(tree=self.tree, dbh_cm=14, measured_on=today)
        self.assertEqual(self.tree.measurements.first().dbh_cm, 14)


class SpeciesTests(TestCase):

    def test_growth_params_fall_back_to_defaults(self):
        species = TreeSpecies.objects.create(name='Pine')
        self.assertEqual(species.growth_params().dbh_max_cm, 60.0)

    def test_species_values_override_defaults(self):
        species = TreeSpecies.objects.create(name='Pine', growth_dbh_max_cm=80)
        self.assertEqual(species.growth_params().dbh_max_cm, 80)
        self.assertEqual(species.growth_params().shape, 1.3)
