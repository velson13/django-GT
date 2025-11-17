from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    # Auth
    path('login/', auth_views.LoginView.as_view(), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),

    # Clients
    path('clients/', views.clients_list, name='clients_list'),
    path('clients/add/', views.client_add, name='client_add'),
    path('clients/<int:pk>/edit/', views.client_edit, name='client_edit'),
    path('clients/<int:pk>/delete/', views.delete_client, name='delete_client'),

    path('klijent-info/<int:pk>/', views.klijent_info, name='klijent_info'),

    # Dokumenti
    path('dokumenti/', views.dokument_list, name='dokument_list'),
    path('nova/<str:tip>/', views.dokument_create, name='dokument_create'),
    path('izmena/<int:pk>/', views.dokument_edit, name='dokument_edit'),
    path('brisanje/<int:pk>/', views.dokument_delete, name='dokument_delete'),
    path("dokument/<int:pk>/details/", views.dokument_details, name="dokument_details"),
    
    # Invoices & Jobs
    path('invoices/', views.invoices_list, name='invoices_list'),
    path('jobs/', views.jobs_list, name='jobs_list'),

    # API calls
    path('check_sef/', views.check_sef, name='check_sef'),
    path('fetch-company-info/', views.fetch_company_info, name='fetch_company_info'),
    
    # Webhooks
    path("api/efaktura/ulazne/", views.sef_ulazne, name="sef_ulazne"),
    path("api/efaktura/ulazne", views.sef_ulazne, name="sef_ulazne"),
    path("api/efaktura/izlazne/", views.sef_izlazne, name="sef_izlazne"),
    path("api/efaktura/izlazne", views.sef_izlazne, name="sef_izlazne"),
]
