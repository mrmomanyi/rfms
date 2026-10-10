from django.urls import path

from . import views

urlpatterns = [
    path('', views.index, name='index'),
    path('about/', views.about, name='about'),
    path('methodology/', views.methodology, name='methodology'),

    # Registration and trees
    path('tree_registration/', views.tree_registration, name='tree_registration'),
    path('check-coordinates/', views.check_coordinate_availability, name='check_coordinate_availability'),
    path('get-subcounties/', views.get_subcounties, name='get_subcounties'),
    path('trees/<str:tree_id>/', views.tree_detail, name='tree_detail'),
    path('trees/<str:tree_id>/measure/', views.add_measurement, name='add_measurement'),

    # Dashboards
    path('dashboard/', views.dashboard, name='dashboard'),
    path('carbon-score/', views.carbon_score_view, name='carbon_score'),
    path('oxygen-index/', views.oxygen_index_view, name='oxygen_index'),
    path('rankings/', views.rankings, name='rankings'),
    path('map/', views.forest_map, name='forest_map'),

    # Data
    path('api/trees/', views.tree_data_api, name='tree_data_api'),
    path('export/trees.csv', views.export_trees_csv, name='export_trees_csv'),

    # Accounts (login and logout come from django.contrib.auth.urls in the project urls)
    path('accounts/signup/', views.signup, name='signup'),
]
