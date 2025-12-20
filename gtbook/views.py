import base64
from calendar import monthrange
from pathlib import Path
import json, logging, traceback, requests
from django.apps import apps
from django.contrib.auth.decorators import login_required
from django.contrib import messages
from django.forms import inlineformset_factory
from django.shortcuts import render, redirect, get_object_or_404
from django.urls import reverse
from gtbook.templatetags.slovima import iznos_slovima
from gtbook.utils.cron import process_pending_webhooks
from gtbook.utils.sef_status import get_sef_subscription_status
from gtbook.utils.services import attach_otpremnice_to_faktura
from .models import Klijenti, Dokumenti, FakturaStavka, OtpremnicaStavka, UlaznaFakturaStavka, DEF_OPT, WebhookEvent, WebhookLog
from .forms import ClientForm, DokumentForm, DokumentStavkeForm
from django.utils.timezone import now, localdate, timedelta, make_aware, datetime as dt
from django.db.models.functions import TruncMonth
from django.db.models import Q, Count, F, ExpressionWrapper, BooleanField, Sum
from django.db import IntegrityError, transaction
from datetime import date, datetime, timezone
from django.conf import settings
from django.http import JsonResponse, Http404, HttpResponse
from django.template.loader import render_to_string
from django.views.decorators.http import require_GET, require_POST
from django.views.decorators.csrf import csrf_exempt
from .utils.api_calls import get_company_accounts, parse_company_accounts, check_pib_in_sef, sef_send_storno
from .utils.utils import next_dok_number, filter_klijenti_by_tip_sqlite, format_qty
from .utils.xml_export import generate_invoice_xml
from .utils.pdf import render_pdf_to_response
import pdfkit


def upload_invoice(request, pk):
    faktura = Dokumenti.objects.get(pk=pk)
    xml = generate_invoice_xml(faktura)

    # -----------------------------------------------------------------------------
    url = f"https://{settings.SEF}.mfin.gov.rs/api/publicApi/sales-invoice/ubl"
    params = {
        "requestId": f"IZF{faktura.dok_br}",
        "sendToCir": "No",
        "executeValidation": "false",
    }
    headers = {
        "accept": "text/plain",
        "ApiKey": settings.SEF_API_KEY,
        "Content-Type": "application/xml",
    }

    # Upload XML directly (filestream)
    response = requests.post(url, params=params, headers=headers, data=xml)

    if response.status_code != 200:
        return JsonResponse({
            "status": response.status_code,
            "error": response.text,
        }, status=400)

 # Parse JSON
    try:
        data = response.json()
    except Exception:
        return JsonResponse({
            "status": response.status_code,
            "error": "Invalid JSON returned by API",
            "raw": response.text
        }, status=400)

    # Extract values safely
    faktura.invoiceId = data.get("InvoiceId")
    faktura.purchaseInvoiceId = data.get("PurchaseInvoiceId")
    faktura.salesInvoiceId = data.get("SalesInvoiceId")
    faktura.status_dok = True

    faktura.save()

    # Return JSON to front-end
    return JsonResponse({
        "status": "ok",
        "saved": {
            "invoice_id": faktura.invoiceId,
            "purchase_invoice_id": faktura.purchaseInvoiceId,
            "sales_invoice_id": faktura.salesInvoiceId,
        }
    })
    # ------------------------------------------------------------------------------
    # response = HttpResponse(xml, content_type="application/xml")
    # response["Content-Disposition"] = f'attachment; filename="{faktura.dok_br}.xml"'
    # return response

@require_POST
def dokument_storno_view(request, pk):
    """Django view to handle POST request from modal button"""
    doc = get_object_or_404(Dokumenti, pk=pk)

    try:
        storno_doc = dokument_storno(doc)  # call your helper
        messages.success(
            request,
            f"Storno dokument {storno_doc.dok_br} je uspešno kreiran."
        )
    except Exception as e:
        messages.error(request, str(e))

    return redirect("dokument_details", pk=doc.pk)

