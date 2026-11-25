import re
import unicodedata
from dataclasses import dataclass, field


def norm(s: str) -> str:
    """Casefold and strip accents so 'Karāchi' matches 'karachi'."""
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    return " ".join(s.casefold().split())


def norm_title(s: str) -> str:
    """Titles only: 'Full-Stack Engineer' and 'full stack developer' compare equal."""
    s = re.sub(r"[-–—/]", " ", norm(s))
    return re.sub(r"\bengineers?\b", "developer", s)


@dataclass
class FilterResult:
    passed: bool
    reasons: list[str] = field(default_factory=list)


def is_remote(job) -> bool:
    return bool(job.remote) or "remote" in norm(job.title)


def check_job(job, profile, require_description: bool = True) -> FilterResult:
    """Hard filters. Pure function: works on unsaved objects, touches no DB."""
    reasons = []
    if require_description and not (job.description or "").strip():
        reasons.append("no_description")  # can't be scored; refetch later

    title = norm_title(job.title)
    haystack = norm(f"{job.title} {job.company_name}")  # not the description: too many false hits
    for term in profile.blocklist or []:
        t = norm(term)
        if t and t in haystack:
            reasons.append(f"blocklist:{t}")
            break

    titles = [norm_title(t) for t in (profile.titles or []) if norm(t)]
    if titles and not any(all(w in title for w in t.split() if len(w) > 2) for t in titles):
        reasons.append("title")

    remote = is_remote(job)
    pref = profile.remote_pref
    if pref == "remote_only" and not remote:
        reasons.append("not_remote")
    elif pref == "onsite_only" and remote:
        reasons.append("remote_not_wanted")

    locs = [norm(l) for l in (profile.locations or []) if norm(l)]
    if locs and not (remote and pref != "onsite_only") and not any(l in norm(job.location) for l in locs):
        reasons.append("location")  # remote jobs skip the location check

    return FilterResult(passed=not reasons, reasons=reasons)
