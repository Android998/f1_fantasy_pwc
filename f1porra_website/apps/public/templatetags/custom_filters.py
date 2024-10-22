# myapp/templatetags/custom_filters.py
from django import template

register = template.Library()

@register.filter(name="dict_lookup")
def dict_lookup(dictionary, key):
    return dictionary.get(key, 'default_value')  # Adjust 'default_value' as needed