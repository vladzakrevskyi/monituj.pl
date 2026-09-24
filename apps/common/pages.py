from django.http import Http404
from django.shortcuts import render

from apps.common import seo
from apps.common.content import FAQ, FAQ_CATEGORIES, SEGMENTS
from apps.documents.validation import MAX_UPLOAD_SIZE


def _page(template, extra=None):
    def view(request):
        context = {"faq": FAQ, "faq_categories": FAQ_CATEGORIES, "segments": SEGMENTS}
        context.update(extra() if extra else {})
        return render(request, template, context)

    return view


landing = _page("pages/landing.html")
how_it_works = _page(
    "pages/how_it_works.html",
    lambda: {"max_upload_mb": MAX_UPLOAD_SIZE // (1024 * 1024)},
)
features = _page("pages/features.html")
for_whom = _page("pages/for_whom.html")
security = _page(
    "pages/security.html",
    lambda: {"max_upload_mb": MAX_UPLOAD_SIZE // (1024 * 1024)},
)
pricing = _page("pages/pricing.html")
faq = _page("pages/faq.html")
demo = _page("pages/demo.html")
guide = _page("pages/guide.html")


def segment(request, slug):
    """One industry's page - written around what people there search for."""
    current = next((s for s in SEGMENTS if s["slug"] == slug), None)
    if current is None:
        raise Http404
    others = [s for s in SEGMENTS if s["slug"] != slug]
    return render(
        request,
        "pages/segment.html",
        {
            "segment": current,
            "others": others,
            "seo": seo.segment_seo(request, current),
        },
    )
