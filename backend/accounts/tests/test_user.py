# backend/accounts/tests/test_user.py
import pytest
from django.contrib.auth import get_user_model

User = get_user_model()


@pytest.mark.django_db
def test_create_user_defaults():
    u = User.objects.create_user("Ali@Example.COM", "pw12345!")
    assert u.email == "ali@example.com"
    assert u.plan == "free" and u.mfa_enabled is False
    assert u.check_password("pw12345!") and not u.is_staff


@pytest.mark.django_db
def test_superuser_flags():
    u = User.objects.create_superuser("root@example.com", "pw12345!")
    assert u.is_staff and u.is_superuser


@pytest.mark.django_db
def test_email_required():
    with pytest.raises(ValueError):
        User.objects.create_user("", "pw")