@transaction.atomic
def dokument_storno(original: Dokumenti) -> Dokumenti:

    # --- Validation ---
    if original.is_storno:
        raise ValueError("Nije moguće stornirati storno dokument.")

    if original.dok_tip != 'IZF':
        raise ValueError("Samo izlazna faktura može biti stornirana.")

    if Dokumenti.objects.filter(storno_of=original).exists():
        raise ValueError("Ova faktura je već stornirana.")
    
    # --- 1️⃣ UNLINK ALL DELIVERY NOTES (OTP) ---
    # assumes: OTP model has faktura = ForeignKey(Dokumenti, related_name="otpremnice")
    original.otpremnice.update(faktura=None)

    # --- 2️⃣ UPDATE ORIGINAL INVOICE STATUS ---
    original.status_fak = "STO"
    original.save(update_fields=["status_fak"])

    # --- Create storno document ---
    storno = Dokumenti.objects.create(
        klijent=original.klijent,
        dok_tip=original.dok_tip,          # IZF stays IZF
        efaktura=original.efaktura,
        dok_br=f"ST-{original.dok_br}",
        dok_datum=date.today(),
        val_datum=None,
        prm_datum=original.prm_datum,
        valuta=original.valuta,

        iznos_P=-original.iznos_P,
        iznos_U=-original.iznos_U,

        status_SEF='STO',                  # already defined in choices
        status_fak='STO',
        status_dok=True,

        napomena=f"STORNO dokument za fakturu {original.dok_br}",

        is_storno=True,
        storno_of=original,
    )

    # --- Copy & negate invoice items ---
    for stavka in original.stavke_izf.all():
        FakturaStavka.objects.create(
            faktura=storno,
            naziv=stavka.naziv,
            tip_prometa=stavka.tip_prometa,
            kolicina=-stavka.kolicina,
            cena=stavka.cena,
            jed_mere=stavka.jed_mere,
        )
    # --- SEND TO SEF ---
    response = sef_send_storno(
        invoice_id=original.salesInvoiceId,
        storno_number=storno.dok_br,
        comment=storno.napomena or "Pogrešni podaci na fakturi",
    )

    if not response.ok:
        raise RuntimeError(
            f"Storniranje na SEF-u nije uspelo: {response.status_code} {response.text}"
        )
    
    return storno

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
    total_invoices = Dokumenti.objects.filter(dok_tip='IZF').count()
    total_webhooks = WebhookEvent.objects.filter(processed=False).count()
    # total_jobs = Job.objects.count() if 'Job' in globals() else 0

    # Last 5 records
    recent_clients = Klijenti.objects.all().order_by('-id')[:5]
    recent_invoices = Dokumenti.objects.filter(dok_tip='IZF').order_by('-id')[:5]
    recent_webhooks = WebhookLog.objects.order_by('-timestamp')[:10]
    # recent_jobs = Job.objects.all().order_by('-id')[:5] if 'Job' in globals() else []

    # Monthly data for charts (last 12 months)
    # from datetime import timedelta
    # from django.utils.timezone import make_aware, datetime as dt

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

        invoices_in_month = Dokumenti.objects.filter(
            dok_tip='IZF',
            id__isnull=False  # placeholder
        ).count()  # update with filter by date field

        client_counts.append(clients_in_month)
        invoice_counts.append(invoices_in_month)

        # Placeholder: empty lists for invoices and jobs
        # recent_invoices = []
        # recent_webhooks = []

    context = {
        'total_clients': total_clients,
        'total_invoices': total_invoices,
        'total_webhooks': total_webhooks,
        'recent_clients': recent_clients,
        'recent_invoices': recent_invoices,
        'recent_webhooks': recent_webhooks,
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
def dokument_create_empty(request, tip):
    today = now().strftime("%d.%m.%Y")
    next_number = next_dok_number(tip)

    # Common initial data
    initial_data = {
        "dok_tip": tip,
        "dok_datum": today,
        "prm_datum": today,
        "dok_br": next_number,
    }

    # Filter clients
    klijenti = filter_klijenti_by_tip_sqlite(tip).annotate(
        sef_flag=ExpressionWrapper(F('defcode').bitand(4), output_field=BooleanField())
    )

    if request.method == "POST":
        # Bind only the main form — NOT THE FORMSET
        form = DokumentForm(request.POST, request.FILES, initial=initial_data)
        form.fields["klijent"].queryset = klijenti

        if form.is_valid():
            dok = form.save(commit=False)
            dok.dok_tip = tip
            dok.dok_br = next_dok_number(tip)

            # Auto val_datum
            dok.val_datum = dok.prm_datum + timedelta(days=30) if dok.prm_datum else None
            dok.save()

            messages.success(
                request,
                f"{dict(Dokumenti.TIPOVI_DOK).get(tip, tip)} #{dok.dok_br} kreirana. Dodaj stavke!"
            )

            # 🔥 Redirect to the EDIT view where formset lives
            return redirect('dokument_edit', pk=dok.pk)#, tip=tip)
    else:
        # GET request → unbound form
        form = DokumentForm(initial=initial_data)
        form.fields["klijent"].queryset = klijenti

    # # Render empty edit page with EMPTY formset
    # empty_formset = DokumentStavkeForm(queryset=FakturaStavka.objects.none())
    # context = {
    #     "form": form,
    #     "formset": empty_formset,
    #     "tip": tip,
    #     "title": f"Nova {dict(Dokumenti.TIPOVI_DOK).get(tip, tip)} (blanko)",
    #     "klijenti": klijenti.order_by("ime"),
    #     "today": today,
    #     "next_number": next_number,
    #     "mode": "create_empty",
    # }

    # return render(request, "dokument_edit.html", context)

@login_required
def dokument_create(request, tip):
    # Choose correct ItemModel and related names for this tip
    if tip == "IZF":
        ItemModel = FakturaStavka
        related_name = "stavke_izf"
        fk_name = "faktura"
    elif tip == "OTP":
        ItemModel = OtpremnicaStavka
        related_name = "stavke_otp"
        fk_name = "otpremnica"
    elif tip == "ULF":
        ItemModel = UlaznaFakturaStavka
        related_name = "stavke_ulf"
        fk_name = "ulazna_faktura"
    else:
        messages.error(request, "Unknown document type")
        return redirect("dokument_list")

    # Build a form class for this item model (keeps your DokumentStavkeForm widgets/validation)
    # StavkaForm = get_stavka_form(tip)

    # Create a FormSet class for this tip. For create we want one empty row by default.
    FormSetClass = inlineformset_factory(
        parent_model=Dokumenti,
        model=ItemModel,
        form=DokumentStavkeForm,
        fk_name=fk_name,
        fields=["tip_prometa", "naziv", "kolicina", "jed_mere", "cena"],
        extra=1,   # one empty row for create
        can_delete=True,
    )

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
    
        form = DokumentForm(data, request.FILES, initial={"dok_tip": tip})
        # Validate formset without instance first
        formset = FormSetClass(request.POST, instance=None)
        print("POST KEYS:", list(request.POST.keys()))
        print("FORMSET VALID:", formset.is_valid())
        print("FORM ERRORS:", formset.errors)

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

        # If valid, create document instance (but items will be saved after header exists)
        dok = form.save(commit=False)
        dok.dok_tip = tip

        # Check that there are items (ignore blank rows) — formset must be valid too
        if form.is_valid() and formset.is_valid():
            valid_items = [
                fs for fs in formset
                if fs.cleaned_data and not fs.cleaned_data.get("DELETE", False)
            ]
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

        # Now bind formset to the saved dokument and persist items
        formset.instance = dok
        if formset.is_valid():
            for form in formset:
                print(
                    form.cleaned_data.get('kolicina'),
                    type(form.cleaned_data.get('kolicina'))
                )
            formset.save()

        # --- Sum and update totals --- (use correct related_name)
        iznos_P = iznos_U = 0
        for item in getattr(dok, related_name).all():
            if item.tip_prometa == "P":
                iznos_P += item.cena * item.kolicina
            elif item.tip_prometa == "U":
                iznos_U += item.cena * item.kolicina

        dok.iznos_P = iznos_P
        dok.iznos_U = iznos_U
        dok.save(update_fields=["iznos_P", "iznos_U"])

        print(request, f"{dict(Dokumenti.TIPOVI_DOK).get(tip, tip)} #{dok.dok_br} uspešno kreirana.")
        messages.success(request, f"{dict(Dokumenti.TIPOVI_DOK).get(tip, tip)} #{dok.dok_br} uspešno kreirana.")

        # ✅ Handle OTP auto-create if requested (duplicate items into real OtpremnicaStavka)
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
                        faktura=dok,  # link Otpremnica → Faktura
                    )
                    # Duplicate the items from original document (use related_name)
                    for item in getattr(dok, related_name).all():
                        # create OtpremnicaStavka objects attached to otp
                        OtpremnicaStavka.objects.create(
                            otpremnica=otp,
                            naziv=item.naziv,
                            tip_prometa=item.tip_prometa,
                            kolicina=item.kolicina,
                            cena=item.cena,
                            jed_mere=item.jed_mere,
                        )
                    print(request, f"Otpremnica #{otp.dok_br} automatski kreirana.")
                    messages.success(request, f"Otpremnica #{otp.dok_br} automatski kreirana.")
            except Exception as e:
                messages.error(
                    request,
                    f"Greška pri kreiranju otpremnice: {str(e)}. Nijedna stavka nije sačuvana.",
                )

        return redirect("dokument_list")

    else:
        # GET request
        form = DokumentForm(initial=initial_data)
        formset = FormSetClass(instance=None)  # show one empty row (extra=1)
        form.fields["klijent"].queryset = klijenti

    context = {
        "form": form,
        "formset": formset,
        "tip": tip,
        "title": f"Nova {dict(Dokumenti.TIPOVI_DOK).get(tip, tip)}",
        "klijenti": klijenti.order_by("ime"),
        "today": today,
        "next_number": initial_data.get("dok_br", ""),
        "mode": "create",
    }
    return render(request, "dokument_form.html", context)

