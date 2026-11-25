# backend/jobs/tests/test_ingest_linkedin.py
import pandas as pd
import pytest

from jobs.models import Job
from jobs.services.ingest_linkedin import ingest_linkedin


def fake(rows):
    return lambda **kw: pd.DataFrame(rows)


ROW = {"job_url": "https://www.linkedin.com/jobs/view/3696158877", "job_url_direct": None,
       "title": "Python Developer", "location": "Lahore, Pakistan", "is_remote": False,
       "description": "Build things", "date_posted": None}

    
@pytest.mark.django_db
def test_ingest_dedupes_and_preserves_apply_method():
    ingest_linkedin("python", scrape=fake([ROW]))
    Job.objects.update(apply_method="easy_apply")  # set later by the extension
    res = ingest_linkedin("python", scrape=fake([ROW]))
    job = Job.objects.get()
    assert res == {"created": 0, "updated": 1}
    assert job.external_id == "3696158877" and job.apply_method == "easy_apply"


@pytest.mark.django_db
def test_missing_results_never_close_jobs():
    ingest_linkedin("python", scrape=fake([ROW]))
    ingest_linkedin("python", scrape=fake([{**ROW, "job_url": ROW["job_url"].replace("69", "70")}]))
    assert Job.objects.filter(status="open").count() == 2

def test_empty_result_raises_instead_of_silently_succeeding():
    from jobs.sources.linkedin import LinkedInBlocked
    with pytest.raises(LinkedInBlocked):
        ingest_linkedin("python", scrape=fake([]))


@pytest.mark.django_db
def test_reingest_keeps_fetched_description():
    from jobs.models import Job
    from jobs.sources.base import NormalizedJob

    def nj(desc):
        return NormalizedJob(external_id="1", title="SE", location="Karachi", remote=False,
                             url="http://x", apply_url="", description=desc, posted_at=None)

    class Src:
        def __init__(self, d):
            self.d = d

        def fetch(self, *a, **k):
            return [nj(self.d)]

    ingest_linkedin("x", source=Src("Full text"))
    ingest_linkedin("x", source=Src(""))
    assert Job.objects.get(external_id="1").description == "Full text"
