from django.shortcuts import render

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
