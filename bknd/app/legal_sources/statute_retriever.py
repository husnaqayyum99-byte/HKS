import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime, timezone
from functools import lru_cache
from io import BytesIO
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader
from pypdf.errors import PdfReadError, PdfStreamError

from app.legal_sources.evidence import EvidenceItem
from app.legal_sources.source_registry import jurisdiction_scope


FEDERAL_LAWS_URL = "https://pakistancode.gov.pk/english/sHyuRiF.php"
KP_LAWS_SEARCH_URL = "https://kpcode.kp.gov.pk/homepage/search"
USER_AGENT = "Apna-Wakeel/0.1"
CATALOG_CACHE_SECONDS = 3600
MAX_LAWS_PER_CASE = 6
MAX_PAGES_PER_LAW = 2


@dataclass(frozen=True)
class LawRecord:
    title: str
    detail_url: str
    jurisdiction: str
    official_domain: str


_catalog_cache: dict[str, tuple[float, list[LawRecord]]] = {}
_catalog_lock = threading.Lock()
_stop_words = {
    "about", "after", "also", "all", "and", "any", "applicable", "are",
    "been", "being", "case", "code", "did", "for", "from", "have", "has",
    "into", "investigation", "its", "law", "laws", "legal", "may", "more", "not", "only",
    "officer", "officers", "other", "over", "police", "procedure", "provision",
    "report", "section", "sections", "should", "such", "pakistan",
        "that", "their", "them", "there", "these", "this", "those", "under",
        "was", "what", "when", "where", "which", "who", "with", "would", "the",
}


def _trusted_host(url: str, official_domain: str) -> bool:
    host = urlparse(url).hostname or ""
    host = host.lower().rstrip(".")
    domain = official_domain.lower().rstrip(".")
    return host == domain or host.endswith(f".{domain}")


def _fetch_federal_catalog() -> list[LawRecord]:
    response = requests.get(
        FEDERAL_LAWS_URL,
        timeout=20,
        headers={"User-Agent": USER_AGENT},
    )
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    records = []

    for link in soup.find_all("a", href=True):
        title = " ".join(link.get_text(" ", strip=True).split())
        detail_url = urljoin(FEDERAL_LAWS_URL, link["href"])
        if not title or not _trusted_host(detail_url, "pakistancode.gov.pk"):
            continue
        if "/english/" not in urlparse(detail_url).path:
            continue
        records.append(LawRecord(title, detail_url, "Federal", "pakistancode.gov.pk"))

    return records


def _fetch_kp_catalog(search_title: str) -> list[LawRecord]:
    session = requests.Session()
    headers = {"User-Agent": USER_AGENT}
    session.get(
        "https://kpcode.kp.gov.pk/homepage/advance_search",
        timeout=20,
        headers=headers,
    ).raise_for_status()
    response = session.post(
        KP_LAWS_SEARCH_URL,
        data={"search_law": search_title},
        timeout=20,
        headers=headers,
    )
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    records = []

    for link in soup.find_all("a", href=True):
        title = " ".join(link.get_text(" ", strip=True).split())
        detail_url = urljoin(response.url, link["href"])
        if not title or "/homepage/lawDetails/" not in urlparse(detail_url).path:
            continue
        if not _trusted_host(detail_url, "kpcode.kp.gov.pk"):
            continue
        records.append(
            LawRecord(title, detail_url, "Khyber Pakhtunkhwa", "kpcode.kp.gov.pk")
        )

    return records


def _cached_federal_catalog() -> list[LawRecord]:
    key = "federal"
    now = time.monotonic()
    with _catalog_lock:
        cached = _catalog_cache.get(key)
        if cached and now - cached[0] < CATALOG_CACHE_SECONDS:
            return cached[1]

    records = _fetch_federal_catalog()
    with _catalog_lock:
        _catalog_cache[key] = (time.monotonic(), records)
    return records


def _normalize(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.lower()))


