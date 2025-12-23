from gtbook.models import Klijenti, Dokumenti, FakturaStavka, UlaznaFakturaStavka, WebhookLog
from django.db import transaction
from gtbook.utils.faktura_xml_extract import extract_full_invoice
import requests
from pathlib import Path
from django.conf import settings
from decimal import Decimal
from django.db.models import Max
from django.core.files import File


SEF_STATUS_MAP = {
    "Draft": "NAC",
    "New": "NOV",
    "Sending": "SLA",
    "Sent": "POS",
    "Seen": "PRE",
    "Approved": "PRI",
    "Rejected": "ODB",
    "Cancelled": "OTK",
    "Storno": "STO",
    "ReNotified": "PON",
    "Mistake": "GRE",
    "Unknown": "NEP"
}

def process_webhook(webhook):
    try:
        events = webhook.payload if isinstance(webhook.payload, list) else [webhook.payload]

        for event in events:
            sef_id, invoice_type = get_sef_invoice_id(event, webhook.type)

            status_raw = event.get("NewInvoiceStatus")
            status = SEF_STATUS_MAP.get(status_raw, status_raw)
            comment = event.get("Comment")

            with transaction.atomic():
                doc = None
                xml_path = None
                extracted = None

                lookup = (
                    {"purchaseInvoiceId": sef_id}
                    if invoice_type == "ulazne"
                    else {"salesInvoiceId": sef_id}
                )
                doc = Dokumenti.objects.filter(**lookup).first()

                if not doc or not doc.file:
                    xml_path = Path(settings.MEDIA_ROOT) / "sef_tmp" / f"{invoice_type}_{sef_id}.xml"
                    if not xml_path.exists():
                        xml_path = download_invoice_xml(sef_id, invoice_type)
                    extracted = extract_full_invoice(xml_path)
                    if not extracted:
                        raise Exception("No extracted data available")

                if not doc:
                    doc, created = get_or_create_invoice(sef_id, invoice_type, extracted)
                else:
                    created = False


                if xml_path:
                    attach_xml_if_missing(doc, xml_path)

                if extracted:
                    insert_items(doc, invoice_type, extracted)

                doc.status_SEF = status
                doc.comment_SEF = comment
                doc.save(update_fields=["status_SEF", "comment_SEF"])

                webhook_log(webhook, doc)

        return True, None
    except Exception as e:
        return False, str(e)
    
def webhook_log(webhook, doc):
    doc_number = getattr(doc, "dok_br", None)
    status = getattr(doc, "status_SEF", None)
    comment = getattr(doc, "comment_SEF", None)
    client_name = None
    
    if doc.klijent_id:
        client = doc.klijent
        client_name = getattr(client, "ime", None)

    WebhookLog.objects.create(
        webhook_id=webhook.id,
        doc_number=doc_number,
        client_name=client_name,
        message=f"Tip: {webhook.type}; Novi status: {status}; Komentar: {comment}"
    )

    WebhookLog.trim()

def get_sef_invoice_id(event, webhook_type):
    if webhook_type == "ulazne":
        return str(event["PurchaseInvoiceId"]), "ulazne"
    else:
        return str(event["SalesInvoiceId"]), "izlazne"

def download_invoice_xml(sef_id, invoice_type):
    if invoice_type == "ulazne":
        url = f"https://{settings.SEF}.mfin.gov.rs/api/publicApi/purchase-invoice/xml"
    else:
        url = f"https://{settings.SEF}.mfin.gov.rs/api/publicApi/sales-invoice/xml"

    r = requests.get(
        url,
        params={"invoiceId": sef_id},
        headers={"ApiKey": settings.SEF_API_KEY},
        timeout=30,
    )
    r.raise_for_status()

    path = Path(settings.MEDIA_ROOT) / "sef_tmp"
    path.mkdir(exist_ok=True)

    xml_path = path / f"{invoice_type}_{sef_id}.xml"
    xml_path.write_bytes(r.content)

    return xml_path

def get_or_create_invoice(sef_id, invoice_type, extracted):

    lookup = (
        {"purchaseInvoiceId": sef_id}
        if invoice_type == "ulazne"
        else {"salesInvoiceId": sef_id}
    )

    doc = Dokumenti.objects.filter(**lookup).first()
    if doc:
        return doc, False

    invoice = extracted["invoice"]

    partner = (
        invoice["Supplier"]
        if invoice_type == "ulazne"
        else invoice["Customer"]
    )

    client = get_or_create_client_from_xml({
        "pib": partner.get("CompanyID"),
        "naziv": partner.get("Name"),
        "maticni_broj": partner.get("CompanyID"),
        "adresa": partner.get("Address"),
    })

    doc = Dokumenti.objects.create(
        klijent=client,
        dok_br=invoice.get("ID"),
        datum=invoice.get("IssueDate"),
        iznos=Decimal(invoice.get("PayableAmount", "0")),
        valuta=invoice.get("DocumentCurrencyCode"),
        purchaseInvoiceId=sef_id if invoice_type == "ulazne" else None,
        salesInvoiceId=sef_id if invoice_type == "izlazne" else None,
    )

    return doc, True

def attach_xml_if_missing(doc, xml_path):
    if doc.file:
        return

    with open(xml_path, "rb") as f:
        doc.file.save(xml_path.name, File(f), save=False)

    doc.save(update_fields=["file"])

UNIT_MAP = {
    "H87": "H87",  # kom
    "HUR": "HUR",  # hour
    "KT": "KT",    # set
}

def map_unit(unit_code):
    return UNIT_MAP.get(unit_code, "H87")  # safe default

def insert_items(doc, invoice_type, extracted):

    # Determine model + FK field
    if invoice_type == "izlazne":
        if doc.stavke_izf.exists():
            return
        Model = FakturaStavka
        fk_field = "faktura"
        tip_prometa = "U"

    elif invoice_type == "ulazne":
        if doc.stavke_ulf.exists():
            return
        Model = UlaznaFakturaStavka
        fk_field = "ulazna_faktura"
        tip_prometa = "P"

    else:
        return  # safety

    items = []

    for line in extracted["lines"]:
        items.append(
            Model(
                **{
                    fk_field: doc,
                    "naziv": line.get("ItemName"),
                    "kolicina": Decimal(line.get("InvoicedQuantity", "1")),
                    "cena": Decimal(line.get("PriceAmount", "0")),
                    "jed_mere": map_unit(line.get("UnitCode")),
                    "tip_prometa": tip_prometa,
                }
            )
        )

    Model.objects.bulk_create(items)



def get_or_create_client_from_xml(client_data):
    pib = client_data["pib"]

    client = Klijenti.objects.select_for_update().filter(pib=pib).first()

    if client:
        return client

    next_id = (
        Klijenti.objects.aggregate(m=Max("id"))["m"] or 0
    ) + 1

    client = Klijenti.objects.create(
        id=next_id,
        ime=client_data["naziv"],
        pib=pib,
        mbr=client_data.get("maticni_broj"),
        adresa=client_data.get("adresa"),
        defcode=13,
    )

    return client