# # Dynamic form factory for document items
# def get_stavka_form(tip):
#     from django import forms

#     if tip == "IZF":
#         model_cls = FakturaStavka
#     elif tip == "OTP":
#         model_cls = OtpremnicaStavka
#     elif tip == "ULF":
#         model_cls = UlaznaFakturaStavka
#     else:
#         raise ValueError("Unknown document type")

#     # Dynamically create the form class
#     return type(
#         f"{tip}StavkaForm",
#         (forms.ModelForm,),
#         {
#             "Meta": type(
#                 "Meta",
#                 (),
#                 {"model": model_cls, "fields": ["naziv", "tip_prometa", "kolicina", "cena", "jed_mere"]}
#             )
#         }
#     )

@login_required
def dokument_edit(request, pk):
    try:
        dok = get_object_or_404(Dokumenti, pk=pk)
    except Http404:
        messages.error(request, "Dokument nije pronađen.")
        return redirect('dokument_list')

    tip = dok.dok_tip  # preserve type

    # Choose correct ItemModel and fk_name / related_name
    if tip == "IZF":
        ItemModel = FakturaStavka
        fk_name = "faktura"
        related_name = "stavke_izf"
    elif tip == "OTP":
        ItemModel = OtpremnicaStavka
        fk_name = "otpremnica"
        related_name = "stavke_otp"
    elif tip == "ULF":
        ItemModel = UlaznaFakturaStavka
        fk_name = "ulazna_faktura"
        related_name = "stavke_ulf"
    else:
        messages.error(request, "Unknown document type")
        return redirect("dokument_list")

    # Build formset for edit
    FormSetClass = inlineformset_factory(
        parent_model=Dokumenti,
        model=ItemModel,
        form=DokumentStavkeForm,
        fk_name=fk_name,
        fields=["tip_prometa", "naziv", "kolicina", "jed_mere", "cena"],
        extra=0,
        can_delete=True,
    )

    if request.method == "POST":
        form = DokumentForm(request.POST, request.FILES, instance=dok)
        formset = FormSetClass(request.POST, instance=dok)

        if form.is_valid() and formset.is_valid():
            form.save()
            formset.save()

            # Handle attaching OTP to IZF (only relevant for IZF)
            if tip == "IZF":
                otpremnice_ids = request.POST.getlist("otpremnice")
                if otpremnice_ids:
                    attach_otpremnice_to_faktura(dok, otpremnice_ids)

            # --- Sum and update totals (use correct related_name) ---
            iznos_P = iznos_U = 0
            for item in getattr(dok, related_name).all():
                if item.tip_prometa == "P":
                    iznos_P += item.cena * item.kolicina
                elif item.tip_prometa == "U":
                    iznos_U += item.cena * item.kolicina

            dok.iznos_P = iznos_P
            dok.iznos_U = iznos_U
            dok.save(update_fields=["iznos_P", "iznos_U"])

            messages.success(
                request,
                f"{dict(Dokumenti.TIPOVI_DOK).get(tip, tip)} #{dok.dok_br} uspešno izmenjena."
            )
            
        
            # ✅ Handle OTP auto-create if requested (duplicate items into real OtpremnicaStavka)
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
                            faktura=dok,  # link Otpremnica → Faktura
                        )
                        # Duplicate the items from original document (use related_name)
                        for item in getattr(dok, related_name).all():
                            # create OtpremnicaStavka objects attached to otp
                            OtpremnicaStavka.objects.create(
                                otpremnica=otp,
                                naziv=item.naziv,
                                tip_prometa=item.tip_prometa,
                                kolicina=item.kolicina,
                                cena=item.cena,
                                jed_mere=item.jed_mere,
                            )
                        print(request, f"Otpremnica #{otp.dok_br} automatski kreirana.")
                        messages.success(request, f"Otpremnica #{otp.dok_br} automatski kreirana.")
                except Exception as e:
                    messages.error(
                        request,
                        f"Greška pri kreiranju otpremnice: {str(e)}. Nijedna stavka nije sačuvana.",
                    )

            return redirect("dokument_list")
    
    else:
        form = DokumentForm(instance=dok)
        formset = FormSetClass(instance=dok)
        linked_otps = dok.otpremnice.all() if dok.dok_tip == "IZF" else []

        for otp in linked_otps:
            otp.preview = "<br>".join(
                f"{item.naziv} – {format_qty(item.kolicina)} {item.get_jed_mere_display()} × {item.cena}"
                for item in otp.stavke_otp.all()
            )

    # Filter clients
    klijenti = filter_klijenti_by_tip_sqlite(tip).annotate(
        sef_flag=ExpressionWrapper(F('defcode').bitand(4), output_field=BooleanField())
    )
    form.fields['klijent'].queryset = klijenti

    # Filter available otpremnice (only unlinked, same client)
    available_otpremnice = Dokumenti.objects.filter(
        dok_tip='OTP',
        faktura__isnull=True,
        klijent=dok.klijent
    )

    for otp in available_otpremnice:
            otp.preview = "<br>".join(
                f"{item.naziv} – {format_qty(item.kolicina)} {item.get_jed_mere_display()} × {item.cena}"
                for item in otp.stavke_otp.all()
            )

    return render(request, 'dokument_form.html', {
        'form': form,
        'formset': formset,
        'tip': tip,
        'title': 'Izmena dokumenta',
        'klijenti': klijenti.order_by('ime'),
        "edit_mode": True,
        "available_otpremnice": available_otpremnice,
        "dokument": dok,
        'linked_otps': linked_otps,
    })

