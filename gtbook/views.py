import traceback
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.shortcuts import render, redirect, get_object_or_404
from .models import Client, DEF_OPT
from .forms import ClientForm
from django.utils.timezone import now
from django.db.models.functions import TruncMonth
from django.db.models import Count
from django.db.models import Q
import calendar, requests
from django.http import JsonResponse
from django.views.decorators.http import require_GET
from .utils.api_calls import get_company_accounts, parse_company_accounts, check_pib_in_sef

@require_GET
def fetch_company_info(request):
    pib = request.GET.get("pib")
    if not pib:
        return JsonResponse({"error": "PIB mora imati 9 cifara"}, status=400)

    try:
        xml_str = get_company_accounts(pib)
        accounts = parse_company_accounts(xml_str)
        return JsonResponse({"accounts": accounts})
    except Exception as e:
        print("=== NBS Fetch Error ===")
        print(traceback.format_exc())   # full error in Django console
        return JsonResponse({"error": str(e)}, status=500)

@require_GET
def check_sef(request):
    pib = request.GET.get('pib', '').strip()
    if len(pib) != 9 or not pib.isdigit():
        return JsonResponse({"registered": False, "error": "PIB mora imati 9 cifara"}, status=400)

    try:
        result = check_pib_in_sef(pib)
        # Budget user (warning present) → 400 to highlight special case
        if "warning" in result:
            return JsonResponse(result, status=400)

        # Normal registered or NOT registered → always 200
        return JsonResponse(result, status=200)
    except Exception as e:
        return JsonResponse({"registered": False, "error": str(e)}, status=500)

@login_required
def dashboard(request):
    total_clients = Client.objects.count()
    # total_invoices = Invoice.objects.count() if 'Invoice' in globals() else 0
    # total_jobs = Job.objects.count() if 'Job' in globals() else 0

    # Last 5 records
    recent_clients = Client.objects.all().order_by('-id')[:5]
    # recent_invoices = Invoice.objects.all().order_by('-id')[:5] if 'Invoice' in globals() else []
    # recent_jobs = Job.objects.all().order_by('-id')[:5] if 'Job' in globals() else []

    # Monthly data for charts (last 12 months)
    from datetime import timedelta
    from django.utils.timezone import make_aware, datetime as dt

    today = now().date()
    months = []
    client_counts = []
    invoice_counts = []

    for i in reversed(range(12)):
        month_date = (today.replace(day=1) - timedelta(days=i*30)).replace(day=1)
        month_str = month_date.strftime("%b %Y")
        months.append(month_str)

        clients_in_month = Client.objects.filter(
            id__isnull=False  # placeholder if no date field, replace with created_at if exists
        ).count()  # update with filter by created_at if you have it

        # invoices_in_month = Invoice.objects.filter(
        #     id__isnull=False  # placeholder
        # ).count()  # update with filter by date field

        client_counts.append(clients_in_month)
        # invoice_counts.append(invoices_in_month)

        # Placeholder: empty lists for invoices and jobs
        recent_invoices = []
        recent_jobs = []

    context = {
        'total_clients': total_clients,
        'total_invoices': 0,#total_invoices,
        'total_jobs': 0,#total_jobs,
        'recent_clients': recent_clients,
        'recent_invoices': recent_invoices,
        'recent_jobs': recent_jobs,
        'months': months,
        'client_counts': client_counts,
        'invoice_counts': invoice_counts,
    }
    return render(request, 'dashboard.html', context)

@login_required
def clients_list(request):
    sort = request.GET.get("sort", "ime")
    order = request.GET.get("order", "asc")
    search = request.GET.get("search", "")
    defcom_filters = request.GET.getlist("defcom")
    
    allowed = ["id", "ime", "pib", "mbr"] #, "jbkjs", "adresa", "mesto"]
    if sort not in allowed:
        sort = "ime"

    sort_prefix = "-" if order == "desc" else ""
    clients = Client.objects.all()

    # Text search
    if search:
        clients = clients.filter(
            Q(ime__icontains=search) |
            Q(pib__icontains=search) |
            Q(kontakt__icontains=search) |
            Q(email__icontains=search) |
            Q(mbr__icontains=search)
        )

    clients = clients.order_by(f"{sort_prefix}{sort}")
    # clients = Client.objects.all().order_by(f"{sort_prefix}{sort}")
    
    # Apply defcom filter
    if defcom_filters:
        bits = [int(f) for f in defcom_filters if f.isdigit()]
        clients = [c for c in clients if all(c.defcode & b for b in bits)] # AND logic

    # Compute human-readable defcode options
    for client in clients:
        client.defcode_options = []
        for bit, label in DEF_OPT:
            if client.defcode & bit:
                client.defcode_options.append(label)
        
    sortable_columns = [
        ("id", "ID"),
        ("ime", "Ime"),
        ("pib", "PIB"),
        ("mbr", "MBR"),
        # ("jbkjs", "JBKJS"),
        # ("adresa", "Addresa"),
        # ("mesto", "Mesto"),
    ]

    return render(request, "clients_list.html", {
        "clients": clients,
        "sort": sort,
        "order": order,
        "sortable_columns": sortable_columns,
        "search": search,
        "defcom_filters": defcom_filters,
        "def_opt": DEF_OPT,
    })

# @login_required
# def client_detail(request, pk):
#     client = get_object_or_404(Client, pk=pk)
#     return render(request, 'client_detail.html', {'client': client})

@login_required
def client_add(request):
    if request.method == 'POST':
        form = ClientForm(request.POST)
        if form.is_valid():
            client = form.save()
            messages.success(
                request,
                f'<i class="text-success"></i> Klijent <strong>{client.ime}</strong> uspešno dodat.'
            )
            return redirect("clients_list")
    else:
        form = ClientForm()
    return render(request, 'client_form.html', {'form': form})

@login_required
def client_edit(request, pk):
    client = get_object_or_404(Client, pk=pk)
    if request.method == 'POST':
        form = ClientForm(request.POST, instance=client)
        if form.is_valid():
            form.save()
            messages.success(
                request,
                f'<i class="text-primary"></i> Klijent <strong>{client.ime}</strong> uspešno izmenjen.'
            )
            return redirect("clients_list")
    else:
        form = ClientForm(instance=client)
    return render(request, 'client_form.html', {'form': form, 'edit_mode': True})

@login_required
def delete_client(request, pk):
    client = get_object_or_404(Client, pk=pk)
    if request.method == "POST":
        client_name = client.ime
        client.delete()
        messages.success(
            request,
            f'<i class="text-danger"></i> Klijent <strong>{client_name}</strong> uspešno izbrisan.'
        )
        return redirect("clients_list")

@login_required
def invoices_list(request):
    return render(request, 'invoices.html')

@login_required
def jobs_list(request):
    return render(request, 'jobs.html')
