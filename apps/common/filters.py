def status_tabs(request, choices, results, active):
    """One tab per status choice, each counting the results it would show and
    linking to the current URL with only the status (and page) changed."""
    tabs = []
    for code, label in choices:
        params = request.GET.copy()
        params.pop("page", None)
        params.pop("status", None)
        if code:
            params["status"] = code
        tabs.append(
            {
                "code": code,
                "label": label,
                "count": sum(1 for r in results if not code or r.status_code == code),
                "query": params.urlencode(),
                "active": code == active,
            }
        )
    return tabs


def active_filter_count(request, keys, defaults=None):
    defaults = defaults or {}
    return sum(
        1
        for key in keys
        if request.GET.get(key) and request.GET.get(key) != defaults.get(key)
    )


def query_without_page(request):
    params = request.GET.copy()
    params.pop("page", None)
    return params.urlencode()