logger = logging.getLogger(__name__)

@login_required
def unlink_otp_from_izf(request, izf_id, otp_id):
    """
    Unlink OTP (otp_id) from IZF (izf_id). Also remove from the IZF any FakturaStavka
    rows that appear to originate from that OTP (match by naziv, kolicina, cena, jed_mere).
    """
    # Load documents and verify types / relation
    izf = get_object_or_404(Dokumenti, pk=izf_id, dok_tip="IZF")
    otp = get_object_or_404(Dokumenti, pk=otp_id, dok_tip="OTP")

    # Ensure OTP is actually linked to this IZF
    if otp.faktura_id != izf.id:
        messages.error(request, "Otpremnica nije bila vezana za ovu fakturu (ništa nije menjano).")
        logger.warning("Pokušano odvezivanje otpremnice %s od fakture %s ali otp.faktura=%s",
                       otp_id, izf_id, otp.faktura_id)
        return redirect("dokument_edit", pk=izf.id)

    # perform unlink + deletion atomically
    with transaction.atomic():
        # unlink
        otp.faktura = None
        otp.save(update_fields=["faktura"])

        # gather OTP items
        otp_items = OtpremnicaStavka.objects.filter(otpremnica=otp)

        # build a filter for faktura items to delete
        # match by naziv, kolicina, cena, jed_mere — this is what we used before
        deleted_count = 0
        for item in otp_items:
            qs = FakturaStavka.objects.filter(
                faktura=izf,
                naziv=item.naziv,
                kolicina=item.kolicina,
                cena=item.cena,
                jed_mere=item.jed_mere
            )
            # count removed per item (may remove multiple identical rows)
            cnt = qs.count()
            if cnt:
                qs.delete()
                deleted_count += cnt

        messages.success(request, f"Otpremnica odvojena. Uklonjeno stavki: {deleted_count}")
        logger.info("Otpremnica %s odvojena od fakture %s — uklonjeno %d stavki fakture",
                    otp_id, izf_id, deleted_count)

    return redirect("dokument_edit", pk=izf.id)

