from apps.demo.models import is_demo_user


def demo(request):
    user = getattr(request, "user", None)
    if not is_demo_user(user):
        return {}

    from apps.demo.services import DemoService

    showcase = DemoService.showcase_request(user)
    return {
        "demo_account": user.demo_account,
        "demo_showcase_url": f"/d/{showcase.public_token}/" if showcase else "",
    }
