from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

urlpatterns = [
    # auth
    path('login/', auth_views.LoginView.as_view(), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),
    #clients
    path('clients/', views.clients_list, name='clients_list'),
    path("<int:pk>/", views.client_detail, name="client_detail"),
    path('clients/add/', views.client_add, name='client_add'),
    path('clients/<int:pk>/edit/', views.client_edit, name='client_edit'),
    path("clients/delete/<int:client_id>/", views.delete_client, name="delete_client"),
    path('invoices/', views.invoices_list, name='invoices'),
    path('jobs/', views.jobs_list, name='jobs'),
]
