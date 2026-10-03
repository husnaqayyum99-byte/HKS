import hashlib
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup

from app.legal_sources.source_registry import LegalSource


def _belongs_to_registered_domain(url: str, source: LegalSource) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().rstrip(".")
    domain = source.official_domain.lower().rstrip(".")
    return parsed.scheme == "https" and (host == domain or host.endswith(f".{domain}"))


def check_source_health(
    source: LegalSource,
    previous_content_hash: str | None = None,
    timeout: int = 10,
) -> dict:
    url = source.search_url or f"https://{source.official_domain}"
    try:
        response = requests.get(
            url,
            timeout=timeout,
            headers={"User-Agent": "Apna-Wakeel/0.1"},
        )
        response.raise_for_status()
    except requests.RequestException as error:
        return {
            "source_name": source.name,
            "available": False,
            "redirected": False,
            "redirect_within_domain": None,
            "content_accessible": False,
            "content_hash": None,
            "page_changed": None,
            "final_url": None,
            "error": type(error).__name__,
        }

    final_url = response.url
    redirect_within_domain = _belongs_to_registered_domain(final_url, source)
    content_type = response.headers.get("content-type", "").lower()
    content = response.content
    if "text/html" in content_type:
        soup = BeautifulSoup(response.text, "html.parser")
        for element in soup(["script", "style", "noscript"]):
            element.decompose()
        accessible = bool(soup.get_text(" ", strip=True))
    elif "application/pdf" in content_type:
        accessible = bool(content)
    else:
        accessible = False

    content_hash = hashlib.sha256(content).hexdigest() if accessible else None
    return {
        "source_name": source.name,
        "available": True,
        "redirected": final_url != url,
        "redirect_within_domain": redirect_within_domain,
        "content_accessible": accessible,
        "content_hash": content_hash,
        "page_changed": (
            content_hash != previous_content_hash
            if content_hash and previous_content_hash
            else None
        ),
        "final_url": final_url,
        "error": None,
    }
