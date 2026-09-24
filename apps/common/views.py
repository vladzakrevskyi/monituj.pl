from apps.common.responses import success_response


def health_check(request):
    return success_response({"status": "ok"})
