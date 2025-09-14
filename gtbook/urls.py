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

    # # Optional detail page
    # path('clients/<int:pk>/', views.client_detail, name='client_detail'),

    # Invoices & Jobs
    path('invoices/', views.invoices_list, name='invoices_list'),
    path('jobs/', views.jobs_list, name='jobs_list'),

    # API calls
    path('check_sef/', views.check_sef, name='check_sef'),
    path("fetch-company-info/", views.fetch_company_info, name="fetch_company_info"),
]
