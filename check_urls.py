import os
import django
import requests
from django.urls import get_resolver, URLPattern, URLResolver

# ----------------------------
# Configure Django settings
# ----------------------------
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "gtw.settings")  
django.setup()

# ----------------------------
# Collect all URL patterns
# ----------------------------
def collect_urls(resolver, prefix=""):
    urls = []
    for pattern in resolver.url_patterns:
        if isinstance(pattern, URLPattern):
            urls.append(prefix + str(pattern.pattern))
        elif isinstance(pattern, URLResolver):
            nested_prefix = prefix + str(pattern.pattern)
            urls.extend(collect_urls(pattern, nested_prefix))
    return urls

urls = collect_urls(get_resolver())

# ----------------------------
# Test URLs
# ----------------------------
base_url = "http://127.0.0.1:8000"

for path in urls:
    # Ensure leading slash
    if not path.startswith("/"):
        path = "/" + path

    full_url = base_url + path
    try:
        r = requests.get(full_url)
        if r.status_code == 200:
            print(f"[OK]   {full_url} -> {r.status_code}")
        else:
            print(f"[WARN] {full_url} -> {r.status_code}")
    except requests.RequestException as e:
        print(f"[ERR]  {full_url} -> {e}")
