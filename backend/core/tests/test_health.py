# backend/core/tests/test_health.py
import pytest
from django.db import connection

from core.tasks import ping


@pytest.mark.django_db
def test_health(client):
    r = client.get("/api/health")
    assert r.status_code == 200 and r.json() == {"status": "ok"}

@pytest.mark.django_db
def test_pgvector_installed():
    with connection.cursor() as cur:
        cur.execute("SELECT 1 FROM pg_extension WHERE extname='vector'")
        assert cur.fetchone() == (1,)

def test_celery_ping():
    assert ping() == "pong"