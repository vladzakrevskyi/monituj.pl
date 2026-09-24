from django.contrib import admin

from apps.clients.models import Client


@admin.register(Client)
class ClientAdmin(admin.ModelAdmin):
    list_display = ["name", "email", "owner", "created_at"]
    search_fields = ["name", "email"]
    list_filter = ["owner"]
