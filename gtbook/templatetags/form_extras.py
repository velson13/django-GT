from django import template

register = template.Library()

@register.filter
def widget_class(field, base_class="form-control"):
    """
    Adds Bootstrap validation classes to form fields.
    Usage: {{ form.field|widget_class }}
    """
    css = base_class
    if field.errors:
        css += " is-invalid"
    return field.as_widget(attrs={"class": css})

@register.filter
def add_class(field, css):
    return field.as_widget(attrs={"class": css})
