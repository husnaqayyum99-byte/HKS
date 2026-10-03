import math
import re
from dataclasses import dataclass


@dataclass(frozen=True)
class LegalSource:
    name: str
    authority: str
    jurisdiction: str
    source_type: str
    domain: str
    official_domain: str
    search_url: str | None = None
    information_types: tuple[str, ...] = ()
    legal_topics: tuple[str, ...] = ()
    priority: int = 50
    active: bool = True


LEGAL_SOURCES = [
    LegalSource(
        name="Pakistan Code",
        authority="Ministry of Law and Justice, Government of Pakistan",
        jurisdiction="Federal",
        source_type="legislation",
        domain="Federal laws and statutes",
        official_domain="pakistancode.gov.pk",
        search_url="https://pakistancode.gov.pk/english/",
        information_types=("federal legislation", "statutory text"),
        legal_topics=("identity documents", "property", "inheritance", "tenancy", "employment", "police reporting"),
        priority=100,
    ),
    LegalSource(
        name="Khyber Pakhtunkhwa Code",
        authority="Law, Parliamentary Affairs and Human Rights Department, Government of Khyber Pakhtunkhwa",
        jurisdiction="Khyber Pakhtunkhwa",
        source_type="legislation",
        domain="Provincial legislation and legal codes",
        official_domain="kpcode.kp.gov.pk",
        search_url="https://kpcode.kp.gov.pk/homepage/search",
        information_types=("provincial legislation", "statutory text"),
        legal_topics=("property", "inheritance", "tenancy", "employment", "police reporting"),
        priority=100,
    ),

    LegalSource(
        name="Khyber Pakhtunkhwa Government Portal",
        authority="Government of Khyber Pakhtunkhwa",
        jurisdiction="Khyber Pakhtunkhwa",
        source_type="government",
        domain="Provincial government information and services",
        official_domain="kp.gov.pk",
        search_url="https://kp.gov.pk/",
        information_types=("government services", "official department information"),
        legal_topics=("property", "tenancy", "housing", "employment", "police reporting"),
        priority=60,
    ),
    LegalSource(
        name="Khyber Pakhtunkhwa Revenue and Estate Department",
        authority="Revenue and Estate Department, Government of Khyber Pakhtunkhwa",
        jurisdiction="Khyber Pakhtunkhwa",
        source_type="government_department",
        domain="Property records, land administration, and revenue services",
        official_domain="revenue.kp.gov.pk",
        search_url="https://revenue.kp.gov.pk/",
        information_types=("land administration", "revenue services", "official procedures"),
        legal_topics=("property", "inheritance", "agricultural land"),
        priority=90,
    ),
    LegalSource(
        name="Khyber Pakhtunkhwa Police",
        authority="Police Department, Government of Khyber Pakhtunkhwa",
        jurisdiction="Khyber Pakhtunkhwa",
        source_type="police_authority",
        domain="Police reporting, public services, and complaint information",
        official_domain="kppolice.gov.pk",
        search_url="https://www.kppolice.gov.pk/",
        information_types=("police services", "complaint information", "reporting procedures"),
        legal_topics=("police reporting", "criminal"),
        priority=90,
    ),
    LegalSource(
        name="Khyber Pakhtunkhwa Labour Department",
        authority="Labour Department, Government of Khyber Pakhtunkhwa",
        jurisdiction="Khyber Pakhtunkhwa",
        source_type="government_department",
        domain="Employment standards and labour services",
        official_domain="labour.kp.gov.pk",
        search_url="https://labour.kp.gov.pk/",
        information_types=("labour services", "employment standards", "official procedures"),
        legal_topics=("employment", "wages", "workplace"),
        priority=90,
    ),

    LegalSource(
        name="NADRA",
        authority="National Database and Registration Authority",
        jurisdiction="Pakistan",
        source_type="government_authority",
        domain="Identity documents and registration services",
        official_domain="nadra.gov.pk",
        search_url="https://www.nadra.gov.pk/",
        information_types=("identity registration", "CNIC services", "official procedures"),
        legal_topics=("identity documents", "CNIC", "registration"),
        priority=90,
    ),
]

_UNKNOWN_JURISDICTIONS = {
    "",
    "unknown",
    "unclear",
    "not known",
    "not specified",
}
_JURISDICTION_ALIASES = {
    "federal": "federal",
    "pakistan": "federal",
    "khyber pakhtunkhwa": "khyber pakhtunkhwa",
    "kp": "khyber pakhtunkhwa",
}
_MATCH_STOP_WORDS = {
    "about", "and", "are", "authority", "department", "government",
    "information", "legal", "official", "procedure", "services", "source",
    "the", "to",
}


