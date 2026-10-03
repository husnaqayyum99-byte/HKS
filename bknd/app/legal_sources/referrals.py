from __future__ import annotations


LAST_VERIFIED = "2026-10-04"

CHITRAL_LEGAL_DIRECTORY = [
    {
        "id": "dlec",
        "name": "District Legal Empowerment Committee (DLEC), via Chitral District & Sessions Court",
        "type": "free_legal_aid",
        "district": "Lower Chitral",
        "phone": "+92-0943-412533",
        "website": "https://www.districtcourtschitral.gov.pk/",
        "source_url": "https://www.dawn.com/news/1771837",
        "last_verified": LAST_VERIFIED,
        "confidence": "medium",
        "verified": False,
        "free_service": True,
        "notes": "The District & Sessions Judge presides over DLEC, receives legal-aid applications and appoints lawyer panels. Ask the Chitral court registry how to apply. The rules are general to KP; Chitral-specific arrangements and Upper Chitral coverage are unconfirmed.",
    },
    {
        "id": "kp_legal_aid_desk",
        "name": "KP Legal Aid Desk Committees",
        "type": "prisoner_legal_aid",
        "district": "Chitral-wide",
        "phone": None,
        "website": None,
        "source_url": "https://tribune.com.pk/story/2621556/k-p-activates-legal-aid-desks-for-destitute-women-prisoners",
        "last_verified": LAST_VERIFIED,
        "confidence": "medium",
        "verified": False,
        "free_service": True,
        "notes": "For destitute and women prisoners facing criminal cases only. Applications may be made through District Public Prosecution offices, jail superintendents, or deputy and assistant commissioner offices. This is not general legal aid.",
    },
    {
        "id": "chitral_lower_court",
        "name": "District & Sessions Court, Chitral (Lower Chitral)",
        "type": "court_and_dlec_contact",
        "district": "Lower Chitral",
        "phone": "+92-0943-412533",
        "fax": "0943-412380",
        "email": "dsjctl@districtcourtschitral.gov.pk",
        "website": "https://www.districtcourtschitral.gov.pk/",
        "source_url": "https://www.districtcourtschitral.gov.pk/ContactUs/",
        "last_verified": LAST_VERIFIED,
        "confidence": "high",
        "verified": True,
        "free_service": None,
        "notes": "The court website carries a Free Legal Aid circular, but the circular could not be opened for verification. Summer (16 April to 15 October): Monday to Thursday 8:00 to 3:30, Friday 8:00 to 12:00, Saturday 8:00 to 2:00. Winter (16 October to 15 April): Monday to Thursday and Saturday 8:30 to 3:00, Friday 8:30 to 12:30; closed Sunday. Confirm current hours directly. An ADR court at Drosh and judicial magistrates at Drosh are also listed by the court.",
    },
    {
        "id": "chitral_adr_courts",
        "name": "Local courts and ADR, including Drosh",
        "type": "court_and_adr",
        "district": "Lower Chitral",
        "phone": None,
        "website": "https://www.districtcourtschitral.gov.pk/",
        "source_url": "https://www.districtcourtschitral.gov.pk/",
        "last_verified": LAST_VERIFIED,
        "confidence": "high",
        "verified": True,
        "free_service": None,
        "notes": "An ADR court was reported at Drosh in February 2026, with judicial magistrates at Drosh and other ADR courts in Lower Chitral. Confirm current locations with the court.",
    },
    {
        "id": "chitral_bar_associations",
        "name": "District Bar Chitral, Tehsil Bar Booni (Mastuj), and Sub-Tehsil Bar Drosh",
        "type": "bar_association",
        "district": "Chitral-wide",
        "phone": None,
        "website": "https://www.districtcourtschitral.gov.pk/DistrictBarChitral/",
        "source_url": "https://www.districtcourtschitral.gov.pk/DistrictBarChitral/",
        "last_verified": LAST_VERIFIED,
        "confidence": "medium",
        "verified": False,
        "free_service": None,
        "notes": "Ask the relevant bar association about pro bono assistance. The court bar page dates from 2014 and its leadership may have changed; no individual lawyer contact is listed.",
    },
    {
        "id": "kp_bar_council",
        "name": "KP Bar Council, Peshawar (referral directory listing)",
        "type": "legal_aid_referral",
        "district": "Chitral-wide",
        "phone": "091-9211172",
        "website": None,
        "source_url": "https://shirkatgah.org/wp-content/uploads/2024/02/Referral-Directory-KPK_GAC.pdf",
        "last_verified": LAST_VERIFIED,
        "confidence": "low",
        "verified": False,
        "free_service": True,
        "notes": "A 2024 secondary referral directory describes free legal aid to victims. Whether this service accepts Chitral referrals is not confirmed.",
    },
    {
        "id": "chitral_police_emergency",
        "name": "Chitral Police emergency",
        "type": "police_emergency",
        "district": "Chitral-wide",
        "phone": "15",
        "website": "https://chitralpolice.gov.pk/",
        "source_url": "https://chitralpolice.gov.pk/",
        "last_verified": LAST_VERIFIED,
        "confidence": "high",
        "verified": True,
        "free_service": None,
        "notes": "Police emergency number listed by Chitral Police.",
    },
    {
        "id": "dpo_lower_chitral",
        "name": "DPO Lower Chitral",
        "type": "police",
        "district": "Lower Chitral",
        "phone": "0943-412077",
        "website": "https://chitralpolice.gov.pk/",
        "source_url": "https://www.kppolice.gov.pk/phone-directory.php?tid=2",
        "last_verified": LAST_VERIFIED,
        "confidence": "high",
        "verified": True,
        "free_service": None,
        "notes": "The KP Police phone directory and Chitral Police list the same number.",
    },
    {
        "id": "chitral_police_directory",
        "name": "Chitral Police directory (control room and listed stations)",
        "type": "police_directory",
        "district": "Lower Chitral",
        "phone": "Control room 0943-412959; SP Investigation 0943-413808; City police station 0943-412913; Drosh 0943-480207; Lotkoh 0943-488015; Koghuzi 0943-477009; Ayun 0943-490007; SDPO Drosh 0943-480308",
        "website": "https://chitralpolice.gov.pk/",
        "source_url": "https://chitralpolice.gov.pk/",
        "last_verified": LAST_VERIFIED,
        "confidence": "high",
        "verified": True,
        "free_service": None,
        "notes": "These are the numbers listed in the Chitral Police directory. No Upper Chitral police contact was confirmed in that directory.",
    },
    {
        "id": "rescue_1122_lower_chitral",
        "name": "Rescue 1122 (KP)",
        "type": "emergency_rescue",
        "district": "Lower Chitral",
        "phone": "1122",
        "website": "https://www.rescue.gov.pk/",
        "source_url": "https://www.app.com.pk/?p=1271723",
        "last_verified": LAST_VERIFIED,
        "confidence": "high",
        "verified": True,
        "free_service": None,
        "notes": "Dial 1122 in KP. Reporting confirms Rescue 1122 responded to emergencies in Lower Chitral. Upper Chitral service availability is not confirmed.",
    },
    {
        "id": "upper_chitral_police_community",
        "name": "Booni and Mastuj police station numbers (older community directory)",
        "type": "police_directory",
        "district": "Upper Chitral",
        "phone": "Booni police station 0943-470027; Mastuj 0943-486026",
        "website": None,
        "source_url": "https://chitraltoday.net/phone-numbers/",
        "last_verified": LAST_VERIFIED,
        "confidence": "low",
        "verified": False,
        "free_service": None,
        "notes": "Older community-directory numbers; not confirmed by an official Upper Chitral source. Not shown in Upper Chitral referrals.",
    },
    {
        "id": "mohr_1099",
        "name": "Ministry of Human Rights helpline",
        "type": "national_legal_and_rights_helpline",
        "district": "national",
        "phone": "1099; WhatsApp 0333-9085709",
        "website": "https://www.mohr.gov.pk/",
        "source_url": "https://www.mohr.gov.pk/Detail/YWRiYjU0NzktMGE2Zi00NDYyLTljNzktMTA2N2M2MjBlZWZl",
        "last_verified": LAST_VERIFIED,
        "confidence": "high",
        "verified": True,
        "free_service": True,
        "notes": "Toll-free helpline for free legal advice, counselling and referral. The directory reports weekday hours of 8:30 AM to 9:00 PM; confirm current hours directly.",
    },
    {
        "id": "kp_human_rights_directorate",
        "name": "KP Directorate of Human Rights",
        "type": "human_rights_helpline",
        "district": "Chitral-wide",
        "phone": "0800-11180; Peshawar 091-9213068/69",
        "website": None,
        "source_url": "https://shirkatgah.org/wp-content/uploads/2024/02/Referral-Directory-KPK_GAC.pdf",
        "last_verified": LAST_VERIFIED,
        "confidence": "medium",
        "verified": False,
        "free_service": None,
        "notes": "Listed in a secondary 2024 KP referral directory. Current operation and Chitral coverage are unconfirmed.",
    },
    {
        "id": "nccia_cybercrime",
        "name": "National Cyber Crime Investigation Agency (NCCIA)",
        "type": "cybercrime_reporting",
        "district": "national",
        "phone": "051-9106691; 1799",
        "website": None,
        "source_url": "https://www.app.com.pk/domestic/national-cyber-crime-investigation-agency-becomes-independent-authority/",
        "last_verified": LAST_VERIFIED,
        "confidence": "medium",
        "verified": False,
        "free_service": None,
        "notes": "The supplied sources conflict about helpline details and neither establishes a current official reporting route. Confirm both numbers and the route before relying on them.",
    },
    {
        "id": "madadgaar_1098",
        "name": "Madadgaar helpline",
        "type": "gender_based_violence_helpline",
        "district": "national",
        "phone": "1098",
        "website": None,
        "source_url": "https://hrcp-web.org/hrcpweb/complaints-cell/",
        "last_verified": LAST_VERIFIED,
        "confidence": "low",
        "verified": False,
        "free_service": None,
        "notes": "The supplied secondary listing does not confirm current service operation or Chitral coverage.",
    },
    {
        "id": "kp_bolo_helpline",
        "name": "KP BOLO helpline",
        "type": "gender_based_violence_helpline",
        "district": "Chitral-wide",
        "phone": "0800-22227",
        "website": None,
        "source_url": "https://nomoredirectory.org/pakistan/",
        "last_verified": LAST_VERIFIED,
        "confidence": "low",
        "verified": False,
        "free_service": None,
        "notes": "Listed in a secondary directory; current operation and Chitral coverage are unconfirmed.",
    },
    {
        "id": "dc_lower_chitral",
        "name": "DC Lower Chitral office (older community directory)",
        "type": "district_administration",
        "district": "Lower Chitral",
        "phone": "0943-412055",
        "website": None,
        "source_url": "https://chitraltoday.net/phone-numbers/",
        "last_verified": LAST_VERIFIED,
        "confidence": "low",
        "verified": False,
        "free_service": None,
        "notes": "Older community-directory contact; confirm directly before relying on it.",
    },
    {
        "id": "nadra_chitral",
        "name": "NADRA Chitral (older community directory)",
        "type": "identity_service",
        "district": "Lower Chitral",
        "phone": "0943-413548",
        "website": None,
        "source_url": "https://chitraltoday.net/phone-numbers/",
        "last_verified": LAST_VERIFIED,
        "confidence": "low",
        "verified": False,
        "free_service": None,
        "notes": "Older community-directory contact; confirm directly before relying on it.",
    },
]