def _record_matches(record: LawRecord, requested_name: str) -> bool:
    title = _normalize(record.title)
    requested = _normalize(requested_name)
    requested_years = set(re.findall(r"\b(?:18|19|20)\d{2}\b", requested_name))
    title_years = set(re.findall(r"\b(?:18|19|20)\d{2}\b", record.title))
    if requested_years and not requested_years.issubset(title_years):
        return False
    provincial_request = "khyber pakhtunkhwa" in requested
    if provincial_request and record.jurisdiction != "Khyber Pakhtunkhwa":
        return False
    aliases = {
        "ppc": "pakistan penal code",
        "crpc": "code of criminal procedure",
        "qso": "qanun e shahadat order",
    }
    requested = re.sub(r"\b(ppc|crpc|qso)\b", lambda match: aliases[match.group(1)], requested)
    if requested and requested in title:
        return True
    title_without_abbreviations = " ".join(
        word for word in title.split() if word not in {"ppc", "crpc", "qso"}
    )
    if requested and requested in title_without_abbreviations:
        return True

    jurisdiction_words = {"pakistan", "federal"}
    requested_words = {
        word
        for word in requested.split()
        if len(word) > 2 and word not in jurisdiction_words and not word.isdigit()
    }
    title_words = set(title.split())
    if len(requested_words) < 3:
        return False
    return len(requested_words & title_words) / len(requested_words) >= 0.8


def _kp_search_title(law_name: str) -> str:
    normalized = _normalize(law_name)
    if "criminal" in normalized and "procedure" in normalized:
        return "Code of Criminal Procedure"
    return law_name


def find_law_records(
    law_names: list[str],
    jurisdiction: str,
) -> list[LawRecord]:
    jurisdiction = jurisdiction_scope(jurisdiction)
    if not law_names or jurisdiction not in {"federal", "khyber pakhtunkhwa"}:
        return []

    selected: dict[str, LawRecord] = {}
    try:
        federal_records = _cached_federal_catalog()
    except requests.RequestException:
        federal_records = []

    for law_name in law_names[:MAX_LAWS_PER_CASE]:
        for record in federal_records:
            if _record_matches(record, law_name):
                selected[record.detail_url] = record

    if jurisdiction == "khyber pakhtunkhwa":
        kp_search_titles = list(dict.fromkeys(
            _kp_search_title(name) for name in law_names[:MAX_LAWS_PER_CASE]
        ))
        with ThreadPoolExecutor(max_workers=3) as executor:
            searches = [
                executor.submit(_fetch_kp_catalog, title)
                for title in kp_search_titles
            ]
            for search in searches:
                try:
                    records = search.result()
                except requests.RequestException:
                    continue
                for record in records:
                    if any(_record_matches(record, name) for name in law_names[:MAX_LAWS_PER_CASE]):
                        selected[record.detail_url] = record

    return sorted(
        selected.values(),
        key=lambda record: 0
        if jurisdiction == "khyber pakhtunkhwa"
        and record.jurisdiction == "Khyber Pakhtunkhwa"
        else 1,
    )[:MAX_LAWS_PER_CASE]


def _ranked_statute_sections(text: str, research_questions: list[str]):
    section_pattern = re.compile(r"(?<![A-Za-z0-9])(\d{1,4}[A-Za-z]?)\.\s+")
    matches = list(section_pattern.finditer(text))
    ranked_sections = []

    for index, match in enumerate(matches):
        end = matches[index + 1].start() if index + 1 < len(matches) else len(text)
        section_text = " ".join(text[match.end():end].split())
        if not section_text:
            continue
        heading = re.split(r"\b(?:CHAPTER|PART)\s+[IVX0-9]+\b", section_text, maxsplit=1, flags=re.IGNORECASE)[0]
        heading = re.split(r"(?<=[.!?])\s+", heading, maxsplit=1)[0].strip(" .")
        section_words = _keywords(section_text[:1800])
        heading_words = _keywords(heading)
        requested_sections = set()
        for question in research_questions:
            requested_sections.update(
                re.findall(r"\b(?:section|sections)\s+(\d+[A-Za-z]?)\b", question, re.IGNORECASE)
            )
        heading_overlap = max(
            (len(heading_words & _keywords(question)) for question in research_questions),
            default=0,
        )
        explicit_section_match = match.group(1).lower() in {
            section.lower() for section in requested_sections
        }
        if not heading_overlap and not explicit_section_match:
            continue
        score = max(
            (
                (100 if explicit_section_match else 0)
                + 10 * len(heading_words & _keywords(question))
                + min(5, len(section_words & _keywords(question)))
                for question in research_questions
            ),
            default=0,
        )
        if score:
            ranked_sections.append((score, match.group(1), heading, section_text))

    ranked_sections.sort(key=lambda item: item[0], reverse=True)
    return ranked_sections


