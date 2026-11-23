# backend/accounts/admin.py
from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    ordering = ("email",)
    list_display = ("email", "plan", "mfa_enabled", "is_staff", "created_at")
    fieldsets = (
        (None, {"fields": ("email", "password")}),
        ("Plan", {"fields": ("plan", "mfa_enabled")}),
        ("Permissions", {"fields": ("is_active", "is_staff", "is_superuser", "groups", "user_permissions")}),
    )
    add_fieldsets = ((None, {"classes": ("wide",), "fields": ("email", "password1", "password2")}),)
    search_fields = ("email",)