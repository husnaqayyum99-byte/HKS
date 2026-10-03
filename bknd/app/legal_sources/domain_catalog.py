"""Deterministic official-catalog search candidates for supported subtypes."""

LAW_CANDIDATES_BY_SUBTYPE = {
    "lost_cnic": ("NADRA Ordinance, 2000",),
    "cnic_renewal": ("NADRA Ordinance, 2000",),
    "cnic_correction": ("NADRA Ordinance, 2000",),
    "marriage_registration": (
        "Khyber Pakhtunkhwa Births, Deaths, Marriages and Divorce/Dissolution Registration Rules, 2021",
    ),
    "divorce_registration": (
        "Khyber Pakhtunkhwa Births, Deaths, Marriages and Divorce/Dissolution Registration Rules, 2021",
    ),
    "child_labour": (
        "Khyber Pakhtunkhwa Prohibition of Employment of Children Act, 2015",
    ),
    "child_protection": (
        "Khyber Pakhtunkhwa Child Protection and Welfare Act, 2010",
    ),
    "workplace_harassment": (
        "Protection Against Harassment of Women at the Workplace Act, 2010",
    ),
    "domestic_violence": (
        "Khyber Pakhtunkhwa Domestic Violence Against Women Prevention and Protection Act, 2021",
    ),
    "online_fraud": ("Prevention of Electronic Crimes Act, 2016",),
    "online_harassment": ("Prevention of Electronic Crimes Act, 2016",),
    "cyberstalking": ("Prevention of Electronic Crimes Act, 2016",),
    "electronic_fraud": ("Prevention of Electronic Crimes Act, 2016",),
    "electronic_identity_misuse": ("Prevention of Electronic Crimes Act, 2016",),
    "succession_certificate": (
        "Khyber Pakhtunkhwa Letters of Administration and Succession Certificates Act, 2021",
    ),
    "letter_of_administration": (
        "Khyber Pakhtunkhwa Letters of Administration and Succession Certificates Act, 2021",
    ),
    "women_ownership_rights": (
        "Khyber Pakhtunkhwa Enforcement of Women Ownership Rights Act, 2012",
    ),
    "road_accident": ("Provincial Motor Vehicles Ordinance, 1965",),
    "vehicle_damage": ("Provincial Motor Vehicles Ordinance, 1965",),
    "compensation_dispute": ("Provincial Motor Vehicles Ordinance, 1965",),
    "responsibility_dispute": ("Provincial Motor Vehicles Ordinance, 1965",),
    "traffic_violation": ("Provincial Motor Vehicles Ordinance, 1965",),
    "driving_licensing": ("Provincial Motor Vehicles Ordinance, 1965",),
    "fir_navigation": (
        "Code of Criminal Procedure, 1898",
        "Khyber Pakhtunkhwa Police Act",
    ),
    "fir_registration_difficulty": (
        "Code of Criminal Procedure, 1898",
        "Khyber Pakhtunkhwa Police Act",
    ),
    "police_complaint": ("Khyber Pakhtunkhwa Police Act",),
}


def law_search_candidates(classification_data: dict) -> list[str]:
    subtype = str(classification_data.get("legal_subtype") or "").strip().casefold()
    jurisdiction = str(classification_data.get("jurisdiction") or "").strip().casefold()
    if jurisdiction not in {"khyber pakhtunkhwa", "kp", "pakistan", "federal"}:
        return []
    candidates = LAW_CANDIDATES_BY_SUBTYPE.get(subtype, ())
    if jurisdiction not in {"khyber pakhtunkhwa", "kp"}:
        federal_titles = {
            "NADRA Ordinance, 2000",
            "Prevention of Electronic Crimes Act, 2016",
            "Code of Criminal Procedure, 1898",
        }
        candidates = [title for title in candidates if title in federal_titles]
    return list(dict.fromkeys(candidates))