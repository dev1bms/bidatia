from django.urls import path

from . import views

app_name = 'glossary'

urlpatterns = [
    path('', views.index, name='index'),
    path('<slug:slug>/', views.term_detail, name='term'),
    path('<slug:slug>/go/', views.go_tool, name='go_tool'),
]
