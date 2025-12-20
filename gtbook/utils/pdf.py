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


def render_pdf_to_response(doc_type, template_path, context, filename="document.pdf", options=None):
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
        # Helpful error message
        msg = (
            "wkhtmltopdf binary was not found. Set settings.WKHTMLTOPDF_CMD to the full path "
            "or install wkhtmltopdf and ensure it's on PATH. Common locations:\n"
            " - /usr/local/bin/wkhtmltopdf\n - /usr/bin/wkhtmltopdf\n"
            " - /volume1/@appstore/wkhtmltopdf/bin/wkhtmltopdf (Synology)\n"
            r" - C:\Program Files\wkhtmltopdf\bin\wkhtmltopdf.exe (Windows)\n\n"
            "To test on this machine, run: `which wkhtmltopdf` or `wkhtmltopdf --version`.\n"
            f"If you set WKHTMLTOPDF_CMD in settings.py, make sure it points to an executable file.\n"
        )
        raise RuntimeError(msg)

    # Configure pdfkit
    try:
        config = pdfkit.configuration(wkhtmltopdf=wk_path)
    except Exception as e:
        raise RuntimeError(
            f"pdfkit.configuration() failed with wkhtmltopdf='{wk_path}'.\n"
            f"Error: {e}\n\n"
            "Make sure the binary is executable and compatible with your platform."
        )
    divider_line = "________________________________________________________________________________________________________________________________________________________________________________"
    if doc_type == "KPO":
        # Default options (can be overridden)
        default_options = {
            "page-size": "A4",
            "encoding": "UTF-8",
            "margin-top": "10mm",
            "margin-right": "10mm",
            "margin-left": "10mm",
            "margin-bottom": "14mm",
            "footer-left": "    Obrazac KPO",
            "footer-center": f"{divider_line}\nSZR Grafotip  : : :  PIB: 105645069",
            "footer-right": "Strana [page] od [topage]    ",
            "footer-font-size": "6",
            "footer-spacing": "3",  # mm above footer
            "footer-font-name": "Calibri",
        }
    elif doc_type in ["OTP", "IZF"]:
        default_options = {
            "page-size": "A4",
            "encoding": "UTF-8",
            "margin-top": "10mm",
            "margin-right": "10mm",
            "margin-left": "10mm",
            "margin-bottom": "14mm",
            # "footer-left": "",
            "footer-center": f"{divider_line}\nSZR Grafotip | Novi Sad, Tihomira Ostojića 42 | grafotip.ns@gmail.com | +381621540826",
            # "footer-right": "Strana [page] od [topage]    ",
            "footer-font-size": "6",
            "footer-spacing": "3",  # mm above footer
            "footer-font-name": "Calibri",
        }

    if options:
        default_options.update(options)

    try:
        pdf = pdfkit.from_string(html, False, configuration=config, options=default_options)
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
