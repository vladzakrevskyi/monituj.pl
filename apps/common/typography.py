"""Polish typography: one-letter words (and a few short prepositions and
conjunctions) must not be left hanging at the end of a line - the so-called
"sierotki". Gluing them to the following word with a non-breaking space
fixes that everywhere at once: templates, database content and emails."""

import re

from apps.common.link_titles import add_link_titles

NBSP = " "

_SHORT = (
    r"[aiouwzAIOUWZ]|[Dd]o|[Nn]a|[Pp]o|[Oo]d|[Zz]a|[Zz]e|[Ww]e|[Kk]u|[Żż]e|[Ii]ż"
    r"|[Bb]o|\d+"
)
# A short word preceded by whitespace, a line start or an opening quote or
# bracket, followed by ordinary whitespace and then more text. NBSP counts as
# whitespace before the word, so chains like "a w domu" are glued fully.
_ORPHAN = re.compile(rf"(?<![^\s(„\"'«])({_SHORT})[ \t\r\n]+(?=\S)")
_ORPHAN_AT_END = re.compile(rf"(?<![^\s(„\"'«])({_SHORT})[ \t\r\n]+$")
# "Tak – jedną" - a dash must not start a new line either.
_DASH = re.compile(r"(?<=\S)[ \t\r\n]+(?=[–—-](?:\s|$))")

_TOKEN = re.compile(
    # <title> too: search results show it as plain text, spaces included.
    r"<(script|style|textarea|pre|code|title)\b.*?</\1\s*>|<!--.*?-->|<[^>]*>",
    re.S | re.I,
)
_INLINE_TAG = re.compile(r"</?(a|abbr|b|em|i|mark|small|span|strong|time|u)\b", re.I)


def fix_orphans_text(text):
    text = _ORPHAN.sub(rf"\1{NBSP}", text)
    return _DASH.sub(NBSP, text)


def fix_orphans(html):
    """Applies fix_orphans_text to the text between tags only - attributes,
    scripts, styles and form contents stay untouched."""
    out = []
    position = 0
    for match in _TOKEN.finditer(html):
        text = fix_orphans_text(html[position : match.start()])
        if _INLINE_TAG.match(match.group(0)):
            # "w <strong>kilka</strong>": the next word starts inside the tag.
            text = _ORPHAN_AT_END.sub(rf"\1{NBSP}", text)
        out.append(text)
        out.append(match.group(0))
        position = match.end()
    out.append(fix_orphans_text(html[position:]))
    return "".join(out)


class OrphansMiddleware:
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        if (
            response.streaming
            or response.has_header("Content-Encoding")
            or not response.get("Content-Type", "").startswith("text/html")
            or request.path.startswith("/admin/")
        ):
            return response
        charset = response.charset or "utf-8"
        html = add_link_titles(fix_orphans(response.content.decode(charset)))
        response.content = html.encode(charset)
        if response.has_header("Content-Length"):
            response["Content-Length"] = str(len(response.content))
        return response
