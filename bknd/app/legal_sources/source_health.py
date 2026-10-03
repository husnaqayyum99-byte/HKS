import hashlib
import time
from datetime import datetime, timezone
from io import BytesIO
from urllib.parse import urlparse

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader
from pypdf.errors import PdfReadError, PdfStreamError

from app.legal_sources.source_registry import LegalSource


_MAX_ATTEMPTS = 3
_RETRY_DELAY_SECONDS = 0.25


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
    checked_at = datetime.now(timezone.utc).isoformat()
    response = None
    request_error = None
    attempts = 0
    for attempt in range(_MAX_ATTEMPTS):
        attempts += 1
        try:
            response = requests.get(
                url,
                timeout=timeout,
                headers={
                    "User-Agent": "Apna-Wakeel/0.1",
                    "Accept": "text/html,application/pdf;q=0.9,*/*;q=0.8",
                },
            )
            response.raise_for_status()
            request_error = None
            break
        except requests.RequestException as error:
            request_error = error
            status_code = getattr(getattr(error, "response", None), "status_code", None)
            transient_http_status = status_code == 429 or (
                status_code is not None and 500 <= status_code < 600
            )
            transient_transport_error = (
                isinstance(error, (requests.Timeout, requests.ConnectionError))
                and not isinstance(error, requests.exceptions.SSLError)
            )
            if (
                attempt + 1 >= _MAX_ATTEMPTS
                or not (transient_http_status or transient_transport_error)
            ):
                break
            time.sleep(_RETRY_DELAY_SECONDS * (attempt + 1))

    if request_error is not None:
        response = getattr(request_error, "response", None)
        status_code = getattr(response, "status_code", None)
        body = getattr(response, "text", "") or ""
        lowered_body = body.casefold()
        if status_code == 403 and ("cloudflare" in lowered_body or "just a moment" in lowered_body):
            failure_reason = "HTTP 403: remote Cloudflare challenge blocks automated access"
        elif status_code == 403:
            failure_reason = "HTTP 403: remote server denied access to this request"
        elif isinstance(request_error, requests.Timeout):
            failure_reason = f"Request timed out after {timeout} seconds"
        elif isinstance(request_error, requests.exceptions.SSLError):
            failure_reason = f"TLS/SSL request failed: {request_error}"
        elif isinstance(request_error, requests.ConnectionError):
            failure_reason = f"Connection failed: {request_error}"
        else:
            failure_reason = f"{type(request_error).__name__}: {request_error}"
        return {
            "source_name": source.name,
            "available": False,
            "redirect_within_domain": (
                _belongs_to_registered_domain(response.url, source)
                if response is not None and getattr(response, "url", None)
                else None
            ),
            "content_accessible": False,
            "content_hash": None,
            "page_changed": None,
            "freshness_status": "unknown",
            "status": "unavailable",
            "checked_at": checked_at,
            "attempts": attempts,
            "requested_url": url,
            "redirected": bool(
                response is not None
                and getattr(response, "url", None)
                and response.url != url
            ),
            "final_url": getattr(response, "url", None),
            "http_status": status_code,
            "error": type(request_error).__name__,
            "failure_reason": failure_reason,
        }

    final_url = response.url
    redirect_within_domain = _belongs_to_registered_domain(final_url, source)
    content_type = response.headers.get("content-type", "").lower()
    content = response.content
    if not redirect_within_domain:
        accessible = False
        failure_reason = (
            f"Redirected outside registered official domain "
            f"{source.official_domain}: {final_url}"
        )
    elif "text/html" in content_type:
        soup = BeautifulSoup(response.text, "html.parser")
        for element in soup(["script", "style", "noscript"]):
            element.decompose()
        accessible = bool(soup.get_text(" ", strip=True))
        failure_reason = None if accessible else "HTML response contained no readable text"
    elif "application/pdf" in content_type:
        try:
            reader = PdfReader(BytesIO(content), strict=False)
            accessible = any(
                (page.extract_text() or "").strip()
                for page in reader.pages[:5]
            )
        except (PdfReadError, PdfStreamError, ValueError, OSError):
            accessible = False
        failure_reason = (
            None if accessible
            else "PDF response contained no extractable text in its first five pages"
        )
    else:
        accessible = False
        failure_reason = f"Unsupported content type: {content_type or 'missing'}"

    content_hash = hashlib.sha256(content).hexdigest() if accessible else None
    page_changed = (
        content_hash != previous_content_hash
        if content_hash and previous_content_hash
        else None
    )
    return {
        "source_name": source.name,
        "available": True,
        "redirected": final_url != url,
        "redirect_within_domain": redirect_within_domain,
        "content_accessible": accessible,
        "content_hash": content_hash,
        "page_changed": page_changed,
        "freshness_status": (
            "unknown" if page_changed is None
            else "changed_since_last_check" if page_changed
            else "unchanged_since_last_check"
        ),
        "status": (
            "unavailable" if not redirect_within_domain
            else "available" if accessible
            else "unreadable"
        ),
        "checked_at": checked_at,
        "attempts": attempts,
        "requested_url": url,
        "final_url": final_url,
        "http_status": getattr(response, "status_code", None),
        "error": None,
        "failure_reason": failure_reason,
    }
