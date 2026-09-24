"""Every link carries a title attribute. Links that need more than their
visible text (a logo, "Otwórz", pagination) get one written in the template;
every other link gets its own text as the title here, so none is ever
missing - in pages and in emails alike."""

import re
from html import escape, unescape

# Only blocks whose content isn't markup; <code> may sit inside a link.
_PROTECTED = re.compile(r"<(script|style|textarea)\b.*?</\1\s*>", re.S | re.I)
_LINK = re.compile(r"<a\b(?P<attrs>[^>]*)>(?P<body>.*?)</a\s*>", re.S | re.I)
_HAS_TITLE = re.compile(r"\stitle\s*=", re.I)
_ARIA_LABEL = re.compile(r'\saria-label\s*=\s*"([^"]*)"', re.I)
_TAG = re.compile(r"<[^>]+>")
# Arrows and similar decoration say nothing on their own.
_DECORATION = "←→↑↓‹›«»·•"
MAX_LENGTH = 120


def _title_for(attrs, body):
    text = " ".join(unescape(_TAG.sub(" ", body)).split()).strip(_DECORATION + " ")
    if not text:
        label = _ARIA_LABEL.search(attrs)
        text = unescape(label.group(1)).strip() if label else ""
    return text[:MAX_LENGTH]


def _add(match):
    attrs, body = match.group("attrs"), match.group("body")
    if _HAS_TITLE.search(attrs):
        return match.group(0)
    title = _title_for(attrs, body)
    if not title:
        return match.group(0)
    return f'<a title="{escape(title, quote=True)}"{attrs}>{body}</a>'


def add_link_titles(html):
    parts, position = [], 0
    for block in _PROTECTED.finditer(html):
        parts.append(_LINK.sub(_add, html[position : block.start()]))
        parts.append(block.group(0))
        position = block.end()
    parts.append(_LINK.sub(_add, html[position:]))
    return "".join(parts)