_DIRECTORY_BY_ID = {entry["id"]: entry for entry in CHITRAL_LEGAL_DIRECTORY}

_HIGH_RISK_DOMAINS = {
    "child_protection",
    "harassment_protection",
    "fraud_cybercrime",
}
_HIGH_RISK_SUBTYPES = {
    "child_protection",
    "child_marriage_reporting",
    "child_labour",
    "domestic_violence",
    "workplace_harassment",
    "online_harassment",
    "cyberstalking",
    "general_harassment_complaint",
    "online_fraud",
    "electronic_fraud",
    "identity_misuse",
    "electronic_identity_misuse",
}
_UNRESOLVED_STATUSES = {
    "evidence_unavailable",
    "evidence_unresolved",
    "unable_to_verify",
}
_DETENTION_TERMS = (
    "prisoner",
    "detained",
    "detention",
    "arrested",
    "arrest",
    "jail",
    "custody",
    "undertrial",
    "under-trial",
)

CHITRAL_COVERAGE_LIMITS = (
    "The DLEC application form and contact person could not be confirmed.",
    "Official Upper Chitral court, police, and DLEC contacts could not be confirmed.",
    "A women's crisis centre or Dar-ul-Aman, and the Dispute Resolution Council in Chitral, could not be confirmed.",
    "Whether LAJA serves Chitral or KP could not be confirmed; Chitral users are not referred to LAJA.",
)


