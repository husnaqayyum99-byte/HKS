import json
import logging
from typing import Any
from urllib.parse import urlparse

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field
from groq import RateLimitError

from app.services.ai_service import generate_response
from app.agents.orchestrator import process_case
from app.legal_sources.source_registry import LEGAL_SOURCES

router = APIRouter(
    prefix="/api",
    tags=["Legal Analysis"],
)

logger = logging.getLogger(__name__)


class FollowUpRequest(BaseModel):
    problem: str
    province: str | None = ""
    language: str | None = "en"


class FollowUpQuestion(BaseModel):
    id: str
    text: str
    type: str = "yesno"  # "choice" | "yesno" | "text"
    hint: str | None = None
    options: list[str] | None = None


class AnswerItem(BaseModel):
    questionId: str | None = None
    question: str
    answer: str


class AnalyzeRequest(BaseModel):
    problem: str
    province: str | None = ""
    answers: list[AnswerItem] = Field(default_factory=list)
    language: str | None = "en"


def normalize_analysis(result: dict, problem: str, province: str, language: str) -> dict:
    is_urdu = "ur" in language and "roman" not in language
    is_roman = "roman" in language

    # Legal area
    legal_area = result.get("legalArea")
    if not isinstance(legal_area, dict) or not legal_area.get("name"):
        legal_area = {
            "name": "جائیداد اور شہری حقوق" if is_urdu else "Property & Civil Law" if not is_roman else "Property aur Civil Law",
            "tag": "قانونی تنازع" if is_urdu else "Legal Dispute & Rights" if not is_roman else "Qanooni Tanaza",
        }

    # Explanation
    explanation = result.get("explanation")
    if not isinstance(explanation, list) or len(explanation) == 0:
        if isinstance(explanation, str):
            explanation = [explanation]
        else:
            explanation = [
                "آپ کے بیان کردہ مسئلے کا تفصیلی قانونی جائزہ لیا گیا ہے۔ پاکستانی قانون کے تحت آپ کے پاس قانونی چارہ جوئی کے حقوق حاصل ہیں۔" if is_urdu else
                "Based on your statement, you have clear legal rights and procedural remedies available under Pakistani law." if not is_roman else
                "Aap ke maslay ka tafseeli qanooni jaiza liya gaya hai. Pakistani qanoon ke teht aap ke paas qanooni chara joi ke huqooq mojood hain."
            ]

    # Relevant info
    relevant_info = result.get("relevantInfo")
    if not isinstance(relevant_info, list) or len(relevant_info) == 0:
        relevant_info = [
            {
                "title": "قانونی دائرہ اختیار" if is_urdu else "Legal Jurisdiction" if not is_roman else "Qanooni Daira Ikhtiar",
                "text": f"یہ معاملہ {province or 'پاکستان'} کی متعلقہ عدالت یا مجاز اتھارٹی کے دائرہ اختیار میں آتا ہے۔" if is_urdu else
                        f"This matter falls under the jurisdiction of the relevant forum in {province or 'Pakistan'}." if not is_roman else
                        f"Yeh mamla {province or 'Pakistan'} ki mutaaliqa adalat ya authority ke daira ikhtiar mein aata hai.",
            },
            {
                "title": "شہری حقوق اور تحفظ" if is_urdu else "Citizen Rights & Protection" if not is_roman else "Shehri Huqooq",
                "text": "کسی بھی فریق کو قانون ہاتھ میں لینے کی اجازت نہیں ہے۔ ضابطے کے مطابق قانونی نوٹس اور کارروائی ضروری ہے۔" if is_urdu else
                        "No party is legally entitled to take the law into their own hands without due judicial process." if not is_roman else
                        "Kisi bhi fareeq ko qanoon hath mein lenay ki ijazat nahi hai.",
            },
        ]

    # Authority
    authority = result.get("authority")
    if not isinstance(authority, dict) or not authority.get("name"):
        authority = {
            "name": "سول کورٹ / متعلقہ ضلعی اتھارٹی" if is_urdu else "Civil Court / District Authority" if not is_roman else "Civil Court / Zillai Authority",
            "description": "متعلقہ فورم جو اس قسم کے تنازعات کی باضابطہ سماعت اور احکامات جاری کرنے کا مجاز ہے۔" if is_urdu else
                           "The competent local legal forum authorized to issue injunctions, relief, and binding orders." if not is_roman else
                           "Mutaaliqa forum jo qanooni ehkaam jari karnay ka majaz hai.",
            "howToReach": [
                "اپنے قریبی ڈسٹرکٹ یا تحصیل ہیڈکوارٹر میں متعلقہ دفتر سے رابطہ کریں۔" if is_urdu else "Visit the nearest District or Tehsil court complex." if not is_roman else "Qareebi District ya Tehsil court se rabta karein.",
                "اصل شناختی کارڈ اور تمام تصدیق شدہ دستاویزات ہمراہ رکھیں۔" if is_urdu else "Carry your original CNIC and all relevant documents." if not is_roman else "Asal CNIC aur documents sath le jayein.",
                "ڈسٹرکٹ بار کے لیگل ایڈ ڈیسک سے مفت ابتدائی مشورہ حاصل کریں۔" if is_urdu else "Consult the District Bar Association legal aid desk if needed." if not is_roman else "District Bar ke legal aid desk se mashwara karein.",
            ],
        }

    # Timeline
    timeline = result.get("timeline")
    if not isinstance(timeline, list) or len(timeline) == 0:
        timeline = [
            {
                "title": "مرحلہ ۱: دستاویزات اور ثبوت کی تیاری" if is_urdu else "Phase 1: Evidence Gathering" if not is_roman else "Marhala 1: Dastawizat ki tayari",
                "time": "۱ سے ۳ دن" if is_urdu else "1 to 3 days" if not is_roman else "1 se 3 din",
                "detail": "شناختی کارڈ، معاہدات، رسیدیں اور رابطوں کا ریکارڈ محفوظ کریں۔" if is_urdu else "Compile CNIC, contracts, receipts, and communication logs." if not is_roman else "CNIC, contracts aur receipts jama karein.",
            },
            {
                "title": "مرحلہ ۲: قانونی نوٹس یا باضابطہ درخواست" if is_urdu else "Phase 2: Legal Notice / Formal Application" if not is_roman else "Marhala 2: Qanooni Notice",
                "time": "۱ سے ۲ ہفتے" if is_urdu else "1 to 2 weeks" if not is_roman else "1 se 2 haftay",
                "detail": "وکیل کے ذریعے فریق مخالف کو باضابطہ نوٹس بھجوائیں۔" if is_urdu else "Serve a formal legal notice giving reasonable opportunity to comply." if not is_roman else "Wakeel ke zariye notice bhijwayein.",
            },
            {
                "title": "مرحلہ ۳: عدالتی کارروائی یا تصفیہ" if is_urdu else "Phase 3: Formal Proceedings or Settlement" if not is_roman else "Marhala 3: Adalati Karwayi",
                "time": "۱ سے ۳ ماہ" if is_urdu else "1 to 3 months" if not is_roman else "1 se 3 mahinay",
                "detail": "عدالت میں دعویٰ دائر کریں یا باہمی تصفیے کے تحت فیصلہ حاصل کریں۔" if is_urdu else "Initiate formal suit or conclude through mediated settlement." if not is_roman else "Adalat mein case daire karein ya settlement karein.",
            },
        ]

    # Documents
    documents = result.get("documents")
    if not isinstance(documents, list) or len(documents) == 0:
        documents = [
            "قومی شناختی کارڈ کی کاپی" if is_urdu else "Original CNIC and photocopies" if not is_roman else "CNIC copy",
            "متعلقہ تحریری معاہدہ یا رجسٹری" if is_urdu else "Relevant agreement, deed, or allotment letter" if not is_roman else "Written agreement ya deed",
            "ادائیگی کی رسیدیں یا بینک اسٹیٹمنٹ" if is_urdu else "Payment receipts, invoices, or bank records" if not is_roman else "Payment receipts ya bank records",
            "فریق مخالف کا نام، پتہ اور رابطہ نمبر" if is_urdu else "Opposing party full name, address, and contact" if not is_roman else "Opposite party details",
        ]

    # Evidence
    evidence = result.get("evidence")
    if not isinstance(evidence, list) or len(evidence) == 0:
        evidence = [
            "تاریخ وار پیغامات، ای میلز یا تحریری پیغامات" if is_urdu else "Screenshots of text messages, WhatsApp chats, or emails" if not is_roman else "Chat screenshots aur message history",
            "موقع کی تصاویر، ویڈیوز یا جائے وقوعہ کا ثبوت" if is_urdu else "Dated photographs, videos, or site inspection notes" if not is_roman else "Dated photos ya video evidence",
            "گواہان کے بیانات اور ان کے شناختی کوائف" if is_urdu else "Names and contact details of neutral eyewitnesses" if not is_roman else "Gawahon ke naam aur contact",
            "متعلقہ محکمے یا پولیس کو دی گئی سابقہ درخواستیں" if is_urdu else "Copies of any earlier complaints or applications filed" if not is_roman else "Pehlay di gayi complaints ki copies",
        ]

    # Action Plan
    action_plan = result.get("actionPlan")
    if not isinstance(action_plan, list) or len(action_plan) == 0:
        action_plan = [
            {
                "when": "آج" if is_urdu else "Today" if not is_roman else "Aaj",
                "title": "قانون ہاتھ میں نہ لیں اور شواہد محفوظ کریں" if is_urdu else "Stay safe and preserve all records" if not is_roman else "Shawahid mehfooz karein",
                "detail": "کسی بھی قسم کے تصادم سے گریز کریں اور تمام پیغامات کے اسکرین شاٹ محفوظ کر لیں۔" if is_urdu else "Avoid direct verbal or physical confrontation; preserve digital and paper trails." if not is_roman else "Kisi larai se bachein aur saboot mehfooz rakhein.",
            },
            {
                "when": "اس ہفتے" if is_urdu else "This Week" if not is_roman else "Is Haftay",
                "title": "دستاویزات کی فائل تیار کریں" if is_urdu else "Prepare your document dossier" if not is_roman else "Documents file tayar karein",
                "detail": "اصل دستاویزات محفوظ رکھیں اور کم از کم تین فوٹو کاپیاں تیار کریں۔" if is_urdu else "Keep original documents safe and make 3 sets of photocopies." if not is_roman else "Photocopies ke 3 sets bana lein.",
            },
            {
                "when": "اگلا قدم" if is_urdu else "Next Step" if not is_roman else "Agla Qadam",
                "title": "قانونی وکیل یا لیگل ایڈ سے رجوع کریں" if is_urdu else "Seek licensed legal counsel" if not is_roman else "Licensed Wakeel se mashwara karein",
                "detail": "متعلقہ وکیل سے رجوع کر کے باضابطہ نوٹس یا دعویٰ دائر کرنے کی کارروائی شروع کریں۔" if is_urdu else "Consult a practitioner in the relevant field to issue formal notice." if not is_roman else "Mutaaliqa wakeel se notice bhijwane ka rabta karein.",
            },
        ]

    # Lawyer recommendation
    lawyer_type = result.get("lawyerType")
    if not isinstance(lawyer_type, dict) or not lawyer_type.get("type"):
        lawyer_type = {
            "type": "ماہر دیوانی و جائیداد وکیل" if is_urdu else "Civil & Property Litigation Lawyer" if not is_roman else "Civil & Property Lawyer",
            "reason": "یہ وکیل عدالتی حکم امتناعی اور حقوق کی بحالی کی کارروائی میں مکمل مہارت رکھتا ہے۔" if is_urdu else "This specialist regularly handles injunctions, recovery of rights, and civil remedies." if not is_roman else "Yeh wakeel civil remedies aur stay orders mein mahir hota hai.",
            "prepare": [
                "واقعات کی تاریخ وار تفصیل" if is_urdu else "Chronological timeline of events" if not is_roman else "Tareekh war waqiyat ki list",
                "تمام کاغذی و ڈیجیٹل ثبوت" if is_urdu else "Copies of title deeds, lease, or receipts" if not is_roman else "Saboot aur agreements",
                "فریق مخالف کا مکمل پتہ" if is_urdu else "Full contact details of opposing parties" if not is_roman else "Mukhalif fareeq ka pata",
            ],
        }

    # Case Assessment
    case_assessment = result.get("caseAssessment")
    if not isinstance(case_assessment, dict) or not case_assessment.get("summary"):
        case_assessment = {
            "summary": "آپ کے فراہم کردہ حقائق کی روشنی میں آپ کا موقف معقول بنیادوں پر استوار ہے، تاہم باضابطہ دستاویزات کا ہونا ضروری ہے۔" if is_urdu else "Based on the facts provided, your stance is legally plausible, subject to formal documentation and notice." if not is_roman else "Aap ke faraham karda haqaiq ki roshni mein aap ka moaqqaf qanooni tor par wazan rakhta hai.",
            "strengths": [
                "آپ کے پاس ابتدائی بیان اور موقف واضح ہے" if is_urdu else "Clear factual narrative and specific grievance" if not is_roman else "Wazeh grievance aur bayan",
                "قانون ہاتھ میں نہ لے کر پرامن حل کی کوشش" if is_urdu else "Peaceful conduct without resorting to self-help violence" if not is_roman else "Pur-aman tareeqe se hal ki koshish",
            ],
            "weaknesses": [
                "باضابطہ تحریری نوٹس کا ابھی بھجوایا جانا باقی ہے" if is_urdu else "Formal statutory notice has not yet been served" if not is_roman else "Formal notice abhi nahi bheja gaya",
            ],
            "missingInfo": [
                "فریق مخالف کا تحریری موقف یا جواب" if is_urdu else "Opposing party written defense or written notice" if not is_roman else "Mukhalif fareeq ka tehreeri jawab",
            ],
            "evidenceStrength": "moderate",
            "preparedness": "reasonable",
            "improve": [
                "تحریری رسیدیں اور گواہان کے رابطے اکٹھے کریں" if is_urdu else "Collect stamped receipts and written statements from witnesses" if not is_roman else "Receipts aur gawahon ke rabtay jama karein",
            ],
        }

    # Sources
    sources = result.get("sources")
    if not isinstance(sources, list):
        sources = []

    # Disclaimer
    disclaimer = result.get("disclaimer") or (
        "یہ معلومات صرف رہنمائی اور آگاہی کے لیے فراہم کی گئی ہیں اور یہ باضابطہ وکیل-مؤکل کے رشتے کا متبادل نہیں ہیں۔" if is_urdu else
        "This legal navigation is generated for informational purposes under Pakistani law and does not replace formal advocate consultation." if not is_roman else
        "Yeh maloomat sirf rehnumai ke liye hain aur wakeel ke formal mashwaray ka mutabadil nahi hain."
    )

    return {
        "isDemo": not bool(result),
        "legalArea": legal_area,
        "explanation": explanation,
        "relevantInfo": relevant_info,
        "authority": authority,
        "timeline": timeline,
        "documents": documents,
        "evidence": evidence,
        "actionPlan": action_plan,
        "lawyerType": lawyer_type,
        "caseAssessment": case_assessment,
        "sources": sources,
        "disclaimer": disclaimer,
        "intake": {
            "problem_summary": problem[:160] + ("..." if len(problem) > 160 else ""),
        },
        "classification": {
            "jurisdiction": province or "Pakistan",
            "locality": province or "Pakistan",
        },
    }


