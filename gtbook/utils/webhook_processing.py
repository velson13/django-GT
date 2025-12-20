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
    events = webhook.payload if isinstance(webhook.payload, list) else [webhook.payload]

    try:
        for event in events:
            status_raw = event.get("NewInvoiceStatus")
            status = SEF_STATUS_MAP.get(status_raw, status_raw)

            # Determine document by type
            if webhook.type == "ulazne":
                pid = str(event.get("PurchaseInvoiceId"))
                doc = Dokumenti.objects.get(purchaseInvoiceId=pid)

            else:  # izlazne
                sid = str(event.get("SalesInvoiceId"))
                doc = Dokumenti.objects.get(salesInvoiceId=sid)

            # Apply status change
            doc.status_SEF = status
            doc.save(update_fields=["status_SEF"])

            # Log the change
            webhook_log(webhook, doc)

        return True, None

    except Exception as e:
        return False, str(e)



def webhook_log(webhook, doc):
    doc_number = getattr(doc, "dok_br", None)
    client_name = None
    if doc.klijent_id:
        client = doc.klijent
        client_name = getattr(client, "ime", None)

    WebhookLog.objects.create(
        webhook_id=webhook.id,
        doc_number=doc_number,
        client_name=client_name,
        message=f"Webhook processed: {doc_number} / {client_name}"
    )

    WebhookLog.trim()
