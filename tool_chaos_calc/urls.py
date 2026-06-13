from django.urls import path

from . import views

app_name = 'tool_chaos_calc'

urlpatterns = [
    path('', views.landing, name='landing'),
    path('go/rescue/', views.go_rescue, name='go_rescue'),
    path('go/xray/', views.go_xray, name='go_xray'),
]
