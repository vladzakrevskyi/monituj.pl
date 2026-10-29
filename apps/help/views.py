from django.http import Http404, JsonResponse
from django.shortcuts import render
from django.urls import NoReverseMatch, reverse
from django.views.decorators.http import require_GET

from apps.common import seo
from apps.help import articles, search
from apps.help.templatetags.help_text import help_plain

INDEX_LABEL = "Centrum pomocy"
LIVE_RESULTS = 5

# Added to descriptions too short to fill a search result.
HELP_FILLER = "Instrukcja krok po kroku w Centrum pomocy Monituj."


def _crumbs(*trail):
    return seo.breadcrumbs([(INDEX_LABEL, reverse("help:index")), *trail])


@require_GET
def index(request):
    groups = [
        {"category": category, "articles": articles.in_category(category.slug)}
        for category in articles.CATEGORIES
    ]
    return render(
        request,
        "help/index.html",
        {
            "groups": [g for g in groups if g["category"].audience == "sender"],
            "recipient": next(
                g for g in groups if g["category"].audience == "recipient"
            ),
            "popular": articles.popular(),
        },
    )


@require_GET
def category(request, slug):
    current = articles.CATEGORY_BY_SLUG.get(slug)
    if current is None:
        raise Http404
    return render(
        request,
        "help/category.html",
        {
            "category": current,
            "articles": articles.in_category(slug),
            "categories": articles.CATEGORIES,
            "seo": seo.build(
                request,
                f"{current.title} w Centrum pomocy",
                seo.fit_description(current.description, HELP_FILLER),
                jsonld=[seo.graph(_crumbs((current.title, request.path)))],
            ),
        },
    )


def _panel_link(article):
    if not article.panel:
        return None
    name, label = article.panel
    try:
        return {"url": reverse(name), "label": label}
    except NoReverseMatch:
        return None


@require_GET
def article(request, slug):
    current = articles.BY_SLUG.get(slug)
    if current is None:
        raise Http404
    category = articles.CATEGORY_BY_SLUG[current.category]
    category_url = reverse("help:category", args=[category.slug])
    return render(
        request,
        "help/article.html",
        {
            "article": current,
            "category": category,
            "siblings": articles.in_category(category.slug),
            "related": [articles.BY_SLUG[s] for s in current.related],
            "panel": _panel_link(current),
            "seo": seo.build(
                request,
                current.title,
                seo.fit_description(help_plain(current.summary), HELP_FILLER),
                og_type="article",
                jsonld=[
                    seo.graph(
                        _crumbs(
                            (category.title, category_url),
                            (current.title, request.path),
                        )
                    )
                ],
            ),
        },
    )


@require_GET
def search_view(request):
    query = request.GET.get("q", "").strip()[:200]
    found = search.search(query) if query else []
    if request.GET.get("format") == "json":
        # Under the box: the best few; Enter shows them all.
        found = found[:LIVE_RESULTS]
        return JsonResponse(
            {
                "results": [
                    {
                        "title": a.title,
                        "summary": help_plain(a.summary),
                        "category": articles.CATEGORY_BY_SLUG[a.category].title,
                        "url": reverse("help:article", args=[a.slug]),
                    }
                    for a in found
                ]
            }
        )
    return render(
        request,
        "help/search.html",
        {
            "query": query,
            "results": [
                {"article": a, "category": articles.CATEGORY_BY_SLUG[a.category]}
                for a in found
            ],
            "popular": articles.popular(),
            # Results pages are not for search engines.
            "seo": seo.build(
                request,
                "Szukaj w pomocy",
                "Wyniki wyszukiwania w Centrum pomocy Monituj.",
                indexable=False,
                public=True,
            ),
        },
    )
