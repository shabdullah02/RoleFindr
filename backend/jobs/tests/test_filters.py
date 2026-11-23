from types import SimpleNamespace as NS

from jobs.models import Profile
from jobs.services.filters import check_job, norm


def job(**kw):
    d = {
        "title": "Software Engineer",
        "company_name": "Acme",
        "location": "Karāchi, Sindh, Pakistan",
        "remote": False,
        "description": "Build things",
    }
    d.update(kw)
    return NS(**d)


def test_norm_strips_accents():
    assert norm("Islāmābād") == "islamabad" and norm("Karāchi") == "karachi"


def test_empty_profile_passes_everything_with_a_description():
    assert check_job(job(), Profile()).passed


def test_missing_description_is_rejected():
    assert check_job(job(description=""), Profile()).reasons == ["no_description"]


def test_location_matches_across_spellings():
    p = Profile(locations=["karachi"])
    assert check_job(job(location="Karāchi, Sindh, Pakistan"), p).passed
    assert check_job(job(location="Karachi Division, Sindh, Pakistan"), p).passed
    assert check_job(job(location="Lahore, Punjab, Pakistan"), p).reasons == ["location"]


def test_title_filter_requires_all_words_of_one_phrase():
    p = Profile(titles=["backend developer", "full stack developer"])
    assert check_job(job(title="Senior .Net Full Stack Developer"), p).passed
    assert check_job(job(title=".NET Developer"), p).reasons == ["title"]


def test_blocklist_checks_company_and_title():
    p = Profile(blocklist=["Acme"])
    assert check_job(job(), p).reasons == ["blocklist:acme"]


def test_remote_in_title_counts_and_skips_location():
    p = Profile(remote_pref="remote_only", locations=["lahore"])
    r = check_job(job(title="Engineer - Remote", location="Karāchi, Pakistan"), p)
    assert r.passed
    assert check_job(job(), p).reasons == ["not_remote", "location"]
