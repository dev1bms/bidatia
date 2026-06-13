from django.urls import path

from . import views

app_name = 'leads'

urlpatterns = [
    path('', views.contact, name='contact'),
    path('thank-you/', views.contact_success, name='contact_success'),
]
