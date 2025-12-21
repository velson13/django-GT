import tempfile
from django.core.files.base import ContentFile
from .faktura_xml_extract import extract_full_invoice
from .faktura_xml_extract import map_extracted_invoice_to_model
from .api_calls import download_purchase_invoice_xml
from django.conf import settings
from ..models import Dokumenti

def get_or_create_invoice_from_sef(invoice_id, invoice_type):
    """
    invoice_type: 'ulazne' | 'izlazne'
    """

    lookup = (
        {"purchaseInvoiceId": invoice_id}
        if invoice_type == "ulazne"
        else {"salesInvoiceId": invoice_id}
    )

    doc = Dokumenti.objects.filter(**lookup).first()
    if doc:
        return doc, False  # already exists

    # 1️⃣ download XML
    xml_bytes = download_purchase_invoice_xml(invoice_id)

    # 2️⃣ save XML to temp file for extractor
    with tempfile.NamedTemporaryFile(delete=False, suffix=".xml") as tmp:
        tmp.write(xml_bytes)
        tmp_path = tmp.name

    # 3️⃣ extract data
    extracted = extract_full_invoice(tmp_path, output_pdf=None)

    # 4️⃣ map to model fields
    mapped_fields = map_extracted_invoice_to_model(extracted)

    # 5️⃣ create document
    doc = Dokumenti.objects.create(
        **mapped_fields,
        **lookup,
        file=ContentFile(xml_bytes, name=f"{invoice_id}.xml"),
    )

    return doc, True

def create_purchase_invoice_from_sef(pid, status, comment):
    # 1️⃣ Download XML
    xml_bytes = download_purchase_invoice_xml(pid)

    # 2️⃣ Write temp XML for extractor
    with tempfile.NamedTemporaryFile(delete=False, suffix=".xml") as tmp:
        tmp.write(xml_bytes)
        xml_path = tmp.name

    # 3️⃣ Extract data
    extracted = extract_full_invoice(xml_path, output_pdf=None)

    # 4️⃣ Map to model fields
    fields = map_extracted_invoice_to_model(extracted)

    # 5️⃣ Create document
    doc = Dokumenti.objects.create(
        purchaseInvoiceId=pid,
        status_SEF=status,
        comment_SEF=comment,
        **fields,
    )

    # 6️⃣ Attach XML
    doc.file.save(
        f"purchase_{pid}.xml",
        ContentFile(xml_bytes),
        save=True,
    )

    return doc