@login_required
def link_otp_to_izf(request, izf_id, otp_id):
    """
    Link OTP (otp_id) to IZF (izf_id). Also copy all OtpremnicaStavka items into
    the IZF as FakturaStavka.
    """
    izf = get_object_or_404(Dokumenti, pk=izf_id, dok_tip="IZF")
    otp = get_object_or_404(Dokumenti, pk=otp_id, dok_tip="OTP")

    # If already linked, do nothing
    if otp.faktura_id == izf.id:
        return JsonResponse({"success": False, "message": "Otpremnica je već povezana."})

    with transaction.atomic():
        # link otp → izf
        otp.faktura = izf
        otp.save(update_fields=["faktura"])

        # collect items that will be inserted into formset immediately
        otp_items = OtpremnicaStavka.objects.filter(otpremnica=otp)

        copied_count = 0
        for item in otp_items:
            # Create FakturaStavka copy
            FakturaStavka.objects.create(
                faktura=izf,
                tip_prometa=item.tip_prometa,
                naziv=item.naziv,
                kolicina=item.kolicina,
                jed_mere=item.jed_mere,
                cena=item.cena,
            )
            copied_count += 1

        messages.success(request, f"Otpremnica povezana. Kopirano stavki: {copied_count}")
        logger.info("Otpremnica %s povezana sa fakturom %s — kopirano %d stavki",
                    otp_id, izf_id, copied_count)

    return redirect("dokument_edit", pk=izf.id)

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
    dok_tip = dok.dok_tip
    # Render small HTML snippet for connected docs
    connected_html = render_to_string("partials/connected_docs.html", {"doc": dok}, request=request)

    # Get all document items
    if dok_tip == "IZF":
        items = FakturaStavka.objects.filter(faktura=dok).values("naziv", "kolicina", "cena", "iznos_stavke")
    elif dok_tip == "OTP":
        items = OtpremnicaStavka.objects.filter(otpremnica=dok).values("naziv", "kolicina", "cena", "iznos_stavke")
    elif dok_tip == "ULF":
        items = UlaznaFakturaStavka.objects.filter(ulazna_faktura=dok).values("naziv", "kolicina", "cena", "iznos_stavke")
    # else:
    # items = DokumentStavke.objects.filter(dokument=dok).values("naziv", "kolicina", "cena", "iznos_stavke")

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
        "is_storno": dok.is_storno,
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

    # parse JSON payload
    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "invalid json"}, status=400)

    # store payload or process it
    WebhookEvent.objects.create(payload=data, type="ulazne")
    return JsonResponse({"status": "ok"})

