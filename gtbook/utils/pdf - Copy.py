from django.utils import timezone
import os
import shutil
import pdfkit
from django.http import HttpResponse
from django.template.loader import get_template
from django.conf import settings

def find_wkhtmltopdf(explicit_path=None):
    """
    Try to find a usable wkhtmltopdf binary.
    - If explicit_path is provided and exists -> return it.
    - Else try shutil.which on PATH.
    - Else try some common install locations.
    - Return None if not found.
    """
    # 1) explicit path from settings
    if explicit_path:
        explicit_path = os.path.expanduser(explicit_path)
        if os.path.isfile(explicit_path) and os.access(explicit_path, os.X_OK):
            return explicit_path

    # 2) try PATH
    which_path = shutil.which("wkhtmltopdf")
    if which_path:
        return which_path

    # 3) common locations (Linux, Synology, Windows)
    candidates = [
        "/usr/local/bin/wkhtmltopdf",
        "/usr/bin/wkhtmltopdf",
        "/opt/bin/wkhtmltopdf",
        "/volume1/@appstore/wkhtmltopdf/bin/wkhtmltopdf",  # common Synology location
        r"C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe",
        r"C:\Program Files (x86)\wkhtmltopdf\bin\wkhtmltopdf.exe",
    ]
    for p in candidates:
        p = os.path.expanduser(p)
        if os.path.isfile(p) and os.access(p, os.X_OK):
            return p

    return None


def render_pdf_to_response(template_path, context, filename="document.pdf", options=None):
    """
    Render a Django template to PDF using pdfkit/wkhtmltopdf with robust binary discovery.
    Returns Django HttpResponse with content-type application/pdf.

    If wkhtmltopdf cannot be found, raises RuntimeError with helpful instructions.
    """
    # Render HTML
    template = get_template(template_path)
    html = template.render(context)

    # Determine wkhtmltopdf binary path
    explicit = getattr(settings, "WKHTMLTOPDF_CMD", None)
    wk_path = find_wkhtmltopdf(explicit)

    if not wk_path:
        raise RuntimeError("wkhtmltopdf not found.")

    # Configure pdfkit
    try:
        config = pdfkit.configuration(wkhtmltopdf=wk_path)
    except Exception as e:
        raise RuntimeError(
            f"pdfkit.configuration() failed with wkhtmltopdf='{wk_path}'.\n"
            f"Error: {e}\n\n"
            "Make sure the binary is executable and compatible with your platform."
        )

    # Footer text
    print_datetime = timezone.localtime().strftime("%d.%m.%Y. %H:%M")
    divider_line = "______________________________________________________________________________"  # Unicode line for hairline effect
    # Options (can be overridden)
    wk_options = {
        "page-size": "A4",
        "encoding": "UTF-8",
        "margin-top": "12mm",
        "margin-right": "10mm",
        "margin-left": "10mm",
        "margin-bottom": "12mm",  # leave space for footer
        "footer-left": f"Datum i vreme štampe: {print_datetime}",
        "footer-center": f"{divider_line}\n\nObrazac KPO  : : :  SZR Grafotip  : : :  PIB: 105645069",
        "footer-right": "Strana [page] od [topage]",
        "footer-font-size": "6",
        "footer-spacing": "3",  # mm above footer
    }
    if options:
        wk_options.update(options)

    try:
        pdf = pdfkit.from_string(html, False, configuration=config, options=wk_options)
    except OSError as e:
        # Common wkhtmltopdf runtime errors (permission, incompatible binary, missing libs)
        raise RuntimeError(
            "wkhtmltopdf runtime error while generating PDF. This often means the binary is "
            "incompatible with the OS or missing required libraries.\n"
            f"Binary used: {wk_path}\nError: {e}\n\n"
            "Check that the binary runs on the host by executing:\n"
            f"  '{wk_path} --version'\n"
            "If that fails, install a matching wkhtmltopdf static binary for your platform."
        )
    except Exception as e:
        raise RuntimeError(f"Unexpected error while running wkhtmltopdf: {e}")

    # Build response
    response = HttpResponse(pdf, content_type="application/pdf")
    response["Content-Disposition"] = f'inline; filename="{filename}"'
    return response
