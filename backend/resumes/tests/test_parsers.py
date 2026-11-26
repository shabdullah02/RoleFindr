import pytest
import requests

from resumes.parsers import ResumeIQParser, ResumeParseError


class R:
    def __init__(self, status=200, body=None):
        self.status_code, self._body = status, body

    def json(self):
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


def parser(resp=None, exc=None):
    def post(*a, **k):
        if exc:
            raise exc
        return resp
    return ResumeIQParser(base_url="http://iq/", api_key="k", post=post)


def test_parse_ok_and_normalizes():
    body = {"extracted_text": "Jane", "json_resume": {"basics": {"name": "Jane"}}}
    out = parser(R(200, body)).parse("cv.pdf", b"x")
    assert out.text == "Jane" and out.json_resume["basics"]["name"] == "Jane"
    assert out.json_resume["work"] == [] and out.json_resume["skills"] == []


def test_http_error_raises():
    with pytest.raises(ResumeParseError, match="401"):
        parser(R(401, {})).parse("cv.pdf", b"x")


def test_unreachable_raises():
    with pytest.raises(ResumeParseError, match="unreachable"):
        parser(exc=requests.Timeout()).parse("cv.pdf", b"x")


def test_bad_shape_raises():
    with pytest.raises(ResumeParseError, match="shape"):
        parser(R(200, {"nope": 1})).parse("cv.pdf", b"x")


def test_unconfigured_raises(monkeypatch):
    monkeypatch.delenv("RESUMEIQ_URL", raising=False)
    monkeypatch.delenv("RESUMEIQ_API_KEY", raising=False)
    with pytest.raises(ResumeParseError, match="not configured"):
        ResumeIQParser().parse("resume.pdf", b"test")
