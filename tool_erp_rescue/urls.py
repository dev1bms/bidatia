from django.urls import path

from . import views

app_name = 'tool_erp_rescue'

urlpatterns = [
    path('', views.landing, name='landing'),
    path('result/<uuid:run_id>/', views.result, name='result'),
    path('result/<uuid:run_id>/book/', views.book_review, name='book_review'),
    path('result/<uuid:run_id>/advisor/', views.advisor_status, name='advisor_status'),
    path('result/<uuid:run_id>/share/', views.send_to_manager, name='send_to_manager'),
]
