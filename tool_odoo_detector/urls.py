from django.urls import path

from . import views

app_name = 'tool_odoo_detector'

urlpatterns = [
    path('', views.landing, name='landing'),
    path('go/xray/', views.go_xray, name='go_xray'),
    path('go/rescue/', views.go_rescue, name='go_rescue'),
    path('go/demo/', views.go_demo, name='go_demo'),
]
