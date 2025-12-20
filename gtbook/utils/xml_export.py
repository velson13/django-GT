from django.conf import settings
from django.utils.timezone import localdate
import xml.etree.ElementTree as ET
from decimal import Decimal
from django.utils.safestring import mark_safe


# UBL namespaces
NSMAP = {
    "cec": "urn:oasis:names:specification:ubl:schema:xsd:CommonExtensionComponents-2",
    "cac": "urn:oasis:names:specification:ubl:schema:xsd:CommonAggregateComponents-2",
    "cbc": "urn:oasis:names:specification:ubl:schema:xsd:CommonBasicComponents-2",
    "xsi": "http://www.w3.org/2001/XMLSchema-instance",
    "xsd": "http://www.w3.org/2001/XMLSchema",
    "sbt": "http://mfin.gov.rs/srbdt/srbdtext",
}
DEFAULT_NS = "urn:oasis:names:specification:ubl:schema:xsd:Invoice-2"

def fmt_number(value):
    try:
        # Convert to Decimal for safety
        v = Decimal(value)

        if v == v.to_integral():
            return str(int(v))        # remove decimals
        else:
            return f"{v.normalize()}" # remove trailing zeros, keep decimals
    except Exception:
        return str(value)


def _reg_ns():
    for p, uri in NSMAP.items():
        ET.register_namespace("" if p is None else p, uri)

_reg_ns()


