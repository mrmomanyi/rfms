"""Scorecard tests. These use simple stand-in objects, so no database is needed."""
import unittest
from datetime import date, datetime
from types import SimpleNamespace as NS

from momanyi import calculations as calc
from momanyi import services

TODAY = date(2026, 10, 9)


class _Measurements:
    def __init__(self, items):
        self.items = items

    def all(self):
        return self.items


def make_tree(n, category='afforestation', density=0.55, planting=None, who='Wanjiku Kamau',
              kind='individual', measurements=None, verification='pending', county='Nakuru'):
    species = NS(name='Grevillea', wood_density=density, growth_params=lambda: calc.GrowthParams())
    return NS(
        tree_id=f'T{n}', species=species, forest_category=category, planting_date=planting,
        registration_date=datetime(2024, 1, 1), county=NS(name=county), subcounty=NS(name='Njoro'),
        plot_name='Plot', contributor_name=who, contributor_type=kind,
        verification_status=verification, measurements=_Measurements(measurements or []))


class ServiceTests(unittest.TestCase):

    def setUp(self):
        self.trees = [
            make_tree(1, planting=date(2021, 10, 9)),
            make_tree(2, measurements=[NS(measured_on=date(2026, 6, 1), dbh_cm=30, height_m=20, pk=1)],
                      verification='verified'),
            make_tree(3, category='existing'),
            make_tree(4, category='existing', who='GREEN SCHOOL', kind='institution',
                      measurements=[NS(measured_on=date(2026, 1, 1), dbh_cm=45, height_m=None, pk=2)]),
            make_tree(5, who='wanjiku kamau', county='Kiambu'),
        ]
        self.card = services.build_scorecard(self.trees, today=TODAY)

    def test_counts(self):
        s = self.card.summary
        self.assertEqual(s['trees_total'], 5)
        self.assertEqual(s['trees_counted'], 4)
        self.assertEqual(s['needs_measurement'], 1)
        self.assertEqual(s['measured_trees'], 2)
        self.assertEqual(s['verified_trees'], 1)

    def test_stock_is_removal_plus_existing(self):
        s = self.card.summary
        self.assertAlmostEqual(s['stock_co2e_kg'], s['removal_co2e_kg'] + s['existing_co2e_kg'], delta=0.2)

    def test_existing_forest_is_not_counted_as_removal(self):
        rows = {r['tree_id']: r for r in self.card.rows}
        self.assertFalse(rows['T4']['counts_as_removal'])
        self.assertTrue(rows['T1']['counts_as_removal'])
        self.assertGreater(self.card.summary['existing_co2e_kg'], 0)

    def test_unknown_age_without_measurement_is_not_estimated(self):
        row = [r for r in self.card.rows if r['tree_id'] == 'T3'][0]
        self.assertTrue(row['needs_measurement'])
        self.assertIsNone(row['co2e_kg'])

    def test_names_are_grouped_without_regard_to_case(self):
        matches = [c for c in self.card.contributors if c['name'].lower() == 'wanjiku kamau']
        self.assertEqual(len(matches), 1)
        self.assertEqual(matches[0]['trees'], 3)

    def test_ranking_order_and_numbers(self):
        self.assertEqual([c['rank'] for c in self.card.contributors], [1, 2])
        self.assertEqual(self.card.contributors[0]['name'], 'Wanjiku Kamau')

    def test_verified_only_ranking(self):
        card = services.build_scorecard(self.trees, today=TODAY, rank_verified_only=True)
        self.assertEqual([c['trees'] for c in card.contributors], [1])

    def test_forecast_has_six_points_and_grows(self):
        self.assertEqual(len(self.card.forecast_labels), 6)
        self.assertGreater(self.card.forecast_removal_kg[-1], self.card.forecast_removal_kg[0])

    def test_measured_existing_tree_has_forecast_and_increment(self):
        row = [r for r in self.card.rows if r['tree_id'] == 'T4'][0]
        self.assertEqual(row['method'], 'measured')
        self.assertGreater(row['annual_co2e_kg'], 0)

    def test_oxygen_follows_carbon(self):
        row = [r for r in self.card.rows if r['tree_id'] == 'T2'][0]
        self.assertAlmostEqual(row['oxygen_kg'], row['co2e_kg'] * calc.O2_PER_CO2, delta=0.2)

    def test_empty_input(self):
        card = services.build_scorecard([], today=TODAY)
        self.assertEqual(card.summary['trees_counted'], 0)
        self.assertEqual(card.contributors, [])
        self.assertEqual(card.summary['avg_confidence'], 0)

    def test_default_density_is_flagged(self):
        card = services.build_scorecard([make_tree(9, density=None, planting=date(2022, 1, 1))], today=TODAY)
        self.assertTrue(card.rows[0]['uses_default_density'])
        self.assertEqual(card.summary['default_density_trees'], 1)


if __name__ == '__main__':
    unittest.main()
