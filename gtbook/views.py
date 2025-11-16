import json
import traceback
import hmac
import hashlib
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.forms import inlineformset_factory
from django.shortcuts import render, redirect, get_object_or_404
from .models import Klijenti, Dokumenti, DokumentStavke, DEF_OPT
from .forms import ClientForm, DokumentForm, DokumentStavkeForm, DokumentStavkeFormSet
from django.utils.timezone import now, localdate, timedelta
from django.db.models.functions import TruncMonth
from django.db.models import Q, Count, F, ExpressionWrapper, BooleanField
from django.db import IntegrityError, transaction
import calendar, requests
from datetime import date, datetime
from django.conf import settings
from django.http import JsonResponse, Http404, HttpResponse, HttpResponseForbidden
from django.template.loader import render_to_string
from django.views.decorators.http import require_GET
from django.views.decorators.csrf import csrf_exempt
from .utils.api_calls import get_company_accounts, parse_company_accounts, check_pib_in_sef
from .utils.utils import next_dok_number, filter_klijenti_by_tip_sqlite
from .utils.efaktura.hooks import verify_hookrelay_signature

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
    total_clients = Klijenti.objects.count()
    # total_invoices = Dokumenti.objects.count() if 'Dokumenti' in globals() else 0
    # total_jobs = Job.objects.count() if 'Job' in globals() else 0

    # Last 5 records
    recent_clients = Klijenti.objects.all().order_by('-id')[:5]
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

        clients_in_month = Klijenti.objects.filter(
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
    clients = Klijenti.objects.all()

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
    
    # Apply defcom filter
    if defcom_filters:
        bits = [int(f) for f in defcom_filters if f.isdigit()]
        #clients = [c for c in clients if all(c.defcode & b for b in bits)] # AND logic
        for b in bits:
            clients = clients.filter(defcode__bitand=b)


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
    client = get_object_or_404(Klijenti, pk=pk)
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
    client = get_object_or_404(Klijenti, pk=pk)
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
    #return render(request, 'dokument_form.html')

@login_required
def jobs_list(request):
    return render(request, 'jobs.html')

@login_required
def dokument_create(request, tip):
    # Kreira novi dokument odredjenog tipa (tip = Izlazna faktura, Ulazna faktura, Otpremnica)
    client = None
    today = now().strftime("%d.%m.%Y")
    # Compute next document number for auto-numbered types
    next_number = next_dok_number(tip) if tip in ["IZF", "OTP"] else ""
    initial_data = {
        "dok_tip": tip,
        "dok_datum": today,
        "prm_datum": today,
        "dok_br": next_number,
    }
    # Compute dok_br only for auto-numbered types
    #if request.method == "GET" and tip in ["IZF", "RAC", "OTP"]:
    #    initial_data["dok_br"] = next_dok_number(tip)

    # Prefill client info if 'klijent' param is present
    klijent_id = request.GET.get("klijent")
    if klijent_id:
        try:
            client = Klijenti.objects.get(pk=klijent_id)
            initial_data.update({
                "client_address": client.adresa,
                "client_pib": client.pib,
                "client_mbr": client.mbr
            })
        except Klijenti.DoesNotExist:
            client = None

    klijenti = filter_klijenti_by_tip_sqlite(tip).annotate(
        sef_flag=ExpressionWrapper(F('defcode').bitand(4), output_field=BooleanField())
    )
            
    if request.method == "POST":    
        data = request.POST.copy()
        if tip in ["IZF", "OTP"] and not data.get("dok_br"):
            data["dok_br"] = next_dok_number(tip)
        form = DokumentForm(data, request.FILES)
        formset = DokumentStavkeFormSet(request.POST, instance=None)
        form.fields['klijent'].queryset = klijenti
        if not form.is_valid():
            if not form.cleaned_data.get('klijent'):
                messages.error(request, "Klijent nije izabran.")
            else:
                messages.error(request, "Nije unet broj dokumenta.")

            context = {
                "form": form, "formset": formset, "tip": tip,
                "title": f"Nova {dict(Dokumenti.TIPOVI_DOK).get(tip, tip)}",
                "klijenti": klijenti.order_by("ime"),
                "today": today,
                "next_number": next_number,
            }
            return render(request, "dokument_form.html", context)

        # If valid, create document instance
        dok = form.save(commit=False)
        dok.dok_tip = tip

        # Check that there are items (ignore blank rows)
        if form.is_valid() and formset.is_valid():
            valid_items = [fs for fs in formset if fs.cleaned_data and not fs.cleaned_data.get("DELETE", False)]
            if not valid_items:
                messages.error(request, "Dokument mora sadržati bar jednu stavku.")
                context = {
                    "form": form, "formset": formset, "tip": tip,
                    "title": f"Nova {dict(Dokumenti.TIPOVI_DOK).get(tip, tip)}",
                    "klijenti": klijenti.order_by("ime"),
                    "today": today,
                    "next_number": next_number,
                }
                return render(request, "dokument_form.html", context)
            # Only check for duplicates for ULF (ulazna faktura)
            if tip == "ULF":
                exists = Dokumenti.objects.filter(dok_tip="ULF", dok_br=dok.dok_br).exists()
                if exists:
                    messages.error(request, f"Dokument sa brojem {dok.dok_br} već postoji.")
                    context = {
                        "form": form, "formset": formset, "tip": tip,
                        "title": f"Nova {dict(Dokumenti.TIPOVI_DOK).get(tip, tip)}",
                        "klijenti": klijenti.order_by("ime"),
                        "today": today,
                        "next_number": next_number,
                    }
                    return render(request, "dokument_form.html", context)
        
        # Generate document number if needed
        if tip in ["IZF", "OTP"]:
            dok.dok_br = next_dok_number(tip)

        # Auto-calculate val_datum if not OTP
        if tip != 'OTP' and dok.prm_datum:
            dok.val_datum = dok.prm_datum + timedelta(days=30)
        else:
            dok.val_datum = None
        
        dok.save()

        formset.instance = dok
        if formset.is_valid():
            formset.save()
        
        # --- Sum and update totals ---
        iznos_P = iznos_U = 0
        for item in dok.stavke.all():
            # Example: item.tip_prometa is "P" or "U"
            # tip_prometa = item.tip_prometa or "P"
            if item.tip_prometa == "P":
                iznos_P += item.cena * item.kolicina
            elif item.tip_prometa == "U":
                iznos_U += item.cena * item.kolicina

        dok.iznos_P = iznos_P
        dok.iznos_U = iznos_U
        dok.save(update_fields=["iznos_P", "iznos_U"])
        print(request, f"{dict(Dokumenti.TIPOVI_DOK).get(tip, tip)} #{dok.dok_br} uspešno kreirana.")
        messages.success(request, f"{dict(Dokumenti.TIPOVI_DOK).get(tip, tip)} #{dok.dok_br} uspešno kreirana.")


        # ✅ Handle OTP auto-create if requested
        if request.POST.get("otp-switch") == "on":
            try:
                with transaction.atomic():
                    otp = Dokumenti.objects.create(
                        dok_tip="OTP",
                        dok_datum=dok.dok_datum,
                        prm_datum=dok.prm_datum,
                        klijent=dok.klijent,
                        dok_br=next_dok_number("OTP"),
                        napomena=f"Automatski kreirana otpremnica za {dok.dok_tip} #{dok.dok_br}",
                        val_datum=None,
                        iznos_U=iznos_U,
                        iznos_P=iznos_P,
                        faktura=dok,  # 🔗 link Otpremnica → Faktura
                    )
                    # Duplicate the items from original document
                    for item in dok.stavke.all():
                        item_data = {
                            field.name: getattr(item, field.name)
                            for field in item._meta.fields
                            if field.name not in ["id", "pk", "dokument"]
                        }
                        item_data["dokument"] = otp  # assign to the new document
                        DokumentStavke.objects.create(**item_data)
                    print(request, f"Otpremnica #{otp.dok_br} automatski kreirana.")
                    messages.success(request, f"Otpremnica #{otp.dok_br} automatski kreirana.")
            except Exception as e:
                messages.error(
                    request,
                    f"Greška pri kreiranju otpremnice: {str(e)}. "
                    "Nijedna stavka nije sačuvana.",
                )
        return redirect("dokument_list")#, tip=tip)

    # GET request (initial form)
    else:
        form = DokumentForm(initial=initial_data)
        formset = DokumentStavkeFormSet(instance=None)
        form.fields["klijent"].queryset = klijenti

    context = {
        "form": form,
        "formset": formset,
        "tip": tip,
        "title": f"Nova {dict(Dokumenti.TIPOVI_DOK).get(tip, tip)}",
        "klijenti": klijenti.order_by("ime"),
        "today": today,
        "next_number": initial_data.get("dok_br", ""),
    }
    return render(request, "dokument_form.html", context)

@login_required
def dokument_edit(request, pk):
    try:
        dokument = get_object_or_404(Dokumenti, pk=pk)
    except Http404:
        messages.error(request, "Dokument nije pronađen.")
        return redirect('dokument_list')
    
    tip = dokument.dok_tip  # preserve type

    DokumentStavkeFormSet = inlineformset_factory(
    Dokumenti, DokumentStavke,
    form=DokumentStavkeForm,
    can_delete=True,
    extra=0  # ✅ no extra blank row
    )

    if request.method == "POST":
        form = DokumentForm(request.POST, request.FILES, instance=dokument)
        formset = DokumentStavkeFormSet(request.POST, instance=dokument)

        # if not form.is_valid() or not formset.is_valid():
        #     print("FORM ERRORS:", form.errors)            # temporarily log to console
        #     print("FORMSET ERRORS:", formset.errors)
        #     print("FORMSET NON_FORM_ERRORS:", formset.non_form_errors())

        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()

            # --- Sum and update totals ---
            iznos_P = iznos_U = 0
            for item in dokument.stavke.all():
                # Example: item.tip_prometa is "P" or "U"
                # tip_prometa = item.tip_prometa or "P"
                if item.tip_prometa == "P":
                    iznos_P += item.cena * item.kolicina
                elif item.tip_prometa == "U":
                    iznos_U += item.cena * item.kolicina

            dokument.iznos_P = iznos_P
            dokument.iznos_U = iznos_U
            dokument.save(update_fields=["iznos_P", "iznos_U"])
            messages.success(
                request,
                f"{dict(Dokumenti.TIPOVI_DOK).get(tip, tip)} #{dokument.dok_br} uspešno izmenjena."
            )
            return redirect("dokument_list")
    else:
        form = DokumentForm(instance=dokument)
        formset = DokumentStavkeFormSet(instance=dokument)

    # Filter clients
    klijenti = filter_klijenti_by_tip_sqlite(tip).annotate(
        sef_flag=ExpressionWrapper(F('defcode').bitand(4), output_field=BooleanField())
    )
    form.fields['klijent'].queryset = klijenti

    return render(request, 'dokument_form.html', {
        'form': form,
        'formset': formset,
        'tip': tip,
        'title': 'Izmena dokumenta',
        'klijenti': klijenti.order_by('ime'),
        "edit_mode": True,
    })

@login_required
def dokument_delete(request, pk):
    document = get_object_or_404(Dokumenti, pk=pk)

    if request.method == "POST":
        dok_name = f"{document.get_dok_tip_display()} #{document.dok_br}"
        document.delete()
    #     messages.success(request, f"Dokument <strong>{dok_name}</strong> uspešno obrisan.")
    #     return redirect("dokument_list")  # back to the documents list

    # # Optional: if someone tries GET, just redirect
    # return redirect("dokument_list")
        return JsonResponse({"success": True, "message": f"Dokument <strong>{dok_name}</strong> uspešno obrisan."})
        
    return JsonResponse({"success": False, "message": "Nevažeći zahtev."}, status=400)

@login_required
def dokument_list(request): #def dokument_list(request, doc_type=None):
    # Make a mutable copy of GET parameters
    params = request.GET.copy()

    # Default doc_type = IZF
    if not params.get('doc_type'):
        params['doc_type'] = 'IZF'

    # Filters
    doc_type = params.get("doc_type")
    client_id = params.get("client")
    date_from = params.get("date_from")
    date_to = params.get("date_to")
    status_fak = params.get("status_fak")
    status_SEF = params.get("status_SEF")

    # Default dates: Jan 1 current year → today
    today = date.today()
    default_date_from = date(today.year, 1, 1).strftime("%d.%m.%Y")
    default_date_to = today.strftime("%d.%m.%Y")

    # Base queryset
    docs = Dokumenti.objects.all().select_related("klijent")

    # Apply filters
    if doc_type:
        docs = docs.filter(dok_tip=doc_type)
    if client_id:
        docs = docs.filter(klijent_id=client_id)
    # Handle date format DD.MM.YYYY from your datepicker
    if date_from:
        try:
            df = datetime.strptime(date_from, "%d.%m.%Y").date()
            docs = docs.filter(dok_datum__gte=df)
        except ValueError:
            pass

    if date_to:
        try:
            dt = datetime.strptime(date_to, "%d.%m.%Y").date()
            docs = docs.filter(dok_datum__lte=dt)
        except ValueError:
            pass
    if status_fak:
        docs = docs.filter(status_fak=status_fak)
    if status_SEF:
        docs = docs.filter(status_SEF=status_SEF)

    # Calculate total per document
    for d in docs:
        d.total = float(d.iznos_P or 0) + float(d.iznos_U or 0)

    context = {
        "docs": docs,
        "doc_types": Dokumenti.TIPOVI_DOK,
        "clients": Klijenti.objects.all(),
        "statuses": Dokumenti.FAK_STATUS,
        "sef_statuses": Dokumenti.SEF_STATUS,
        "filters": {
            "doc_type": doc_type,
            "client": client_id,
            "date_from": date_from,
            "date_to": date_to,
            "fak_status": status_fak,
            "sef_status": status_SEF,
        },
        "default_date_from": default_date_from,
        "default_date_to": default_date_to,
    }
    return render(request, 'dokument_list.html', context)

@login_required
def dokument_details(request, pk):
    try:
        dok = Dokumenti.objects.select_related("klijent").get(pk=pk)
    except Dokumenti.DoesNotExist:
        return JsonResponse({"error": "Dokument nije pronađen."}, status=404)
    
    # Render small HTML snippet for connected docs
    connected_html = render_to_string("partials/connected_docs.html", {"doc": dok}, request=request)

    # Get all document items
    items = DokumentStavke.objects.filter(dokument=dok).values("naziv", "kolicina", "cena", "iznos_stavke")

    data = {
        "tip": dok.get_dok_tip_display(),
        "broj": dok.dok_br,
        "datum": dok.dok_datum.strftime("%d.%m.%Y") if dok.dok_datum else "",
        "klijent": dok.klijent.ime if dok.klijent else "",
        "dok_status": dok.get_status_fak_display() if hasattr(dok, "get_status_fak_display") else "",
        "sef_status": dok.get_status_SEF_display() if hasattr(dok, "get_status_SEF_display") else "",
        "iznos_P": float(dok.iznos_P or 0),
        "iznos_U": float(dok.iznos_U or 0),
        "connected_html": connected_html,
        "items": list(items),
    }
    
    return JsonResponse(data)
    
@require_GET
@login_required
def klijent_info(request, pk):
    """Return JSON with address, PIB, MBR for given client_id"""
    try:
        klijent = get_object_or_404(Klijenti, pk=pk)
        data = {
            "adresa": klijent.adresa or "",
            "mesto": str(klijent.mesto) or "",
            "pib": klijent.pib or "",
            "mbr": klijent.mbr or ""
        }
    except Klijenti.DoesNotExist:
        data = {}
    return JsonResponse(data)
    
@csrf_exempt
def sef_ulazne(request):
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    # --- Signature check ---
    if not verify_hookrelay_signature(request):
        return JsonResponse({"error": "invalid signature"}, status=401)

    # --- Parse JSON ---
    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "invalid json"}, status=400)

    # Process webhook payload
    data = json.loads(request.body)
    # ... your logic here ...

    print("ULAZNE WEBHOOK:", payload)
    return JsonResponse({"status": "ok"})

@csrf_exempt
def sef_izlazne(request):
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    # --- Signature check ---
    if not verify_hookrelay_signature(request):
        return JsonResponse({"error": "invalid signature"}, status=401)

    try:
        payload = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "invalid json"}, status=400)

    data = json.loads(request.body)
    # ... your logic here ...

    print("IZLAZNE WEBHOOK:", payload)
    return JsonResponse({"status": "ok"})