def _chitral_district(*location_values: object) -> str | None:
    location = " ".join(
        value.casefold()
        for value in location_values
        if isinstance(value, str)
    )
    if "upper chitral" in location or "booni" in location or "mastuj" in location:
        return "Upper Chitral"
    if "lower chitral" in location or "drosh" in location or "ayun" in location:
        return "Lower Chitral"
    if "chitral" in location:
        return "Chitral-wide"
    return None


def _in_prison_or_criminal_detention(intake: dict, pipeline_result: dict) -> bool:
    text = " ".join(
        value.casefold()
        for value in [
            intake.get("problem_summary"),
            *(intake.get("facts") or []),
            pipeline_result.get("user_message"),
        ]
        if isinstance(value, str)
    )
    return any(term in text for term in _DETENTION_TERMS)


def _directory_entry(resource_id: str) -> dict:
    return dict(_DIRECTORY_BY_ID[resource_id])


def _filter_upper_chitral(entries: list[dict], district: str | None) -> list[dict]:
    if district != "Upper Chitral":
        return entries
    return [
        entry for entry in entries
        if entry["verified"] is True
        and entry["district"] in {"Upper Chitral", "Chitral-wide", "national"}
    ]


def build_referral_context(pipeline_result: dict) -> dict:
    intake = pipeline_result.get("intake") or {}
    classification = pipeline_result.get("classification") or {}
    urgency = str(intake.get("urgency") or "unclear").strip().casefold()
    intake_category = str(intake.get("category") or "unclear").strip().casefold()
    legal_domain = str(classification.get("legal_domain") or "unclear").strip().casefold()
    legal_subtype = str(classification.get("legal_subtype") or "unclear").strip().casefold()
    status = str(pipeline_result.get("status") or "").strip().casefold()
    district = _chitral_district(
        intake.get("location"),
        classification.get("locality"),
        classification.get("jurisdiction"),
    )

    is_high_risk = (
        legal_domain in _HIGH_RISK_DOMAINS
        or intake_category in _HIGH_RISK_DOMAINS
        or legal_subtype in _HIGH_RISK_SUBTYPES
    )
    has_urgent_need = urgency in {"emergency", "urgent"}
    needs_legal_aid = intake.get("needs_legal_aid") is True
    is_unresolved = status in _UNRESOLVED_STATUSES
    cybercrime = legal_domain == "fraud_cybercrime" or legal_subtype in {
        "online_fraud",
        "electronic_fraud",
        "cyberstalking",
        "online_harassment",
        "electronic_identity_misuse",
    }
    is_detention_case = _in_prison_or_criminal_detention(intake, pipeline_result)

    reasons = []
    if urgency == "emergency":
        reasons.append("emergency")
    elif urgency == "urgent":
        reasons.append("urgent")
    if is_high_risk:
        reasons.append("high_risk")
    if needs_legal_aid:
        reasons.append("legal_aid")
    if is_detention_case:
        reasons.append("criminal_detention")
    if status == "evidence_unavailable":
        reasons.append("evidence_unavailable")
    elif status in {"evidence_unresolved", "unable_to_verify"}:
        reasons.append("evidence_unresolved")

    if not (
        has_urgent_need
        or is_high_risk
        or needs_legal_aid
        or is_unresolved
        or is_detention_case
    ):
        return {
            "recommended": False,
            "urgency": urgency,
            "reasons": [],
            "district": district,
            "upper_chitral_contacts_unconfirmed": district == "Upper Chitral",
            "list_not_exhaustive": True,
            "coverage_limits": list(CHITRAL_COVERAGE_LIMITS),
            "resources": [],
        }

    resource_ids = []
    if has_urgent_need:
        resource_ids.append("chitral_police_emergency")
        if district == "Lower Chitral":
            resource_ids.append("rescue_1122_lower_chitral")
    if needs_legal_aid or is_unresolved:
        if district != "Upper Chitral":
            resource_ids.extend((
                "dlec",
                "chitral_lower_court",
                "chitral_bar_associations",
                "kp_bar_council",
            ))
        if is_detention_case:
            resource_ids.append("kp_legal_aid_desk")
    if needs_legal_aid:
        resource_ids.append("mohr_1099")
    if is_high_risk:
        resource_ids.extend(("mohr_1099", "chitral_police_emergency"))
    if cybercrime:
        resource_ids.append("nccia_cybercrime")
    if legal_subtype in {
        "domestic_violence",
        "child_protection",
        "child_marriage_reporting",
        "workplace_harassment",
        "general_harassment_complaint",
    }:
        resource_ids.extend(("madadgaar_1098", "kp_bolo_helpline"))
    if is_detention_case:
        resource_ids.append("kp_legal_aid_desk")

    resource_ids = list(dict.fromkeys(resource_ids))
    entries = [_directory_entry(resource_id) for resource_id in resource_ids]
    entries = _filter_upper_chitral(entries, district)

    # Emergency contacts lead every urgent list; entries stay in curated order.
    if has_urgent_need:
        entries.sort(
            key=lambda entry: (
                0 if entry["id"] == "chitral_police_emergency" else
                1 if entry["id"] == "rescue_1122_lower_chitral" else 2
            )
        )

    return {
        "recommended": True,
        "urgency": urgency,
        "emergency": urgency == "emergency",
        "reasons": reasons,
        "district": district,
        "upper_chitral_contacts_unconfirmed": district == "Upper Chitral",
        "list_not_exhaustive": True,
        "coverage_limits": list(CHITRAL_COVERAGE_LIMITS),
        "resources": entries,
    }
