from django.urls import path

from . import views

app_name = 'tool_studio_xray'

urlpatterns = [
    path('demo/', views.demo_report, name='demo_report'),
    path('report/<uuid:run_id>/share/', views.send_to_manager, name='send_to_manager'),
    path('', views.landing, name='landing'),
    path('run/<uuid:run_id>/', views.progress, name='progress'),
    path('run/<uuid:run_id>/status/', views.status, name='status'),
    path('report/<uuid:run_id>/', views.report, name='report'),
    path('report/<uuid:run_id>/map.svg', views.system_map_svg, name='system_map_svg'),
    path('report/<uuid:run_id>/book/', views.book_review, name='book_review'),
    path('report/<uuid:run_id>/ask/', views.ask_question, name='ask_question'),
    path('question/<uuid:question_id>/', views.question_status, name='question_status'),
]