@router.post("/follow-up-questions")
async def get_follow_up_questions(data: FollowUpRequest):
    """
    Generate targeted legal follow-up questions based on the user's issue and province.
    """
    problem = data.problem.strip()
    province = (data.province or "").strip()
    language = (data.language or "en").lower()

    if not problem:
        raise HTTPException(status_code=400, detail="Problem description cannot be empty")

    lang_instruction = "Respond in English."
    if "ur" in language and "roman" not in language:
        lang_instruction = "Respond in Urdu (Nastaliq script)."
    elif "roman" in language:
        lang_instruction = "Respond in Roman Urdu (Urdu written in English script)."

    prompt = f"""
You are the Legal Intake Assistant for "Apna Wakeel", a Pakistan-focused legal guidance platform.
The user has described a legal issue. Generate 3 to 4 clear follow-up questions to gather necessary factual details.

User Issue: {problem}
Province/Territory: {province or 'Pakistan (Federal/Unspecified)'}
Language Requirement: {lang_instruction}

Guidelines:
1. Provide between 3 and 4 questions.
2. Question 1 should be a multiple-choice question (type: "choice") with 3-4 options.
3. Question 2 should be a yes/no question (type: "yesno") regarding official documents or police/court interaction.
4. Question 3 can be a yes/no (type: "yesno") or text question (type: "text") about threats, possession, or dates.
5. Question 4 can be a text question (type: "text") for any additional relevant details.
6. Provide short, clear questions in the requested language.
7. Return ONLY valid JSON adhering to the schema below.

JSON Format:
{{
  "questions": [
    {{
      "id": "q1",
      "text": "Question text",
      "type": "choice",
      "hint": "Brief hint or null",
      "options": ["Option 1", "Option 2", "Option 3", "Option 4"]
    }},
    {{
      "id": "q2",
      "text": "Question text",
      "type": "yesno",
      "hint": "Brief hint or null"
    }},
    {{
      "id": "q3",
      "text": "Question text",
      "type": "text",
      "hint": "Brief hint or null"
    }}
  ]
}}
"""

    try:
        content = generate_response(prompt)
        parsed = json.loads(content)

        questions = parsed.get("questions", [])
        if not questions:
            raise ValueError("No questions returned by model")

        normalized = []
        for idx, q in enumerate(questions, start=1):
            qid = q.get("id") or f"q{idx}"
            qtext = q.get("text") or q.get("question") or ""
            qtype = q.get("type", "yesno")
            if qtype not in ["choice", "yesno", "text"]:
                qtype = "choice" if q.get("options") else "yesno"

            normalized.append({
                "id": qid,
                "text": qtext,
                "type": qtype,
                "hint": q.get("hint"),
                "options": q.get("options") if qtype == "choice" else None,
            })

        return {"questions": normalized}

    except RateLimitError:
        logger.warning("Follow-up question provider rate limited the request")
        raise HTTPException(status_code=429, detail="legal.aiRateLimited") from None
    except Exception as error:
        logger.warning("Follow-up question generation failed: type=%s", type(error).__name__)
        raise HTTPException(status_code=503, detail="legal.aiUnavailable") from None


