import random
import time

import requests
from bs4 import BeautifulSoup

from jobs.sources.linkedin import LinkedInBlocked

HEADERS = {"User-Agent": "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124 Safari/537.36",
           "Accept-Language": "en-US,en;q=0.9"}


def parse_description(html: str) -> str:
    """Pure function. Selector is [VERIFY]: check against a real guest job page."""
    soup = BeautifulSoup(html or "", "html.parser")
    node = soup.select_one("div.show-more-less-html__markup")
    return node.get_text("\n", strip=True) if node else ""


def fetch_description(url: str, get=requests.get, sleep=time.sleep, pause=(3, 8)) -> str:
    sleep(random.uniform(*pause))
    resp = get(url, headers=HEADERS, timeout=20)
    if resp.status_code in (429, 999):
        raise LinkedInBlocked(f"HTTP {resp.status_code} fetching description; stop and wait")
    resp.raise_for_status()
    return parse_description(resp.text)