@csrf_exempt
def sef_izlazne(request):
 
    if request.method != "POST":
        return JsonResponse({"error": "POST required"}, status=405)

    try:
        data = json.loads(request.body)
    except json.JSONDecodeError:
        return JsonResponse({"error": "invalid json"}, status=400)

    # process payload or store it
    WebhookEvent.objects.create(payload=data, type="izlazne")
    return JsonResponse({"status": "ok"})

def webhook_list(request):
    status = get_sef_subscription_status()
    context = {
        "sef_status": status,
    }
    # AJAX auto-refresh returns only JSON
    if request.GET.get("ajax") == "1":
        ulazne = list(
            WebhookEvent.objects.filter(type="ulazne")
            .order_by("-received_at")
            .values("id", "received_at", "payload")
        )
        izlazne = list(
            WebhookEvent.objects.filter(type="izlazne")
            .order_by("-received_at")
            .values("id", "received_at", "payload")
        )
        return JsonResponse({"ulazne": ulazne, "izlazne": izlazne})

    return render(request, "webhooks_list.html", context)

@require_POST
def delete_webhooks(request):
    ids = request.POST.getlist("ids[]", [])
    delete_all = request.POST.get("delete_all") == "1"

    if delete_all:
        WebhookEvent.objects.all().delete()
    else:
        WebhookEvent.objects.filter(id__in=ids).delete()

    return JsonResponse({"status": "ok"})

def process_webhooks_view(request):
    process_pending_webhooks()
    return redirect("webhook_list")

