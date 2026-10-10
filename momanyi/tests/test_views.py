"""Page and form tests. Needs the Django test runner: python manage.py test"""
import json
from datetime import timedelta

from django.contrib.auth.models import User
from django.core.cache import cache
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from momanyi.models import County, Measurement, SubCounty, Tree, TreeEvent, TreeSpecies


class BaseCase(TestCase):

    def setUp(self):
        cache.clear()
        self.county = County.objects.create(name='Nakuru')
        self.other_county = County.objects.create(name='Kiambu')
        self.sub = SubCounty.objects.create(county=self.county, name='Njoro')
        self.other_sub = SubCounty.objects.create(county=self.other_county, name='Limuru')
        self.species = TreeSpecies.objects.create(name='Grevillea', wood_density=0.55)
        self.user = User.objects.create_user('amina', password='pass-12345', first_name='Amina', last_name='Wanjiru')
        self.other = User.objects.create_user('peter', password='pass-12345')
        self.staff = User.objects.create_user('admin1', password='pass-12345', is_staff=True, is_superuser=True)

    def payload(self, **overrides):
        data = {
            'species': self.species.pk, 'county': self.county.pk, 'subcounty': self.sub.pk,
            'plot_name': 'Block A', 'forest_category': 'afforestation', 'tree_status': 'alive',
            'latitude': '-0.303100', 'longitude': '36.080000',
            'contributor_type': 'individual', 'contributor_name': 'Wanjiku Kamau',
        }
        data.update(overrides)
        return data

    def make_tree(self, **extra):
        fields = dict(
            species=self.species, county=self.county, subcounty=self.sub,
            latitude='-0.303100', longitude='36.080000', plot_name='Block A',
            forest_category='afforestation', tree_status='alive',
            contributor_type='individual', contributor_name='Wanjiku Kamau',
            registered_by=self.user, planting_date=timezone.localdate() - timedelta(days=800))
        fields.update(extra)
        return Tree.objects.create(**fields)