def _section_references(text: str, research_questions: list[str]) -> list[str]:
    return [
        f"section {number} ({heading})"
        for _, number, heading, _ in _ranked_statute_sections(text, research_questions)[:4]
    ]


def _keywords(text: str) -> set[str]:
    return {
        word
        for word in re.findall(r"[a-z]{3,}", text.lower())
        if word not in _stop_words
    }


def _page_score(page_text: str, questions: list[str]) -> int:
    return max(
        (score for score, _, _, _ in _ranked_statute_sections(page_text, questions)),
        default=0,
    )


def _find_pdf_url(record: LawRecord) -> str | None:
    response = requests.get(
        record.detail_url,
        timeout=20,
        headers={"User-Agent": USER_AGENT},
    )
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    candidates = []

    for element in soup.find_all(["a", "iframe", "embed", "object"]):
        target = element.get("href") or element.get("src") or element.get("data")
        if target:
            url = urljoin(record.detail_url, target)
            if ".pdf" in urlparse(url).path.lower():
                candidates.append(url)

    return next(
        (url for url in candidates if _trusted_host(url, record.official_domain)),
        None,
    )


def _retrieve_record(arguments: tuple[LawRecord, list[str]]) -> list[EvidenceItem]:
    record, research_questions = arguments
    try:
        pdf_url = _find_pdf_url(record)
        if not pdf_url:
            return []

        response = requests.get(
            pdf_url,
            timeout=30,
            headers={"User-Agent": USER_AGENT},
        )
        response.raise_for_status()
        if not response.content.startswith(b"%PDF"):
            return []

        reader = PdfReader(BytesIO(response.content), strict=False)
        ranked_pages = []
        for index, page in enumerate(reader.pages):
            page_text = page.extract_text() or ""
            score = _page_score(page_text, research_questions)
            if score:
                ranked_pages.append((score, index + 1, page_text))
        ranked_pages.sort(key=lambda item: item[0], reverse=True)

        evidence = []
        for score, page_number, page_text in ranked_pages[:MAX_PAGES_PER_LAW]:
            relevant_sections = _ranked_statute_sections(page_text, research_questions)[:3]
            sections = [
                f"section {number} ({heading})"
                for _, number, heading, _ in relevant_sections
            ]
            relevant_text = "\n\n".join(
                f"{number}. {heading}. {section_text[:1200]}"
                for _, number, heading, section_text in relevant_sections
            )
            citation_parts = [record.title]
            citation_parts.extend(sections)
            citation_parts.append(f"page {page_number}")
            status = "Under Review" if "under review" in record.title.lower() else None
            evidence.append(
                EvidenceItem(
                    source_name="Pakistan Code" if record.jurisdiction == "Federal" else "Khyber Pakhtunkhwa Code",
                    source_url=pdf_url,
                    source_title=record.title,
                    jurisdiction=record.jurisdiction,
                    source_type="legislation",
                    relevant_text=relevant_text[:4000],
                    retrieval_method="official_law_pdf",
                    retrieval_score=score,
                    retrieved_at=datetime.now(timezone.utc).isoformat(),
                    citation=", ".join(citation_parts),
                    page_number=page_number,
                    official_status=status,
                )
            )
        return evidence
    except (requests.RequestException, ValueError, OSError, PdfReadError, PdfStreamError):
        return []


def collect_statute_evidence(
    law_names: list[str],
    research_questions: list[str],
    jurisdiction: str,
) -> list[EvidenceItem]:
    records = find_law_records(law_names, jurisdiction)
    if not records or not research_questions:
        return []

    with ThreadPoolExecutor(max_workers=min(4, len(records))) as executor:
        evidence_by_law = executor.map(
            _retrieve_record,
            ((record, research_questions) for record in records),
        )
        return [item for result in evidence_by_law for item in result]