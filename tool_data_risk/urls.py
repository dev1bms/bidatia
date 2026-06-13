from django.urls import path

from . import views

app_name = 'tool_data_risk'

urlpatterns = [
    path('', views.landing, name='landing'),
    path('demo/', views.demo_report, name='demo_report'),
    path('run/<uuid:run_id>/', views.progress, name='progress'),
    path('run/<uuid:run_id>/status/', views.status, name='status'),
    path('report/<uuid:run_id>/', views.report, name='report'),
    path('report/<uuid:run_id>/book/', views.book_review, name='book_review'),
    path('report/<uuid:run_id>/share/', views.send_to_manager, name='send_to_manager'),
    path('go/xray/', views.go_xray, name='go_xray'),
    path('go/rescue/', views.go_rescue, name='go_rescue'),
]