def invoice_pdf(request, pk):
    invoice = Dokumenti.objects.get(pk=pk)
    return render_pdf_to_response(
        "print/invoice.html",
        {"invoice": invoice},
        filename=f"invoice_{invoice.broj}.pdf"
    )

# def kpo_report(request):
#     # Example: filter by month/year via GET params
#     year = request.GET.get("year")
#     month = request.GET.get("month")
#     invoices = Dokumenti.objects.all().order_by("datum")

#     if year:
#         invoices = invoices.filter(datum__year=year)
#     if month:
#         invoices = invoices.filter(datum__month=month)

#     totals = invoices.aggregate(
#         total_iznos_u=Sum("iznos_U"),
#         total_iznos_p=Sum("iznos_P"),
#     )

#     return render(request, "reports/kpo_report.html", {
#         "invoices": invoices,
#         "totals": totals,
#         "year": year,
#         "month": month,
#     })

def kpo_pdf(request):
    today = date.today()
    from_str = request.GET.get("fromdate")
    to_str = request.GET.get("todate")
    df = datetime.strptime(from_str, "%d.%m.%Y").date()
    dt = datetime.strptime(to_str, "%d.%m.%Y").date()

    invoices = Dokumenti.objects.filter(
        dok_datum__gte=df,
        dok_datum__lte=dt,
        dok_tip="IZF"
    ).order_by("dok_datum")

    totals = invoices.aggregate(
        total_iznos_u=Sum("iznos_U"),
        total_iznos_p=Sum("iznos_P"),
    )

    # Format dates for display
    # display_date_from = kpo_date_from.strftime("%d.%m.%Y")
    # display_date_to = kpo_date_to.strftime("%d.%m.%Y")

    # # Embed logo as base64
    # logo_path = Path(settings.BASE_DIR) / "gtbook" / "static" / "images" / "logo.png"
    # with open(logo_path, "rb") as f:
    #     logo_base64 = base64.b64encode(f.read()).decode("utf-8")

    return render_pdf_to_response(
        "KPO", "reports/kpo_pdf.html",
        {
            "invoices": invoices,
            "totals": totals,
            "datefrom": df,#.strftime("%d.%m.%Y"),
            "dateto": dt,#.strftime("%d.%m.%Y"),
            "now": today,
        },
        filename="KPO.pdf",
        # filename=f"KPO-{display_date_from}-{display_date_to}.pdf"
    )

# def kpo_editor(request):
#     # Encode logo as base64
#     logo_path = Path(settings.BASE_DIR) / "gtbook" / "static" / "images" / "logo.png"
#     with open(logo_path, "rb") as f:
#         logo_base64 = base64.b64encode(f.read()).decode("utf-8")

#     return render(request, "reports/kpo_editor_ready.html", {"logo_base64": logo_base64})

def otpremnica_pdf(request, doc_id):
    doc = get_object_or_404(Dokumenti, pk=doc_id)
    stavke = OtpremnicaStavka.objects.filter(otpremnica_id=doc_id).order_by("id")
    total = stavke.aggregate(total=Sum('iznos_stavke'))['total'] or 0
    
    return render_pdf_to_response(
        "OTP", "reports/otpremnica_pdf.html",
        {
            "doc": doc,
            "klijent": doc.klijent,
            "stavke": stavke,
            "total": total,
        },
        filename=f"Otpremnica {doc.dok_br}.pdf",
    )

def faktura_pdf(request, doc_id):
    doc = get_object_or_404(Dokumenti, pk=doc_id)
    stavke = FakturaStavka.objects.filter(faktura_id=doc_id).order_by("id")
    total = stavke.aggregate(total=Sum('iznos_stavke'))['total'] or 0
    slovima = iznos_slovima(float(total))
    
    linked_otps = doc.otpremnice.all() if doc.dok_tip == "IZF" else []
    if linked_otps:
        for otp in linked_otps:
            otp = ", ".join(otp.dok_br for otp in doc.otpremnice.all())
    else:
        otp = ""

    return render_pdf_to_response(
        "IZF", "reports/faktura_pdf.html",
        {
            "doc": doc,
            "klijent": doc.klijent,
            "stavke": stavke,
            "total": total,
            "slovima": slovima,
            "otp": otp,
        },
        filename=f"Faktura {doc.dok_br}.pdf",
    )