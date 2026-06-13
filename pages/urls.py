from django.urls import path

from . import views

app_name = 'pages'

urlpatterns = [
    path('privacy-policy/', views.privacy, name='privacy'),
    path('terms/', views.terms, name='terms'),
    path('odoo-version-support/', views.odoo_eol_index, name='odoo_eol_index'),
    path('odoo-version-support/<slug:slug>/', views.odoo_eol_detail, name='odoo_eol_detail'),
    path('odoo-version-support/<slug:slug>/go/xray/', views.eol_go_xray, name='odoo_eol_go_xray'),
    path('odoo-version-support/<slug:slug>/go/rescue/', views.eol_go_rescue, name='odoo_eol_go_rescue'),
]
