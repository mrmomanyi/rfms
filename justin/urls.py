"""Project URL configuration."""
from django.contrib import admin
from django.urls import include, path

admin.site.site_header = 'RFMS administration'
admin.site.site_title = 'RFMS admin'
admin.site.index_title = 'Forest Resource Monitoring System'

handler404 = 'momanyi.views.page_not_found'

urlpatterns = [
    path('admin/', admin.site.urls),
    # Built-in login, logout and password views (login.html lives in templates/registration)
    path('accounts/', include('django.contrib.auth.urls')),
    # The app. Its own urls.py also defines accounts/signup/
    path('', include('momanyi.urls')),
]
