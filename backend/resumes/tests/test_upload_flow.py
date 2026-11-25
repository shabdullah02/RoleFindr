import pytest
from django.contrib.auth import get_user_model
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from rest_framework.test import APIClient

from resumes import views
from resumes.models import ResumeUpload
from resumes.parsers import ParsedResume, ResumeParseError
from resumes.services import run_parse, save_master


@pytest.fixture(autouse=True)
def media(settings, tmp_path):
    settings.MEDIA_ROOT = str(tmp_path)


def make_user(email):
    return get_user_model().objects.create_user(email=email, password="pw-12345-xyz")


def make_upload(user):
    return ResumeUpload.objects.create(user=user, file=ContentFile(b"%PDF-1.4 x", name="cv.pdf"),
                                       original_filename="cv.pdf")


class FakeParser:
    def __init__(self, result=None, exc=None):
        self.result, self.exc = result, exc

    def parse(self, filename, content):
        if self.exc:
            raise self.exc
        return self.result


def client_for(user):
    c = APIClient()
    c.force_authenticate(user)
    return c


@pytest.mark.django_db
def test_upload_queues_parse_after_commit(monkeypatch, django_capture_on_commit_callbacks):
    calls = []
    monkeypatch.setattr(views.parse_resume_task, "delay", lambda i: calls.append(i))
    c = client_for(make_user("a@example.com"))
    with django_capture_on_commit_callbacks(execute=True):
        r = c.post("/api/resume/upload", {"file": SimpleUploadedFile("cv.pdf", b"%PDF-1.4 x")}, format="multipart")
    assert r.status_code == 202 and calls == [r.json()["id"]]


@pytest.mark.django_db
def test_upload_rejects_wrong_content():
    c = client_for(make_user("a@example.com"))
    r = c.post("/api/resume/upload", {"file": SimpleUploadedFile("cv.pdf", b"hello")}, format="multipart")
    assert r.status_code == 400


@pytest.mark.django_db
def test_upload_hourly_cap(monkeypatch):
    monkeypatch.setattr(views.parse_resume_task, "delay", lambda i: None)
    u = make_user("a@example.com")
    for _ in range(views.MAX_UPLOADS_PER_HOUR):
        make_upload(u)
    r = client_for(u).post("/api/resume/upload", {"file": SimpleUploadedFile("cv.pdf", b"%PDF-1.4 x")}, format="multipart")
    assert r.status_code == 429


@pytest.mark.django_db
def test_run_parse_success():
    up = make_upload(make_user("a@example.com"))
    run_parse(up.id, parser=FakeParser(ParsedResume("t", {"basics": {"name": "Jane"}})))
    up.refresh_from_db()
    assert up.status == "parsed" and up.parsed_json["basics"]["name"] == "Jane"


@pytest.mark.django_db
def test_run_parse_permanent_failure_does_not_raise():
    up = make_upload(make_user("a@example.com"))
    run_parse(up.id, parser=FakeParser(exc=ResumeParseError("HTTP 401")))
    up.refresh_from_db()
    assert up.status == "failed" and "401" in up.error


@pytest.mark.django_db
def test_run_parse_retryable_failure_raises_for_celery():
    up = make_upload(make_user("a@example.com"))
    with pytest.raises(ResumeParseError):
        run_parse(up.id, parser=FakeParser(exc=ResumeParseError("timeout", retryable=True)))
    up.refresh_from_db()
    assert up.status == "failed"


@pytest.mark.django_db
def test_master_versions_increment_and_get_returns_latest():
    u = make_user("a@example.com")
    save_master(u, {"basics": {"name": "v1"}})
    c = client_for(u)
    r = c.put("/api/resume/master", {"json_resume": {"basics": {"name": "v2"}}}, format="json")
    assert r.status_code == 201 and r.json()["version"] == 2
    assert c.get("/api/resume/master").json()["json_resume"]["basics"]["name"] == "v2"


@pytest.mark.django_db
def test_other_users_cannot_read_an_upload():
    up = make_upload(make_user("a@example.com"))
    r = client_for(make_user("b@example.com")).get(f"/api/resume/upload/{up.id}")
    assert r.status_code == 404
