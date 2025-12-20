from django.http import HttpResponse
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
    path('nova-blanko/<str:tip>/', views.dokument_create_empty, name='dokument_create_empty'),
    path('izmena/<int:pk>/', views.dokument_edit, name='dokument_edit'),
    path('brisanje/<int:pk>/', views.dokument_delete, name='dokument_delete'),
    path("dokument/<int:pk>/storno/", views.dokument_storno_view, name="dokument_storno"),
    path("dokument/<int:pk>/details/", views.dokument_details, name="dokument_details"),

    path('izf/<int:izf_id>/otp/<int:otp_id>/unlink/', views.unlink_otp_from_izf, name='unlink_otp_from_izf'),
    path("izf/<int:izf_id>/otp/<int:otp_id>/link/", views.link_otp_to_izf, name="link_otp_to_izf"),

    # Invoices & Jobs
    path('invoices/', views.invoices_list, name='invoices_list'),
    path('jobs/', views.jobs_list, name='jobs_list'),

    # API calls
    path('check_sef/', views.check_sef, name='check_sef'),
    path('fetch-company-info/', views.fetch_company_info, name='fetch_company_info'),
    path('upload-invoice/<int:pk>/', views.upload_invoice, name='upload_invoice'),
    
    # Webhooks
    path("api/efaktura/ulazne/", views.sef_ulazne, name="sef_ulazne"),
    path("api/efaktura/izlazne/", views.sef_izlazne, name="sef_izlazne"),
    path("api/efaktura/webhooks/", views.webhook_list, name="webhook_list"),
    path("api/efaktura/webhooks/delete/", views.delete_webhooks, name="webhook_delete"),
    path("webhooks/process/", views.process_webhooks_view, name="webhooks_process"),

    # Reports
    # path("reports/kpo/", views.kpo_report, name="kpo_report"),
    path("reports/kpo/pdf/", views.kpo_pdf, name="kpo_pdf"),
    path("reports/otpremnica/pdf/<int:doc_id>/", views.otpremnica_pdf, name="otpremnica_pdf"),
    path("reports/faktura/pdf/<int:doc_id>/", views.faktura_pdf, name="faktura_pdf"),
    # path("reports/editor/", views.kpo_editor, name="kpo_editor"),
    # path("invoice/<int:id>/print/", views.invoice_print, name="invoice_print"),
    # path("invoice/<int:id>/print/pdf/", views.invoice_print_pdf, name="invoice_print_pdf"),
    # path("otp/<int:id>/print/", views.otp_print, name="otp_print"),
    # path("otp/<int:id>/print/pdf/", views.otp_print_pdf, name="otp_print_pdf"),
]

def health(request):
    return HttpResponse("OK")

urlpatterns += [
    path("healthcheck/", health),
]