from .api_calls import attach_xml_if_missing
# from .get_SEF_invoice import create_purchase_invoice_from_sef
from ..models import Dokumenti, WebhookLog

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
    from django.db import transaction
    from gtbook.utils.faktura_xml_extract import extract_full_invoice

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
                xml_path = download_invoice_xml(sef_id, invoice_type)
                extracted = extract_full_invoice(xml_path, None)
                if not extracted:
                    raise Exception("No extracted data available")

            doc, _ = get_or_create_invoice(sef_id, invoice_type, extracted)

            if xml_path:
                attach_xml_if_missing(doc, xml_path)

            if extracted:
                insert_items(doc, invoice_type, extracted)

            doc.status_SEF = status
            doc.comment_SEF = comment
            doc.save(update_fields=["status_SEF", "comment_SEF"])

            webhook_log(webhook, doc)

    return True, None
    
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

def resolve_client(company_id, name):
    from gtbook.models import Klijenti

    UNKNOWN_PIB = "00000000"

    if company_id:
        client = Klijenti.objects.filter(pib=company_id).first()
        if client:
            return client

        return Klijenti.objects.create(
            pib=company_id,
            naziv=name or "SEF klijent",
            auto_created=True,
        )

    return Klijenti.objects.get(pib=UNKNOWN_PIB)

def get_sef_invoice_id(event, webhook_type):
    if webhook_type == "ulazne":
        return str(event["PurchaseInvoiceId"]), "ulazne"
    else:
        return str(event["SalesInvoiceId"]), "izlazne"

def download_invoice_xml(sef_id, invoice_type):
    import requests
    from pathlib import Path
    from django.conf import settings

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
    from gtbook.models import Dokumenti

    # lookup = (
    #     {"purchaseInvoiceId": sef_id}
    #     if invoice_type == "purchase"
    #     else {"salesInvoiceId": sef_id}
    # )

    # doc = Dokumenti.objects.filter(**lookup).first()
    # if doc:
    #     return doc, False

    supplier = extracted["invoice"].get("Supplier", {})
    customer = extracted["invoice"].get("Customer", {})
    partner = supplier if invoice_type == "ulazne" else customer

    client = resolve_client(
        partner.get("CompanyID"),
        partner.get("Name"),
    )

    doc = Dokumenti.objects.create(
        client=client,
        broj=extracted["invoice"].get("ID"),
        datum=extracted["invoice"].get("IssueDate"),
        iznos=extracted["invoice"].get("PayableAmount"),
        purchaseInvoiceId=sef_id if invoice_type == "ulazne" else None,
        salesInvoiceId=sef_id if invoice_type == "izlazne" else None,
    )

    return doc, True

from django.core.files import File

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
    from gtbook.models import FakturaStavka, UlaznaFakturaStavka
    from decimal import Decimal

    # Determine model + FK field
    if invoice_type == "sales":
        if doc.stavke_izf.exists():
            return
        Model = FakturaStavka
        fk_field = "faktura"
        tip_prometa = "U"

    elif invoice_type == "purchase":
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