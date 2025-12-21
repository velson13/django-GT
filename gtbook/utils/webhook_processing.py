from .api_calls import (download_sales_invoice_xml,
                        attach_xml_if_missing)
from .get_SEF_invoice import create_purchase_invoice_from_sef
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
            comment = event.get("Comment")
            # ───────────────────────────────
            # PURCHASE INVOICES (ULAZNE)
            # ───────────────────────────────
            if webhook.type == "ulazne":
                pid = event.get("PurchaseInvoiceId")
                if not pid:
                    raise ValueError("Purchase webhook missing PurchaseInvoiceId")

                pid = str(pid)

                doc = Dokumenti.objects.filter(purchaseInvoiceId=pid).first()

                if not doc:
                    doc = create_purchase_invoice_from_sef(
                        pid=pid,
                        status=status,
                        comment=comment,
                    )
                else:
                    doc.status_SEF = status
                    doc.comment_SEF = comment
                    doc.save(update_fields=["status_SEF", "comment_SEF"])

            # ───────────────────────────────
            # SALES INVOICES (IZLAZNE)
            # ───────────────────────────────
            else:
                sid = str(event.get("SalesInvoiceId"))

                doc = Dokumenti.objects.get(salesInvoiceId=sid)

                # always update status/comment
                doc.status_SEF = status
                doc.comment_SEF = comment
                doc.save(update_fields=["status_SEF", "comment_SEF"])

                # ⬇️ FIRST-TIME XML ATTACH ONLY
                if not doc.file:
                    xml = download_sales_invoice_xml(sid)
                    attach_xml_if_missing(
                        doc,
                        xml,
                        f"sales_{sid}.xml",
                    )

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
        message=f"Novi status: {status}; Komentar: {comment}"
    )

    WebhookLog.trim()
