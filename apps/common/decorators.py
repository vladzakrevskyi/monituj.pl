from functools import wraps

from apps.common.responses import error_response


def api_login_required(view_func):
    @wraps(view_func)
    def wrapper(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return error_response("UNAUTHORIZED", "Wymagane logowanie.", status=401)
        return view_func(request, *args, **kwargs)

    return wrapper