@router.post("/analyze")
async def analyze_problem(data: AnalyzeRequest):
    """
    Run complete legal analysis for Pakistan jurisdiction and return structured findings.
    """
    problem = data.problem.strip()
    province = (data.province or "").strip()
    language = (data.language or "en").lower()

    if not problem:
        raise HTTPException(status_code=400, detail="Problem description cannot be empty")

    answers_summary = "\n".join(f"- {answer.question}: {answer.answer}" for answer in data.answers if answer.answer)
    user_message = problem
    if answers_summary:
        user_message = f"{problem}\n\nAdditional facts provided by the user:\n{answers_summary}"
    try:
        pipeline = process_case(user_message, language=language)
    except RateLimitError:
        logger.warning("Legal analysis provider rate limited the request")
        raise HTTPException(status_code=429, detail="legal.aiRateLimited") from None
    except Exception as error:
        logger.error("Legal analysis failed: type=%s", type(error).__name__)
        raise HTTPException(status_code=503, detail="legal.aiUnavailable") from None

    if pipeline.get("status") == "needs_clarification":
        intake = pipeline.get("intake") or {}
        classification = pipeline.get("classification") or {}
        follow_up = pipeline.get("follow_up") or {}
        return {
            "isDemo": False,
            "status": "needs_clarification",
            "follow_up_questions": (follow_up.get("questions") or [])[:3],
            "legalArea": {
                "name": classification.get("legal_domain") or "Unclear",
                "tag": classification.get("matter_type") or "Unclear",
            },
            "explanation": [],
            "relevantInfo": [],
            "authority": None,
            "timeline": [],
            "documents": [],
            "evidence": [],
            "actionPlan": [],
            "sources": [],
            "sourceStatus": "none",
            "intake": {
                "problem_summary": intake.get("problem_summary") or problem[:160],
            },
            "classification": {
                "jurisdiction": classification.get("jurisdiction") or province or "Pakistan",
                "locality": classification.get("locality") or province or "unknown",
            },
        }

    intake = pipeline.get("intake") or {}
    classification = pipeline.get("classification") or {}
    response = pipeline.get("response") or {}
    evidence = pipeline.get("evidence") or []
    official_domains = {source.official_domain.lower() for source in LEGAL_SOURCES}
    official_domains.add("kpcode.kp.gov.pk")
    sources = []
    for item in evidence:
        url = item.get("source_url") or ""
        parsed_url = urlparse(url)
        host = (parsed_url.hostname or "").lower()
        if parsed_url.scheme != "https" or not any(host == domain or host.endswith(f".{domain}") for domain in official_domains):
            continue
        sources.append({
            "title": item.get("citation") or item.get("source_title") or item.get("source_name") or "Official source",
            "type": item.get("source_type") or "Official source",
            "note": item.get("official_status") or item.get("verification_notes") or "Retrieved from an official domain; source content has not received human legal review.",
            "url": url,
            "status": "verified" if item.get("verified") is True else "unverified",
        })

    if sources:
        explanation = [response.get("answer")] if response.get("answer") else []
    else:
        explanation = [
            "Official legal-source evidence could not be retrieved for this request. We cannot provide case-specific guidance from unverified model output. Please try again later or consult a qualified local lawyer.",
        ]
        if "ur" in language and "roman" not in language:
            explanation = ["اس درخواست کے لیے سرکاری قانونی ماخذ سے شواہد حاصل نہیں ہو سکے۔ غیر تصدیق شدہ AI جواب پر مخصوص رہنمائی دینا محفوظ نہیں۔ براہِ کرم بعد میں دوبارہ کوشش کریں یا مستند مقامی وکیل سے رجوع کریں۔"]
        elif "roman" in language:
            explanation = ["Is darkhwast ke liye official qanooni sources se daleel hasil nahi ho saki. Ghair-tasdeeq-shuda AI jawab par khaas rehnumai dena munasib nahi. Baad mein dobara koshish karein ya mustanad local wakeel se rabta karein."]

    authorities = response.get("authorities") or []
    authority = None
    if sources and authorities:
        authority = {
            "name": authorities[0],
            "description": "Suggested from the retrieved evidence. Confirm local jurisdiction and procedure with a qualified lawyer.",
            "howToReach": [],
        }
    return {
        "isDemo": False,
        "status": "completed" if sources else "evidence_unavailable",
        "follow_up_questions": (pipeline.get("follow_up", {}).get("questions") or [])[:3],
        "legalArea": {
            "name": classification.get("legal_domain") or "Unclear",
            "tag": classification.get("matter_type") or "Unclear",
        },
        "explanation": explanation,
        "relevantInfo": [
            {"title": item.get("citation") or item.get("source_title") or item.get("source_name", "Official source"), "text": (item.get("relevant_text") or "")[:1200]}
            for item in evidence[:5]
            if item.get("relevant_text")
        ],
        "authority": authority,
        "timeline": [],
        "documents": response.get("documents_needed", []) if sources else [],
        "evidence": [],
        "actionPlan": [{"when": "", "title": step, "detail": ""} for step in (response.get("next_steps") or [])] if sources else [],
        "sources": sources,
        "sourceStatus": "retrieved" if sources else "none",
        "intake": {"problem_summary": intake.get("problem_summary") or problem[:160]},
        "classification": {
            "jurisdiction": classification.get("jurisdiction") or province or "Pakistan",
            "locality": classification.get("locality") or province or "unknown",
        },
    }
