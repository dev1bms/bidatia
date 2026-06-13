from django.urls import path

from . import badge_views, views

app_name = 'tools_core'

urlpatterns = [
    path('', views.hub, name='hub'),
    path('api/test-connection/', views.test_connection_api, name='test_connection'),
    path('api/track/', views.track_event, name='track_event'),
    path('api/detect-database/', views.detect_database_api, name='detect_database'),
    path('badge/create/<uuid:run_id>/', badge_views.badge_create, name='badge_create'),
    path('badge/<uuid:badge_id>/', badge_views.badge_verify, name='badge_verify'),
    path('badge/<uuid:badge_id>/badge.svg', badge_views.badge_svg, name='badge_svg'),
]
