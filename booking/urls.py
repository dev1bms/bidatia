from django.urls import path

from . import views

app_name = 'booking'

urlpatterns = [
    path('', views.book_consultation, name='book_consultation'),
    path('thank-you/', views.booking_success, name='booking_success'),
]
