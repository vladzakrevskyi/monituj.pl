from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as DjangoUserAdmin

from apps.accounts import two_factor
from apps.accounts.models import AccountToken, User


@admin.register(User)
class UserAdmin(DjangoUserAdmin):
    ordering = ["email"]
    list_display = [
        "email",
        "is_staff",
        "is_active",
        "email_verified_at",
        "has_two_factor",
    ]
    search_fields = ["email"]
    actions = ["disable_two_factor"]
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        (
            "Permissions",
            {
                "fields": (
                    "is_active",
                    "is_staff",
                    "is_superuser",
                    "groups",
                    "user_permissions",
                )
            },
        ),
        (
            "Important dates",
            {"fields": ("last_login", "date_joined", "email_verified_at")},
        ),
    )
    add_fieldsets = ((None, {"fields": ("email", "password1", "password2")}),)

    @admin.display(boolean=True, description="2FA")
    def has_two_factor(self, obj):
        return hasattr(obj, "two_factor")

    def get_queryset(self, request):
        return super().get_queryset(request).select_related("two_factor")

    @admin.action(description="Wyłącz weryfikację dwuetapową (utracony telefon)")
    def disable_two_factor(self, request, queryset):
        """Only after checking that the person asking owns the account - e.g.
        a reply from the account's email address. The owner gets an email."""
        done = 0
        for user in queryset:
            if two_factor.is_enabled(user):
                two_factor.admin_disable(user, request=request)
                done += 1
        self.message_user(
            request,
            f"Wyłączono weryfikację dwuetapową na {done} kontach.",
            messages.SUCCESS,
        )


@admin.register(AccountToken)
class AccountTokenAdmin(admin.ModelAdmin):
    list_display = ["user", "purpose", "expires_at", "used_at", "created_at"]
    list_filter = ["purpose"]
    readonly_fields = ["token_hash"]
