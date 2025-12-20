from django import template
from django.contrib.staticfiles import finders
import base64 as pybase64  # rename to avoid conflicts

register = template.Library()

@register.filter
def base64(file_path):
    """
    Converts a static file to a base64 string
    Usage in template: {{ 'images/grafotip-logo3.png'|base64 }}
    """
    full_path = finders.find(file_path)
    if not full_path:
        return ''
    with open(full_path, 'rb') as f:
        encoded = pybase64.b64encode(f.read()).decode()
    return encoded
