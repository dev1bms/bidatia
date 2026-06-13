from django.urls import path

from . import views

app_name = 'blog'

urlpatterns = [
    path('', views.blog_list, name='blog_list'),
    path('<slug:slug>/', views.blog_detail, name='blog_detail'),
]

case_study_urlpatterns = [
    path('', views.case_study_list, name='case_study_list'),
    path('<slug:slug>/', views.case_study_detail, name='case_study_detail'),
]
