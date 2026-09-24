import json

from django import template
from django.utils.safestring import mark_safe

register = template.Library()

# The same escapes Django's json_script uses: "<", ">" and "&" can never
# form "</script>" or an HTML entity inside the block.
_ESCAPES = {ord(">"): "\\u003E", ord("<"): "\\u003C", ord("&"): "\\u0026"}


@register.filter
def ld_json(data):
    """A schema.org block. Escaped like json_script, so text from the page
    can never close the <script> tag."""
    payload = json.dumps(data, ensure_ascii=False).translate(_ESCAPES)
    return mark_safe(f'<script type="application/ld+json">{payload}</script>')
