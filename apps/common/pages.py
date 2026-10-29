from django.http import Http404
from django.shortcuts import render
from django.urls import reverse

from apps.common import seo
from apps.common.content import FAQ, FAQ_CATEGORIES, SEGMENTS
from apps.documents.validation import MAX_UPLOAD_SIZE


def _page(template, extra=None):
    def view(request):
        context = {"faq": FAQ, "faq_categories": FAQ_CATEGORIES, "segments": SEGMENTS}
        context.update(extra() if extra else {})
        return render(request, template, context)

    return view


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


def _pricing_context():
    from apps.billing import plans
    from apps.billing.views import plan_cards

    return {
        "cards": plan_cards(),
        "trial_days": plans.TRIAL_DAYS,
        "trial_plan": plans.TRIAL_PLAN,
        "free_plan": plans.FREE,
        "plan_guide": [plans.START, plans.BIURO, plans.PRO],
        "vat_rate": plans.vat_rate(),
        "calculator_plans": _calculator_plans(plans),
    }


def _calculator_plans(plans):
    """For the time calculator (static/js/calculator.js): the cheapest plan
    that holds a request to every client at once."""
    return [
        {"name": plan.name, "limit": plan.active_requests, "net": plan.monthly // 100}
        for plan in (plans.FREE, *plans.PAID_PLANS)
    ]


def _landing_context():
    from apps.billing import plans

    return {
        "price_from": min(plan.monthly for plan in plans.PAID_PLANS) // 100,
        "trial_days": plans.TRIAL_DAYS,
        "trial_plan": plans.TRIAL_PLAN,
        "calculator_plans": _calculator_plans(plans),
    }


landing = _page("pages/landing.html", _landing_context)
comparison = _page("pages/comparison.html")
calculator = _page("pages/calculator.html", _landing_context)
pricing = _page("pages/pricing.html", _pricing_context)
faq = _page("pages/faq.html")
demo = _page("pages/demo.html")
guide = _page("pages/guide.html")
outside_ksef = _page("pages/outside_ksef.html")
client_questions = _page("pages/client_questions.html")


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
            "templates": _segment_templates(slug),
            "seo": seo.segment_seo(request, current),
        },
    )


def _segment_templates(slug):
    from apps.requests import template_library

    return template_library.for_segment(slug)


def templates_library(request):
    """The ready request templates, by industry - public and indexed."""
    from apps.requests import template_library

    groups = [
        {"segment": segment, "templates": template_library.for_segment(segment["slug"])}
        for segment in SEGMENTS
    ]
    return render(request, "pages/templates_library.html", {"groups": groups})


def template_page(request, slug):
    """One ready template: the list with what each document means, and a way
    to use it - in the panel, after signing up, or without an account."""
    from apps.requests import template_guides, template_library

    template = template_library.get(slug)
    if template is None:
        raise Http404
    guide = template_guides.get(slug)
    segment = next(s for s in SEGMENTS if s["slug"] == template.segment)
    if request.user.is_authenticated:
        use_url = f"{reverse('requests:create')}?szablon={slug}"
    else:
        use_url = f"{reverse('accounts:register')}?szablon={slug}"
    return render(
        request,
        "pages/template_page.html",
        {
            "template": template,
            "guide": guide,
            "segment": segment,
            "related": [
                t
                for t in template_library.for_segment(segment["slug"])
                if t.slug != slug
            ],
            "use_url": use_url,
            "guest_url": f"{reverse('public:guest-request-create')}?szablon={slug}",
            "deadline_text": _deadline_text(template.deadline),
            "seo": seo.template_seo(request, template, segment, guide),
        },
    )


def _deadline_text(choice):
    if choice in ("7", "14"):
        return f"{choice} dni od wysłania"
    if choice == "day10":
        return "do 10. dnia miesiąca"
    return "bez terminu"
