"""{% pagination page_obj %} - one pager for every list: first, previous,
the page numbers, next and last. The list's other query parameters
(filters, search) stay in every link.

The numbers never take more than SLOTS places, however many pages there
are: the first and last page, the current one with a neighbour on each side,
and "…" for the rest - "1 … 4 5 6 … 20". Near either end the run fills up
instead ("1 2 3 4 5 … 20"), so the pager keeps its width while you page.
On a phone the numbers give way to "4 z 20" (components.css)."""

from django import template

register = template.Library()

GAP = None
# first + gap + (neighbour, current, neighbour) + gap + last
SLOTS = 7


def page_numbers(current, last):
    """The page numbers to show, GAP marking the elided runs."""
    if last <= SLOTS:
        return list(range(1, last + 1))
    # The middle run: the current page and a neighbour on each side,
    # shifted inwards near the ends so it always has three pages.
    start = min(max(current - 1, 3), last - 4)
    end = max(min(current + 1, last - 2), 5)
    head = [1, 2] if start == 3 else [1, GAP]
    tail = [last - 1, last] if end == last - 2 else [GAP, last]
    return [*head, *range(start, end + 1), *tail]


@register.inclusion_tag("base/_pagination.html", takes_context=True)
def pagination(context, page_obj):
    request = context["request"]
    params = request.GET.copy()
    params.pop("page", None)
    base = params.urlencode()

    def url(number):
        return f"?{base}&page={number}" if base else f"?page={number}"

    number, last = page_obj.number, page_obj.paginator.num_pages
    pages = [
        {"gap": True}
        if page is GAP
        else {"number": page, "url": url(page), "current": page == number}
        for page in page_numbers(number, last)
    ]
    return {
        "number": number,
        "num_pages": last,
        "pages": pages,
        "first_url": url(1) if number > 1 else None,
        "previous_url": url(number - 1) if page_obj.has_previous() else None,
        "next_url": url(number + 1) if page_obj.has_next() else None,
        "last_url": url(last) if number < last else None,
    }
