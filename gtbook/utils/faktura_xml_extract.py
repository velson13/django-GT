import base64
import xml.etree.ElementTree as ET

myxml_file = "250114.xml"
# myxml_file = "base64.xml"
# myoutput_pdf = "invoice.pdf"

def extract_full_invoice(xml_file, output_pdf):
    tree = ET.parse(xml_file)
    root = tree.getroot()

    # Namespaces
    ns = {
        "env": "urn:eFaktura:MinFinrs:envelop:schema",
        "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
        "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2"
    }

    data = {"header": {}, "invoice": {}, "lines": []}

    # 1️⃣ DocumentHeader
    header = root.find(".//env:DocumentHeader", ns)
    if header is not None:
        for child in header:
            tag = child.tag.split("}", 1)[-1]  # remove namespace
            if tag == "DocumentPdf":
                pdf_b64 = (child.text or "").strip()
                if pdf_b64:
                    pdf_bytes = base64.b64decode(pdf_b64)
                    with open(output_pdf, "wb") as f:
                        f.write(pdf_bytes)
                    data["header"]["DocumentPdfSavedAs"] = output_pdf
            else:
                data["header"][tag] = (child.text or "").strip()

    # 2️⃣ Invoice header and supplier/customer
    invoice = root.find(".//{urn:oasis:names:specification:ubl:schema:xsd:Invoice-2}Invoice")
    if invoice is not None:
        # Header fields
        for field in ["CustomizationID", "ID", "IssueDate", "DueDate", 
                      "InvoiceTypeCode", "Note", "DocumentCurrencyCode"]:
            node = invoice.find(f"cbc:{field}", ns)
            if node is not None:
                data["invoice"][field] = node.text.strip()

        # Supplier
        supplier = invoice.find("cac:AccountingSupplierParty/cac:Party", ns)
        if supplier is not None:
            supplier_data = {}
            name_node = supplier.find("cac:PartyName/cbc:Name", ns)
            if name_node is not None: supplier_data["Name"] = name_node.text.strip()
            email_node = supplier.find("cac:Contact/cbc:ElectronicMail", ns)
            if email_node is not None: supplier_data["Email"] = email_node.text.strip()
            company_id = supplier.find("cac:PartyTaxScheme/cbc:CompanyID", ns)
            if company_id is not None: supplier_data["CompanyID"] = company_id.text.strip()
            data["invoice"]["Supplier"] = supplier_data

        # Customer
        customer = invoice.find("cac:AccountingCustomerParty/cac:Party", ns)
        if customer is not None:
            customer_data = {}
            name_node = customer.find("cac:PartyName/cbc:Name", ns)
            if name_node is not None: customer_data["Name"] = name_node.text.strip()
            email_node = customer.find("cac:Contact/cbc:ElectronicMail", ns)
            if email_node is not None: customer_data["Email"] = email_node.text.strip()
            company_id = customer.find("cac:PartyTaxScheme/cbc:CompanyID", ns)
            if company_id is not None: customer_data["CompanyID"] = company_id.text.strip()
            data["invoice"]["Customer"] = customer_data

        # Delivery
        delivery = invoice.find("cac:Delivery/cbc:ActualDeliveryDate", ns)
        if delivery is not None:
            data["invoice"]["ActualDeliveryDate"] = delivery.text.strip()

        # Monetary totals
        totals = invoice.find("cac:LegalMonetaryTotal", ns)
        if totals is not None:
            for t in ["LineExtensionAmount", "TaxExclusiveAmount", "TaxInclusiveAmount", 
                      "AllowanceTotalAmount", "PrepaidAmount", "PayableRoundingAmount", "PayableAmount"]:
                node = totals.find(f"cbc:{t}", ns)
                if node is not None:
                    data["invoice"][t] = node.text.strip()

        # Invoice lines
        lines = invoice.findall("cac:InvoiceLine", ns)
        for line in lines:
            line_data = {}
            for tag in ["ID", "InvoicedQuantity", "LineExtensionAmount"]:
                node = line.find(f"cbc:{tag}", ns)
                if node is not None:
                    line_data[tag] = node.text.strip()
                    # Also store unit if available
                    if tag == "InvoicedQuantity" and "unitCode" in node.attrib:
                        line_data["UnitCode"] = node.attrib["unitCode"]
            # Item name
            item_node = line.find("cac:Item/cbc:Name", ns)
            if item_node is not None:
                line_data["ItemName"] = item_node.text.strip()
            # Price
            price_node = line.find("cac:Price/cbc:PriceAmount", ns)
            if price_node is not None:
                line_data["PriceAmount"] = price_node.text.strip()
            data["lines"].append(line_data)
            print(data)
    return data

# #######################################################################
# # Usage
# invoice_data = extract_full_invoice(myxml_file, myoutput_pdf)

# # Example: print results
# print("📑 Header Metadata:")
# for k, v in invoice_data["header"].items():
#     print(f"{k}: {v}")

# print("\n📑 Invoice Info:")
# for k, v in invoice_data["invoice"].items():
#     print(f"{k}: {v}")

# print("\n📑 Invoice Lines:")
# for line in invoice_data["lines"]:
#     print(line)

# #######################################################################

def map_extracted_invoice_to_model(data):
    inv = data["invoice"]
    hdr = data["header"]

    return {
        # generalije
        "dok_br": inv.get("ID"),
        "dok_datum": inv.get("IssueDate"),
        "val_datum": inv.get("DueDate"),
        "prm_datum": inv.get("ActualDeliveryDate"),
        "valuta": inv.get("DocumentCurrencyCode"),
        "PurchaseInvoiceId": inv.get("PurchaseInvoiceId"),
        "SalesInvoiceId": inv.get("SalesInvoiceId"),

        # supplier
        # "dobavljac_naziv": inv.get("Supplier", {}).get("Name"),
        # "dobavljac_pib": inv.get("Supplier", {}).get("CompanyID"),
        # "dobavljac_email": inv.get("Supplier", {}).get("Email"),

        # customer
        # "kupac_naziv": inv.get("Customer", {}).get("Name"),
        # "kupac_pib": inv.get("Customer", {}).get("CompanyID"),
        # "kupac_email": inv.get("Customer", {}).get("Email"),

        # amounts
        # "iznos_bez_pdv": inv.get("TaxExclusiveAmount"),
        # "iznos_sa_pdv": inv.get("TaxInclusiveAmount"),
        "iznos_P": inv.get("PayableAmount"),

        # SEF metadata
        # "sef_customization_id": inv.get("CustomizationID"),
    }
