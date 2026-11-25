import os
from dataclasses import dataclass
from typing import Protocol

import requests  # Apache-2.0


class ResumeParseError(Exception):
    def __init__(self, msg, retryable=False):
        super().__init__(msg)
        self.retryable = retryable


@dataclass(frozen=True)
class ParsedResume:
    text: str
    json_resume: dict


class ResumeParser(Protocol):
    def parse(self, filename: str, content: bytes) -> ParsedResume: ...


def normalize(jr: dict) -> dict:
    """Guarantee the JSON Resume sections exist so downstream code can rely on them."""
    jr = dict(jr)
    jr["basics"] = jr.get("basics") if isinstance(jr.get("basics"), dict) else {}
    for key in ("work", "education", "skills", "projects"):
        jr[key] = jr.get(key) if isinstance(jr.get(key), list) else []
    return jr


class ResumeIQParser:
    """Calls the ResumeIQ service's /parse endpoint. Never log resume text."""

    def __init__(self, base_url=None, api_key=None, post=requests.post, timeout=90):
        self.base_url = (base_url or os.environ.get("RESUMEIQ_URL", "")).rstrip("/")
        self.api_key = api_key or os.environ.get("RESUMEIQ_API_KEY", "")
        self._post = post
        self.timeout = timeout  # generous: free-tier hosts cold-start

    def parse(self, filename: str, content: bytes) -> ParsedResume:
        if not self.base_url or not self.api_key:
            raise ResumeParseError("RESUMEIQ_URL / RESUMEIQ_API_KEY not configured")
        try:
            r = self._post(f"{self.base_url}/parse", headers={"X-API-Key": self.api_key},
                           files={"file": (filename, content)}, timeout=self.timeout)
        except requests.RequestException as e:
            raise ResumeParseError(f"ResumeIQ unreachable: {type(e).__name__}", retryable=True) from e
        if r.status_code != 200:
            raise ResumeParseError(f"ResumeIQ returned HTTP {r.status_code}",
                                   retryable=r.status_code >= 500 or r.status_code == 429)
        try:
            data = r.json()
            jr, text = data["json_resume"], data["extracted_text"]
        except (ValueError, KeyError, TypeError) as e:
            raise ResumeParseError("ResumeIQ response had an unexpected shape") from e
        if not isinstance(jr, dict):
            raise ResumeParseError("json_resume is not an object")
        return ParsedResume(text=text, json_resume=normalize(jr))
