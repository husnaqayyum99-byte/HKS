import re
from datetime import datetime, timezone

import requests
from bs4 import BeautifulSoup

from app.legal_sources.evidence import EvidenceItem
from app.legal_sources.source_registry import LegalSource


def fetch_source(source: LegalSource) -> str:
    """
    Fetch and clean readable text from a registered official source.
    """

    url = source.search_url or f"https://{source.official_domain}"

    response = requests.get(
        url,
        timeout=10,
        headers={
            "User-Agent": "Apna-Wakeel/0.1"
        },
    )

    response.raise_for_status()

    soup = BeautifulSoup(response.text, "html.parser")

    for element in soup(["script", "style", "noscript"]):
        element.decompose()

    return soup.get_text(
        separator=" ",
        strip=True,
    )


from urllib.parse import urljoin, urlparse


def _is_official_url(url: str, official_domain: str) -> bool:
    parsed = urlparse(url)
    host = (parsed.hostname or "").lower().rstrip(".")
    domain = official_domain.lower().rstrip(".")
    return parsed.scheme == "https" and (host == domain or host.endswith(f".{domain}"))


def find_relevant_links(
    source: LegalSource,
    research_question: str,
    max_links: int = 5,
) -> list[str]:
    """
    Find potentially relevant links on the registered official source.
    Only links belonging to the same official domain are considered.
    """

    url = source.search_url or f"https://{source.official_domain}"

    response = requests.get(
        url,
        timeout=10,
        headers={
            "User-Agent": "Apna-Wakeel/0.1"
        },
    )

    response.raise_for_status()
    if not _is_official_url(response.url, source.official_domain):
        return []

    soup = BeautifulSoup(response.text, "html.parser")

    question_words = set(
        re.findall(
            r"\b[a-zA-Z]{4,}\b",
            research_question.lower(),
        )
    )

    matches = []

    for link in soup.find_all("a", href=True):

        href = link.get("href")
        link_text = link.get_text(" ", strip=True)

        absolute_url = urljoin(url, href)

        if not _is_official_url(absolute_url, source.official_domain):
            continue

        combined_text = (
            f"{link_text} {absolute_url}"
        ).lower()

        link_words = set(
            re.findall(
                r"\b[a-zA-Z]{4,}\b",
                combined_text,
            )
        )

        score = len(
            question_words & link_words
        )

        if score > 0:
            matches.append(
                (score, absolute_url)
            )

    matches.sort(
        key=lambda item: item[0],
        reverse=True,
    )

    return [
        url
        for _, url in matches[:max_links]
    ]

def find_relevant_text(
    page_text: str,
    research_question: str,
    max_length: int = 5000,
) -> str:
    """
    Find text on the page that overlaps with words
    from the research question.
    """

    question_words = set(
        re.findall(
            r"\b[a-zA-Z]{4,}\b",
            research_question.lower(),
        )
    )

    sentences = re.split(
        r"(?<=[.!?])\s+",
        page_text,
    )

    relevant_sentences = []

    for sentence in sentences:

        sentence_words = set(
            re.findall(
                r"\b[a-zA-Z]{4,}\b",
                sentence.lower(),
            )
        )

        if question_words & sentence_words:
            relevant_sentences.append(sentence)

    result = " ".join(relevant_sentences)

    return result[:max_length]


def fetch_url_text(
    source: LegalSource,
    url: str,
) -> str:
    """
    Fetch readable text from a URL only if it belongs
    to the registered official domain.
    """

    if not _is_official_url(url, source.official_domain):
        raise ValueError(
            "URL does not belong to the registered official domain."
        )

    response = requests.get(
        url,
        timeout=10,
        headers={
            "User-Agent": "Apna-Wakeel/0.1"
        },
    )

    response.raise_for_status()
    if not _is_official_url(response.url, source.official_domain):
        raise ValueError("URL redirected outside the registered official domain.")

    content_type = response.headers.get(
        "content-type",
        ""
    ).lower()

    # We currently handle HTML pages only.
    if "text/html" not in content_type:
        return ""

    soup = BeautifulSoup(
        response.text,
        "html.parser",
    )

    for element in soup(
        ["script", "style", "noscript"]
    ):
        element.decompose()

    return soup.get_text(
        separator=" ",
        strip=True,
    )

def score_relevance(
    text: str,
    research_question: str,
) -> int:
    """
    Score a page based on how many meaningful words
    from the research question appear in the page text.
    """

    question_words = set(
        re.findall(
            r"\b[a-zA-Z]{4,}\b",
            research_question.lower(),
        )
    )

    page_words = set(
        re.findall(
            r"\b[a-zA-Z]{4,}\b",
            text.lower(),
        )
    )

    return len(question_words & page_words)

def find_best_page(
    source: LegalSource,
    research_question: str,
    links: list[str],
) -> tuple[str, str] | None:
    """
    Fetch candidate pages and return the most relevant page
    together with its readable text.
    """

    best_url = None
    best_text = ""
    best_score = 0

    for url in links:

        try:
            text = fetch_url_text(
                source,
                url,
            )

        except (requests.RequestException, ValueError):
            continue

        if not text:
            continue

        score = score_relevance(
            text,
            research_question,
        )

        if score > best_score:
            best_score = score
            best_url = url
            best_text = text

    if best_url is None:
        return None

    return best_url, best_text


def collect_evidence(
    sources: list[LegalSource],
    research_questions: list[str],
) -> list[EvidenceItem]:

    evidence: list[EvidenceItem] = []

    for source in sources:

        for question in research_questions:

            try:
                candidate_links = find_relevant_links(
                    source,
                    question,
                )

                best_page = find_best_page(
                    source,
                    question,
                    candidate_links,
                )

            except requests.RequestException:
                continue

            if best_page is None:
                continue

            best_url, page_text = best_page

            relevant_text = find_relevant_text(
                page_text,
                question,
            )

            if not relevant_text:
                continue

            evidence.append(
                EvidenceItem(
                    source_name=source.name,
                    source_url=best_url,
                    source_title=question,
                    jurisdiction=source.jurisdiction,
                    source_type=source.source_type,
                    relevant_text=relevant_text,
                    retrieval_method="official_html_page",
                    retrieved_at=datetime.now(timezone.utc).isoformat(),
                )
            )

    return evidence