class RegistrationTests(BaseCase):

    def test_login_required(self):
        response = self.client.get(reverse('tree_registration'))
        self.assertEqual(response.status_code, 302)
        self.assertIn('/accounts/login/', response['Location'])

    def test_form_page_loads(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('tree_registration'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Nakuru')
        self.assertContains(response, 'Grevillea')

    def test_successful_registration_credits_typed_name(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('tree_registration'), self.payload())
        tree = Tree.objects.get()
        self.assertRedirects(response, reverse('tree_detail', args=[tree.tree_id]))
        self.assertEqual(tree.contributor_name, 'Wanjiku Kamau')
        self.assertEqual(tree.registered_by, self.user)
        self.assertEqual(tree.verification_status, 'pending')
        self.assertTrue(TreeEvent.objects.filter(tree=tree, event_type='registered').exists())

    def test_initial_measurement_is_saved(self):
        self.client.force_login(self.user)
        self.client.post(reverse('tree_registration'), self.payload(initial_dbh='12.5', initial_height='6'))
        measurement = Measurement.objects.get()
        self.assertEqual(measurement.dbh_cm, 12.5)
        self.assertEqual(measurement.height_m, 6)

    def test_subcounty_from_another_county_is_rejected(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('tree_registration'), self.payload(subcounty=self.other_sub.pk))
        self.assertEqual(Tree.objects.count(), 0)
        self.assertEqual(response.status_code, 200)

    def test_duplicate_location_is_rejected(self):
        self.make_tree()
        self.client.force_login(self.user)
        self.client.post(reverse('tree_registration'), self.payload())
        self.assertEqual(Tree.objects.count(), 1)

    def test_location_outside_kenya_is_rejected(self):
        self.client.force_login(self.user)
        self.client.post(reverse('tree_registration'), self.payload(latitude='51.5', longitude='-0.12'))
        self.assertEqual(Tree.objects.count(), 0)

    def test_missing_species_is_rejected(self):
        self.client.force_login(self.user)
        self.client.post(reverse('tree_registration'), self.payload(species=''))
        self.assertEqual(Tree.objects.count(), 0)

    def test_height_without_diameter_is_rejected(self):
        self.client.force_login(self.user)
        self.client.post(reverse('tree_registration'), self.payload(initial_height='6'))
        self.assertEqual(Tree.objects.count(), 0)

    def test_failed_form_keeps_what_was_typed(self):
        self.client.force_login(self.user)
        response = self.client.post(reverse('tree_registration'), self.payload(species='', plot_name='My plot'))
        self.assertContains(response, 'My plot')


class AjaxTests(BaseCase):

    def post_json(self, lat, lng):
        return self.client.post(reverse('check_coordinate_availability'),
                                data=json.dumps({'latitude': lat, 'longitude': lng}),
                                content_type='application/json')

    def test_requires_login(self):
        self.assertEqual(self.post_json('-0.3', '36.08').status_code, 401)

    def test_free_location(self):
        self.client.force_login(self.user)
        data = self.post_json('-0.3031', '36.08').json()
        self.assertTrue(data['available'])

    def test_taken_location(self):
        self.make_tree()
        self.client.force_login(self.user)
        data = self.post_json('-0.3031', '36.08').json()
        self.assertFalse(data['available'])

    def test_nearby_tree_gives_a_warning_but_is_allowed(self):
        self.make_tree()
        self.client.force_login(self.user)
        data = self.post_json('-0.30315', '36.08').json()   # about 5 m away
        self.assertTrue(data['available'])
        self.assertEqual(data['status'], 'warning')

    def test_outside_kenya(self):
        self.client.force_login(self.user)
        self.assertFalse(self.post_json('51.5', '-0.12').json()['available'])

    def test_get_is_not_allowed(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse('check_coordinate_availability')).status_code, 405)

    def test_subcounties_endpoint(self):
        data = self.client.get(reverse('get_subcounties'), {'county_id': self.county.pk}).json()
        self.assertEqual([s['name'] for s in data['subcounties']], ['Njoro'])

    def test_subcounties_endpoint_without_county(self):
        self.assertEqual(self.client.get(reverse('get_subcounties')).json(), {'subcounties': []})


class PageTests(BaseCase):

    PUBLIC_PAGES = ['index', 'about', 'methodology', 'dashboard', 'carbon_score',
                    'oxygen_index', 'rankings', 'forest_map', 'login', 'signup']

    def test_public_pages_load_with_no_data(self):
        for name in self.PUBLIC_PAGES:
            with self.subTest(page=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)

    def test_public_pages_load_with_data(self):
        tree = self.make_tree()
        Measurement.objects.create(tree=tree, dbh_cm=14, height_m=8)
        self.make_tree(latitude='-0.304000', forest_category='existing')
        for name in self.PUBLIC_PAGES:
            with self.subTest(page=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)

    def test_carbon_page_shows_the_contributor_and_tree(self):
        tree = self.make_tree()
        response = self.client.get(reverse('carbon_score'))
        self.assertContains(response, tree.tree_id)
        self.assertContains(response, 'Wanjiku Kamau')

    def test_filter_by_search_text(self):
        self.make_tree()
        response = self.client.get(reverse('carbon_score'), {'q': 'zzz-nothing'})
        self.assertContains(response, 'No trees match')

    def test_rankings_filter_by_type(self):
        self.make_tree()
        self.make_tree(latitude='-0.304000', contributor_type='institution', contributor_name='Green School')
        response = self.client.get(reverse('rankings'), {'type': 'institution'})
        self.assertContains(response, 'Green School')
        self.assertNotContains(response, 'Wanjiku Kamau')

    def test_dead_trees_are_not_in_the_scores(self):
        self.make_tree(tree_status='dead')
        response = self.client.get(reverse('carbon_score'))
        self.assertContains(response, 'No trees match')

    def test_unknown_page_returns_404(self):
        self.assertEqual(self.client.get('/no-such-page/').status_code, 404)

    def test_logged_in_user_sees_logout_form(self):
        self.client.force_login(self.user)
        response = self.client.get(reverse('index'))
        self.assertContains(response, reverse('logout'))


class TreeDetailTests(BaseCase):

    def test_detail_page_loads(self):
        tree = self.make_tree()
        response = self.client.get(reverse('tree_detail', args=[tree.tree_id]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Grevillea')

        def test_detail_page_with_a_measurement_that_has_no_recorder(self):
            tree = self.make_tree()
        Measurement.objects.create(tree=tree, dbh_cm=14, height_m=8, measured_by=None)
        response = self.client.get(reverse('tree_detail', args=[tree.tree_id]))
        self.assertEqual(response.status_code, 200)

    def test_unknown_tree_is_404(self):
        self.assertEqual(self.client.get(reverse('tree_detail', args=['TREE-NOPE'])).status_code, 404)

    def test_owner_can_add_measurement(self):
        tree = self.make_tree()
        self.client.force_login(self.user)
        self.client.post(reverse('add_measurement', args=[tree.tree_id]),
                         {'measured_on': timezone.localdate().isoformat(), 'dbh_cm': '18.5', 'height_m': '9'})
        self.assertEqual(tree.measurements.count(), 1)
        self.assertTrue(TreeEvent.objects.filter(tree=tree, event_type='measured').exists())

    def test_other_user_cannot_add_measurement(self):
        tree = self.make_tree()
        self.client.force_login(self.other)
        self.client.post(reverse('add_measurement', args=[tree.tree_id]),
                         {'measured_on': timezone.localdate().isoformat(), 'dbh_cm': '18.5'})
        self.assertEqual(tree.measurements.count(), 0)

    def test_staff_can_add_measurement(self):
        tree = self.make_tree()
        self.client.force_login(self.staff)
        self.client.post(reverse('add_measurement', args=[tree.tree_id]),
                         {'measured_on': timezone.localdate().isoformat(), 'dbh_cm': '18.5'})
        self.assertEqual(tree.measurements.count(), 1)

    def test_invalid_measurement_is_rejected(self):
        tree = self.make_tree()
        self.client.force_login(self.user)
        self.client.post(reverse('add_measurement', args=[tree.tree_id]),
                         {'measured_on': timezone.localdate().isoformat(), 'dbh_cm': '-4'})
        self.assertEqual(tree.measurements.count(), 0)

    def test_measurement_changes_the_cached_scorecard(self):
        tree = self.make_tree()
        before = self.client.get(reverse('carbon_score')).content
        Measurement.objects.create(tree=tree, dbh_cm=40, height_m=25)
        after = self.client.get(reverse('carbon_score')).content
        self.assertNotEqual(before, after)


class DataEndpointTests(BaseCase):

    def test_api_returns_geojson_without_names(self):
        self.make_tree()
        data = self.client.get(reverse('tree_data_api')).json()
        self.assertEqual(data['type'], 'FeatureCollection')
        self.assertEqual(len(data['features']), 1)
        self.assertNotIn('Wanjiku', json.dumps(data))

    def test_csv_export_needs_staff(self):
        self.assertEqual(self.client.get(reverse('export_trees_csv')).status_code, 302)
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse('export_trees_csv')).status_code, 302)

    def test_csv_export_for_staff(self):
        self.make_tree()
        self.client.force_login(self.staff)
        response = self.client.get(reverse('export_trees_csv'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'text/csv')
        self.assertIn('TREE-', response.content.decode())

    def test_csv_export_blocks_formula_injection(self):
        self.make_tree(contributor_name='=HYPERLINK("http://bad")')
        self.client.force_login(self.staff)
        content = self.client.get(reverse('export_trees_csv')).content.decode()
        self.assertNotIn(',=HYPERLINK', content)


class AccountTests(BaseCase):

    def test_signup_creates_user_and_logs_in(self):
        response = self.client.post(reverse('signup'), {
            'first_name': 'Grace', 'last_name': 'Chebet', 'username': 'grace',
            'email': 'grace@example.org', 'password1': 'a-Strong-pass-77', 'password2': 'a-Strong-pass-77'})
        self.assertRedirects(response, reverse('tree_registration'))
        self.assertTrue(User.objects.filter(username='grace').exists())
        self.assertEqual(int(self.client.session['_auth_user_id']), User.objects.get(username='grace').pk)

    def test_duplicate_email_is_rejected(self):
        User.objects.create_user('first', email='dup@example.org', password='pass-12345')
        response = self.client.post(reverse('signup'), {
            'first_name': 'A', 'last_name': 'B', 'username': 'second',
            'email': 'DUP@example.org', 'password1': 'a-Strong-pass-77', 'password2': 'a-Strong-pass-77'})
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='second').exists())

    def test_logout_requires_post(self):
        self.client.force_login(self.user)
        self.assertEqual(self.client.get(reverse('logout')).status_code, 405)
        self.client.post(reverse('logout'))
        self.assertNotIn('_auth_user_id', self.client.session)


class AdminTests(BaseCase):

    def test_admin_pages_load(self):
        self.make_tree()
        self.client.force_login(self.staff)
        for name in ('admin:momanyi_tree_changelist', 'admin:momanyi_treespecies_changelist',
                     'admin:momanyi_county_changelist', 'admin:momanyi_subcounty_changelist',
                     'admin:momanyi_measurement_changelist'):
            with self.subTest(page=name):
                self.assertEqual(self.client.get(reverse(name)).status_code, 200)

    def test_verify_action(self):
        tree = self.make_tree()
        self.client.force_login(self.staff)
        self.client.post(reverse('admin:momanyi_tree_changelist'),
                         {'action': 'mark_verified', '_selected_action': [tree.pk]})
        tree.refresh_from_db()
        self.assertEqual(tree.verification_status, 'verified')
        self.assertEqual(tree.verified_by, self.staff)
        self.assertTrue(TreeEvent.objects.filter(tree=tree, event_type='verified').exists())

    def test_rejected_trees_leave_the_scores(self):
        tree = self.make_tree()
        tree.verification_status = 'rejected'
        tree.save()
        response = self.client.get(reverse('carbon_score'))
        self.assertContains(response, 'No trees match')