def jurisdiction_scope(value: str) -> str:
    normalized = " ".join(re.findall(r"[a-z0-9]+", (value or "").casefold()))
    if normalized in _UNKNOWN_JURISDICTIONS:
        return ""
    return _JURISDICTION_ALIASES.get(normalized, normalized)


def _source_jurisdiction_tier(source: LegalSource, jurisdiction: str) -> int | None:
    requested_scope = jurisdiction_scope(jurisdiction)
    source_scope = jurisdiction_scope(source.jurisdiction)
    if not requested_scope:
        return None
    if requested_scope == "federal":
        return 0 if source_scope == "federal" else None
    if requested_scope == "khyber pakhtunkhwa":
        if source_scope == requested_scope:
            return 0
        if source_scope == "federal":
            return 1
        return None
    return 0 if source_scope == requested_scope else None


def _tokens(value: str) -> set[str]:
    return {
        token
        for token in re.findall(r"[a-z0-9]+", value.casefold())
        if len(token) > 2 and token not in _MATCH_STOP_WORDS
    }


def _domain_relevance(source: LegalSource, domain: str) -> int:
    requested = " ".join(re.findall(r"[a-z0-9]+", domain.casefold()))
    requested_tokens = _tokens(domain)
    if not requested_tokens:
        return 0

    values = (
        source.domain,
        *source.legal_topics,
        *source.information_types,
    )
    best_score = 0
    minimum_overlap = max(1, math.ceil(len(requested_tokens) / 2))
    for value in values:
        normalized_value = " ".join(re.findall(r"[a-z0-9]+", value.casefold()))
        if requested and (requested in normalized_value or normalized_value in requested):
            best_score = max(best_score, 4)
            continue
        overlap = len(requested_tokens & _tokens(value))
        if overlap >= minimum_overlap:
            best_score = max(best_score, overlap)
    return best_score


def _metadata_values(source: LegalSource) -> tuple[str, ...]:
    return (
        source.name,
        source.authority,
        source.jurisdiction,
        source.source_type,
        source.domain,
        *source.information_types,
        *source.legal_topics,
    )


def _preference_rank(
    source: LegalSource,
    preferences: list[str],
    *,
    jurisdiction: bool,
) -> int:
    for index, preference in enumerate(preferences):
        if jurisdiction:
            if " ".join(re.findall(r"[a-z0-9]+", preference.casefold())) == " ".join(
                re.findall(r"[a-z0-9]+", source.jurisdiction.casefold())
            ):
                return index
            continue

        preference_tokens = _tokens(preference)
        if not preference_tokens:
            continue
        minimum_overlap = max(1, math.ceil(len(preference_tokens) / 2))
        if any(
            " ".join(re.findall(r"[a-z0-9]+", preference.casefold()))
            in " ".join(re.findall(r"[a-z0-9]+", value.casefold()))
            or len(preference_tokens & _tokens(value)) >= minimum_overlap
            for value in _metadata_values(source)
        ):
            return index
    return len(preferences) + 1


def _context_relevance(source: LegalSource, context: str) -> int:
    context_tokens = _tokens(context)
    metadata_tokens = set().union(*(_tokens(value) for value in _metadata_values(source)))
    return len(context_tokens & metadata_tokens)


def get_relevant_sources(
    jurisdiction: str,
    domain: str,
    locality: str = "",
    priority_jurisdictions: list[str] | None = None,
    source_types: list[str] | None = None,
    research_context: str = "",
) -> list[LegalSource]:
    del locality
    results = []
    priority_jurisdictions = [
        value.strip()
        for value in (priority_jurisdictions or [])
        if isinstance(value, str) and value.strip()
    ]
    source_types = [
        value.strip()
        for value in (source_types or [])
        if isinstance(value, str) and value.strip()
    ]

    for source in LEGAL_SOURCES:
        if not source.active:
            continue

        jurisdiction_tier = _source_jurisdiction_tier(source, jurisdiction)
        domain_score = _domain_relevance(source, domain)
        if jurisdiction_tier is None or not domain_score:
            continue
        results.append((source, jurisdiction_tier, domain_score))

    return [
        source
        for source, _, _ in sorted(
            results,
            key=lambda item: (
                item[1],
                -item[2],
                _preference_rank(item[0], priority_jurisdictions, jurisdiction=True),
                _preference_rank(item[0], source_types, jurisdiction=False),
                -_context_relevance(item[0], research_context),
                -item[0].priority,
            ),
        )
    ]