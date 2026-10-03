import json

from pydantic import BaseModel

from app.services.ai_service import generate_response


class ClassificationResult(BaseModel):
    legal_domain: str = "unclear"
    legal_subtype: str = "unclear"
    jurisdiction: str = "Unknown"
    locality: str = "unknown"
    matter_type: str = "unclear"
    requires_local_procedure: bool = False
    confidence: str = "low"


def classify_case(intake_data: dict) -> ClassificationResult:
    prompt = f"""
You are the Classification Agent for Apna Wakeel.

Apna Wakeel is a Pakistan-focused legal information and navigation
system.

Your job is to classify the user's case based ONLY on the intake
information provided.

Do NOT:
- give legal advice
- cite laws
- invent facts
- invent legal authorities
- make a final legal conclusion
- assume facts that are not present

Determine:

1. legal_domain
2. legal_subtype
3. jurisdiction
4. locality
5. matter_type
6. requires_local_procedure
7. confidence

Use one primary legal_domain from:
identity_documents, government_services, family_marriage,
child_protection, harassment_protection, fraud_cybercrime,
land_revenue, inheritance_succession, traffic_accident,
traffic_services, police_reporting, property, employment, tenancy,
civil, other, unclear.

Use legal_subtype to preserve distinctions. Examples include lost_cnic,
cnic_renewal, cnic_correction, domicile_application,
domicile_verification, marriage_registration, divorce_registration,
child_marriage_reporting, child_labour, child_protection,
workplace_harassment, domestic_violence, online_harassment,
cyberstalking, general_harassment_complaint, online_fraud,
electronic_fraud, identity_misuse, electronic_identity_misuse,
offline_fraud, land_dispute,
land_boundary_dispute, land_record_fard, revenue_dispute,
inheritance_dispute, succession_certificate, letter_of_administration,
road_accident, vehicle_damage, compensation_dispute,
responsibility_dispute, traffic_violation, driving_licensing,
vehicle_service, fir_navigation, fir_registration_difficulty,
police_complaint, or unclear.

Distinguish closely related situations from the user-provided facts:
- Harassment depends on context: workplace, domestic, online/cyber, or
    general complaint. Do not use workplace law for other contexts.
- Fraud is not automatically cybercrime. Use an electronic subtype only
    when the facts describe relevant electronic/online conduct.
- Online conduct can justify researching an electronic-crime source, but
    does not by itself establish that a PECA offence occurred.
- Distinguish road accidents and vehicle-damage disputes from violations,
    licensing, and vehicle services.
- A reported incident is not proof that a crime occurred. Prefer a
    reporting/navigation subtype; do not decide criminal liability.
- Do not calculate or declare inheritance shares.
- If the facts do not distinguish a subtype, use unclear and ask only a
    material clarification question in the follow-up stage.

Jurisdiction should identify the relevant level, such as:

- Pakistan
- Khyber Pakhtunkhwa
- Federal
- Unknown

Locality should contain a city/district/area if known.
Otherwise use "unknown".

Possible confidence values:

- high
- medium
- low
- unclear

Set requires_local_procedure to true when the matter may depend on
local government, district, provincial, police, court, or other
location-specific procedures.

Return ONLY valid JSON.

Required JSON structure:

{{
    "legal_domain": "string",
    "legal_subtype": "string",
    "jurisdiction": "string",
    "locality": "string",
    "matter_type": "string",
    "requires_local_procedure": true,
    "confidence": "string"
}}

Intake information:

{json.dumps(intake_data, indent=2)}
"""

    raw_response = generate_response(prompt)

    try:
        data = json.loads(raw_response)
        return ClassificationResult(**data)

    except (json.JSONDecodeError, ValueError) as e:
        raise ValueError(
            f"Classification Agent returned invalid data: {e}"
        )