def generate_invoice_xml(faktura):
    """
    Generiše UBL 2.1 XML za izlaznu fakturu (IZF).
    """
    SUP = settings.COMPANY
    total = faktura.iznos_P + faktura.iznos_U

    # Root element
    invoice = ET.Element(
        "Invoice",
        {
            "xmlns:cec": NSMAP["cec"],
            "xmlns:xsi": NSMAP["xsi"],
            "xmlns:xsd": NSMAP["xsd"],
            "xmlns:sbt": NSMAP["sbt"],
            "xmlns": DEFAULT_NS,
        },
    )

    # --- BASIC METADATA ---
    ET.SubElement(invoice, "{%s}CustomizationID" % NSMAP['cbc']).text = \
        "urn:cen.eu:en16931:2017#compliant#urn:mfin.gov.rs:srbdt:2022"

    ET.SubElement(invoice, "{%s}ID" % NSMAP['cbc']).text = faktura.dok_br
    ET.SubElement(invoice, "{%s}IssueDate" % NSMAP['cbc']).text = faktura.dok_datum.isoformat()
    ET.SubElement(invoice, "{%s}DueDate" % NSMAP['cbc']).text = faktura.val_datum.isoformat() if faktura.val_datum else ""
    ET.SubElement(invoice, "{%s}InvoiceTypeCode" % NSMAP['cbc']).text = "380"
    ET.SubElement(invoice, "{%s}Note" % NSMAP['cbc']).text = faktura.napomena or ""
    ET.SubElement(invoice, "{%s}DocumentCurrencyCode" % NSMAP['cbc']).text = faktura.valuta

    # --- DISPATCH NOTES (OTPs) ---
    for otp in faktura.otpremnice.all():
        ref = ET.SubElement(invoice, "{%s}DespatchDocumentReference" % NSMAP['cac'])
        ET.SubElement(ref, "{%s}ID" % NSMAP['cbc']).text = otp.dok_br

    # =============================
    # SUPPLIER (FROM SETTINGS)
    # =============================
    asp = ET.SubElement(invoice, "{%s}AccountingSupplierParty" % NSMAP['cac'])
    p = ET.SubElement(asp, "{%s}Party" % NSMAP['cac'])

    ET.SubElement(p, "{%s}EndpointID" % NSMAP['cbc'], {"schemeID": "9948"}).text = SUP["VAT_NUMBER"]

    # Name
    pn = ET.SubElement(p, "{%s}PartyName" % NSMAP['cac'])
    ET.SubElement(pn, "{%s}Name" % NSMAP['cbc']).text = SUP["COMPANY_NAME"]

    # Address
    addr = ET.SubElement(p, "{%s}PostalAddress" % NSMAP['cac'])
    ET.SubElement(addr, "{%s}StreetName" % NSMAP['cbc']).text = SUP["ADDRESS"]
    ET.SubElement(addr, "{%s}CityName" % NSMAP['cbc']).text = SUP["CITY"]
    ctry = ET.SubElement(addr, "{%s}Country" % NSMAP['cac'])
    ET.SubElement(ctry, "{%s}IdentificationCode" % NSMAP['cbc']).text = "RS"

    # Tax
    ts = ET.SubElement(p, "{%s}PartyTaxScheme" % NSMAP['cac'])
    ET.SubElement(ts, "{%s}CompanyID" % NSMAP['cbc']).text = "RS" + SUP["VAT_NUMBER"]
    taxsch = ET.SubElement(ts, "{%s}TaxScheme" % NSMAP['cac'])
    ET.SubElement(taxsch, "{%s}ID" % NSMAP['cbc']).text = "VAT"

    # Legal entity
    ple = ET.SubElement(p, "{%s}PartyLegalEntity" % NSMAP['cac'])
    ET.SubElement(ple, "{%s}RegistrationName" % NSMAP['cbc']).text = SUP["COMPANY_NAME"]
    ET.SubElement(ple, "{%s}CompanyID" % NSMAP['cbc']).text = SUP["COMPANY_ID"]

    # Contact
    ct = ET.SubElement(p, "{%s}Contact" % NSMAP['cac'])
    ET.SubElement(ct, "{%s}ElectronicMail" % NSMAP['cbc']).text = SUP["EMAIL"]


    # =============================
    # CUSTOMER (FROM DATABASE)
    # =============================
    k = faktura.klijent

    acp = ET.SubElement(invoice, "{%s}AccountingCustomerParty" % NSMAP['cac'])
    p2 = ET.SubElement(acp, "{%s}Party" % NSMAP['cac'])

    ET.SubElement(p2, "{%s}EndpointID" % NSMAP['cbc'], {"schemeID": "9948"}).text = k.pib

    pn2 = ET.SubElement(p2, "{%s}PartyName" % NSMAP['cac'])
    ET.SubElement(pn2, "{%s}Name" % NSMAP['cbc']).text = k.ime

    addr2 = ET.SubElement(p2, "{%s}PostalAddress" % NSMAP['cac'])
    ET.SubElement(addr2, "{%s}StreetName" % NSMAP['cbc']).text = k.adresa
    ET.SubElement(addr2, "{%s}CityName" % NSMAP['cbc']).text = k.mesto.grad if hasattr(k.mesto, "grad") else str(k.mesto)
    ctry2 = ET.SubElement(addr2, "{%s}Country" % NSMAP['cac'])
    ET.SubElement(ctry2, "{%s}IdentificationCode" % NSMAP['cbc']).text = "RS"

    ts2 = ET.SubElement(p2, "{%s}PartyTaxScheme" % NSMAP['cac'])
    ET.SubElement(ts2, "{%s}CompanyID" % NSMAP['cbc']).text = "RS" + k.pib
    tsc2 = ET.SubElement(ts2, "{%s}TaxScheme" % NSMAP['cac'])
    ET.SubElement(tsc2, "{%s}ID" % NSMAP['cbc']).text = "VAT"

    ple2 = ET.SubElement(p2, "{%s}PartyLegalEntity" % NSMAP['cac'])
    ET.SubElement(ple2, "{%s}RegistrationName" % NSMAP['cbc']).text = k.ime
    ET.SubElement(ple2, "{%s}CompanyID" % NSMAP['cbc']).text = k.mbr or ""

    ct2 = ET.SubElement(p2, "{%s}Contact" % NSMAP['cac'])
    ET.SubElement(ct2, "{%s}ElectronicMail" % NSMAP['cbc']).text = k.email or ""


    # =============================
    # DELIVERY (prm_datum)
    # =============================
    dlv = ET.SubElement(invoice, "{%s}Delivery" % NSMAP['cac'])
    ET.SubElement(dlv, "{%s}ActualDeliveryDate" % NSMAP['cbc']).text = faktura.prm_datum.isoformat()


    # =============================
    # PAYMENT
    # =============================
    pm = ET.SubElement(invoice, "{%s}PaymentMeans" % NSMAP['cac'])
    ET.SubElement(pm, "{%s}PaymentMeansCode" % NSMAP['cbc']).text = "30"
    ET.SubElement(pm, "{%s}PaymentID" % NSMAP['cbc']).text = faktura.dok_br
    pfa = ET.SubElement(pm, "{%s}PayeeFinancialAccount" % NSMAP['cac'])
    ET.SubElement(pfa, "{%s}ID" % NSMAP['cbc']).text = SUP["BANK_ACCOUNT"]


    # =============================
    # TAX SUMMARY
    # =============================
    tt = ET.SubElement(invoice, "{%s}TaxTotal" % NSMAP['cac'])
    ET.SubElement(tt, "{%s}TaxAmount" % NSMAP['cbc'], {"currencyID": faktura.valuta}).text = "0"

    st = ET.SubElement(tt, "{%s}TaxSubtotal" % NSMAP['cac'])
    ET.SubElement(st, "{%s}TaxableAmount" % NSMAP['cbc'], {"currencyID": faktura.valuta}).text = fmt_number(total)
    ET.SubElement(st, "{%s}TaxAmount" % NSMAP['cbc'], {"currencyID": faktura.valuta}).text = "0"

    cat = ET.SubElement(st, "{%s}TaxCategory" % NSMAP['cac'])
    ET.SubElement(cat, "{%s}ID" % NSMAP['cbc']).text = "SS"
    ET.SubElement(cat, "{%s}Percent" % NSMAP['cbc']).text = "0"
    ET.SubElement(cat, "{%s}TaxExemptionReasonCode" % NSMAP['cbc']).text = "PDV-RS-33"
    ts3 = ET.SubElement(cat, "{%s}TaxScheme" % NSMAP['cac'])
    ET.SubElement(ts3, "{%s}ID" % NSMAP['cbc']).text = "VAT"


    # =============================
    # MONETARY TOTALS
    # =============================
    lmt = ET.SubElement(invoice, "{%s}LegalMonetaryTotal" % NSMAP['cac'])
    ET.SubElement(lmt, "{%s}LineExtensionAmount" % NSMAP['cbc'], {"currencyID": faktura.valuta}).text = fmt_number(total)
    ET.SubElement(lmt, "{%s}TaxExclusiveAmount" % NSMAP['cbc'], {"currencyID": faktura.valuta}).text = fmt_number(total)
    ET.SubElement(lmt, "{%s}TaxInclusiveAmount" % NSMAP['cbc'], {"currencyID": faktura.valuta}).text = fmt_number(total)
    ET.SubElement(lmt, "{%s}AllowanceTotalAmount" % NSMAP['cbc'], {"currencyID": faktura.valuta}).text = "0"
    ET.SubElement(lmt, "{%s}PrepaidAmount" % NSMAP['cbc'], {"currencyID": faktura.valuta}).text = "0"
    ET.SubElement(lmt, "{%s}PayableRoundingAmount" % NSMAP['cbc'], {"currencyID": faktura.valuta}).text = "0"
    ET.SubElement(lmt, "{%s}PayableAmount" % NSMAP['cbc'], {"currencyID": faktura.valuta}).text = fmt_number(total)

    # =============================
    # INVOICE LINES
    # =============================
    for i, s in enumerate(faktura.stavke_izf.all(), start=1):
        il = ET.SubElement(invoice, "{%s}InvoiceLine" % NSMAP['cac'])
        ET.SubElement(il, "{%s}ID" % NSMAP['cbc']).text = str(i)
        ET.SubElement(il, "{%s}InvoicedQuantity" % NSMAP['cbc'], {"unitCode": s.jed_mere}).text = fmt_number(s.kolicina)
        ET.SubElement(il, "{%s}LineExtensionAmount" % NSMAP['cbc'], {"currencyID": faktura.valuta}).text = fmt_number(s.iznos_stavke)

        item = ET.SubElement(il, "{%s}Item" % NSMAP['cac'])
        ET.SubElement(item, "{%s}Name" % NSMAP['cbc']).text = s.naziv or ""

        tax = ET.SubElement(item, "{%s}ClassifiedTaxCategory" % NSMAP['cac'])
        ET.SubElement(tax, "{%s}ID" % NSMAP['cbc']).text = "SS"
        ET.SubElement(tax, "{%s}Percent" % NSMAP['cbc']).text = "0"
        ts4 = ET.SubElement(tax, "{%s}TaxScheme" % NSMAP['cac'])
        ET.SubElement(ts4, "{%s}ID" % NSMAP['cbc']).text = "VAT"

        price = ET.SubElement(il, "{%s}Price" % NSMAP['cac'])
        ET.SubElement(price, "{%s}PriceAmount" % NSMAP['cbc'],
                      {"currencyID": faktura.valuta}).text = fmt_number(s.cena)

    # Return pretty XML
    return ET.tostring(invoice, encoding="utf-8", xml_declaration=True).decode()