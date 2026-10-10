from django import template

register = template.Library()


@register.filter
def num(value, decimals=0):
    """1234.5 -> '1,235'. Missing values show a dash."""
    try:
        return f'{float(value):,.{int(decimals)}f}'
    except (TypeError, ValueError):
        return '–'


@register.filter
def tonnes(value, decimals=1):
    """Kilograms to tonnes, with thousands separators."""
    try:
        return f'{float(value) / 1000:,.{int(decimals)}f}'
    except (TypeError, ValueError):
        return '–'


@register.filter
def get_item(mapping, key):
    try:
        return mapping.get(key)
    except AttributeError:
        return None


@register.filter
def percent_of(value, maximum):
    """Width for a progress bar: value as a percentage of maximum (0 to 100)."""
    try:
        return max(0, min(100, round(100 * float(value) / float(maximum))))
    except (TypeError, ValueError, ZeroDivisionError):
        return 0


@register.filter
def confidence_class(score):
    try:
        score = float(score)
    except (TypeError, ValueError):
        return 'badge-muted'
    if score >= 75:
        return 'badge-ok'
    if score >= 50:
        return 'badge-info'
    return 'badge-warn'


@register.filter
def verification_class(status):
    return {'verified': 'badge-ok', 'pending': 'badge-muted', 'rejected': 'badge-danger'}.get(status, 'badge-muted')
