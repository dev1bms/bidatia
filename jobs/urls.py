from django.urls import path

from . import views

app_name = 'jobs'

urlpatterns = [
    path('<uuid:pk>/status/', views.status_json, name='status'),
    path('<uuid:pk>/', views.status_page, name='detail'),
]
