from django import template

register = template.Library()

@register.filter
def format_sr(value):
    """Formatira broj u stilu: 1.234,56"""
    try:
        return f"{float(value):,.2f}".replace(",", "X").replace(".", ",").replace("X", ".")
    except (ValueError, TypeError):
        return value
    
def smart_float(value):
    """Remove decimals if .00, otherwise show up to 2 decimals."""
    try:
        value = float(value)
        if value.is_integer():
            return f"{int(value)}"
        else:
            return f"{value:.2f}".rstrip('0').rstrip('.')
    except (TypeError, ValueError):
        return value