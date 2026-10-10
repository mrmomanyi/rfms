import unittest

from momanyi.calculations import (
    CO2_PER_CARBON, O2_PER_CO2, GrowthParams, above_ground_biomass_kg,
    age_from_dbh, annual_co2e_increment, confidence_score, forecast_co2e,
    modelled_dbh_cm, oxygen_from_co2e, tree_carbon,
)


class CalculationTests(unittest.TestCase):

    def test_chave_equation_known_value(self):
        # rho 0.6, D 30 cm, H 20 m -> 0.0673 * (0.6 * 900 * 20) ^ 0.976, about 581 kg
        self.assertAlmostEqual(above_ground_biomass_kg(30, 20, 0.6), 581, delta=3)

    def test_wood_density_matters(self):
        self.assertGreater(above_ground_biomass_kg(30, 20, 0.8), above_ground_biomass_kg(30, 20, 0.4))

    def test_zero_or_negative_size_gives_zero(self):
        self.assertEqual(above_ground_biomass_kg(0, 20), 0.0)
        self.assertEqual(above_ground_biomass_kg(30, -1), 0.0)

    def test_stoichiometry_constants(self):
        self.assertAlmostEqual(CO2_PER_CARBON, 3.6667, places=3)
        self.assertAlmostEqual(O2_PER_CO2, 0.7273, places=3)
        self.assertAlmostEqual(oxygen_from_co2e(100), 72.73, places=1)

    def test_measured_tree_pipeline(self):
        t = tree_carbon(10, dbh_cm=30, height_m=20, wood_density=0.6)
        self.assertEqual(t.method, 'measured')
        self.assertAlmostEqual(t.co2e_kg, 1262, delta=15)
        self.assertEqual(t.confidence, 85)

    def test_modelled_tree_has_low_confidence(self):
        t = tree_carbon(5)
        self.assertEqual(t.method, 'modelled')
        self.assertEqual(t.confidence, 35)
        self.assertGreater(t.co2e_kg, 0)

    def test_new_seedling_stores_almost_nothing(self):
        self.assertEqual(tree_carbon(0).co2e_kg, 0.0)

    def test_stock_grows_with_age(self):
        values = [tree_carbon(a).co2e_kg for a in (1, 3, 5, 10, 20)]
        self.assertEqual(values, sorted(values))
        self.assertGreater(annual_co2e_increment(5), 0)

    def test_dbh_only_estimates_height(self):
        t = tree_carbon(8, dbh_cm=20)
        self.assertEqual(t.confidence, 70)
        self.assertGreater(t.height_m, 0)

    def test_age_inversion_round_trip(self):
        p = GrowthParams()
        self.assertAlmostEqual(age_from_dbh(modelled_dbh_cm(12, p), p), 12, places=3)

    def test_confidence_rules(self):
        self.assertEqual(confidence_score('measured', True, 30), 70)
        self.assertEqual(confidence_score('measured', True, 6, verified=True), 95)
        self.assertEqual(confidence_score('modelled', False, verified=True), 45)

    def test_forecast_anchors_to_measurement(self):
        now = tree_carbon(10, dbh_cm=30, height_m=20, wood_density=0.6)
        series = forecast_co2e(10, years=5, current=now, wood_density=0.6)
        self.assertEqual(len(series), 6)
        self.assertAlmostEqual(series[0], now.co2e_kg, places=1)
        self.assertGreater(series[5], series[0])


if __name__ == '__main__':
    unittest.main()
