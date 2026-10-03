import uuid
import logging

from fastapi import APIRouter, Depends, HTTPException
from groq import RateLimitError
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import bindparam, text

from app.api.dependencies import get_authenticated_user
from app.database.connection import engine
from app.agents.orchestrator import process_case
from app.legal_sources.referrals import build_referral_context
from app.services.ai_service import GroqConfigurationError

logger = logging.getLogger(__name__)


router = APIRouter(
    prefix="/api/conversations",
    tags=["Conversations"],
)


def format_case_response(pipeline_result: dict, labels: dict[str, str] | None = None) -> str:
    message_labels = {
        "caseSummary": "Case summary",
        "currentGuidance": "What we can tell you now",
        "nextSteps": "Your to-do list",
        "documentsNeeded": "Keep these documents or details ready",
        "optionalDetails": "Optional details you can share (answer any you know, or skip these)",
        "officialReferences": "Official legal references",
        "aiGenerated": "AI-generated guidance",
        "sourceVerified": "Verified against retrieved evidence",
        "sourceRetrieved": "Retrieved from an official source; not independently verified",
        "noOfficialEvidence": "No official source evidence was retrieved. Treat this response as limited and unverified.",
        "uncertainty": "What the available sources do not specify",
        "legalDisclaimer": "This is general legal information, not legal advice. Confirm important steps with a qualified local lawyer.",
        "underReview": " [Under Review]",
        "underReviewNotice": "The Pakistan Code marks at least one consolidated text as under review; check the relevant Gazette notification for later amendments.",
        "sourceExcerpt": "Relevant excerpt",
        "researchQuestion": "Related research question",
        "supported": "Supported",
        "contradicted": "Contradicted",
        "unresolved": "Unresolved",
        "needDescription": "Please briefly describe what happened and where. Share what outcome you need; you can leave out details you do not know.",
        "clarificationPrompt": "To understand your situation, please clarify:",
        "limitedNextStep": "Keep relevant messages, documents, photos, and dates together.",
        "responseUnavailable": "I could not prepare a response from the available information. Please try again.",
        "referralsTitle": "Support and official referral options",
        "referralsEmergency": "If you are in immediate danger, move to a safe place and contact local emergency services or police now. This prototype could not verify one emergency number for all of Pakistan.",
        "referralsQualification": "These referrals are not confirmed appointments or eligibility. Verify current coverage, contact routes, and procedures directly. The Chitral applicability of the KP Bar Council listing could not be confirmed.",
        "referralsReason_emergency": "The intake indicates emergency urgency.",
        "referralsReason_urgent": "The intake indicates urgent attention.",
        "referralsReason_high_risk": "This matter may involve a high-risk protection or crime concern.",
        "referralsReason_legal_aid": "You indicated difficulty affording legal help.",
        "referralsReason_evidence_unavailable": "No official evidence was retrieved for this matter.",
        "referralsReason_evidence_unresolved": "The official-source research could not verify an answer.",
        "referralsUnverified": "Unverified — please confirm before relying on this.",
        "referralsDirectoryNote": "This curated list is not exhaustive.",
        "referralsUpperNote": "Upper Chitral contacts are not confirmed. Only entries verified for Upper Chitral are shown.",
        "referralsDistrict_lower_chitral": "Lower Chitral",
        "referralsDistrict_upper_chitral": "Upper Chitral",
        "referralsDistrict_chitral_wide": "Chitral-wide",
        "referralsDistrict_national": "National",
        "referralsPhone": "Phone",
        "referralsFax": "Fax",
        "referralsEmail": "Email",
        "referralsWebsite": "Website",
        "referralsSource": "Source",
        "referralsFree": "Free service",
        "referralsLastVerified": "Directory checked",
        "referralsConfidence": "Confidence",
        "referralsConfidence_high": "High",
        "referralsConfidence_medium": "Medium",
        "referralsConfidence_low": "Low",
        "referralsCoverageLimits": "Coverage limits",
        "referralsCoverage_dlec": "The DLEC application form and contact person could not be confirmed.",
        "referralsCoverage_upper": "Official Upper Chitral court, police, and DLEC contacts could not be confirmed.",
        "referralsCoverage_shelter": "A women's crisis centre or Dar-ul-Aman, and the Dispute Resolution Council in Chitral, could not be confirmed.",
        "referralsCoverage_laja": "Whether LAJA serves Chitral or KP could not be confirmed; Chitral users are not referred to LAJA.",
    }
    message_labels.update({key: value for key, value in (labels or {}).items() if isinstance(value, str)})

    referral = build_referral_context(pipeline_result)

    def format_referrals() -> str:
        if not referral["recommended"]:
            return ""
        sections = [message_labels["referralsTitle"]]
        if referral.get("emergency"):
            sections.append(message_labels["referralsEmergency"])
        sections.extend(
            message_labels.get(f"referralsReason_{reason}", reason)
            for reason in referral["reasons"]
        )
        for resource in referral["resources"]:
            district_label = message_labels.get(
                "referralsDistrict_"
                + resource["district"].replace(" ", "_").replace("-", "_").casefold(),
                resource["district"],
            )
            lines = [f"- {resource['name']} ({district_label})"]
            if resource["confidence"] != "high":
                lines.append(f"  {message_labels['referralsUnverified']}")
            if resource.get("phone"):
                lines.append(f"  {message_labels['referralsPhone']}: {resource['phone']}")
            lines.append(
                f"  {message_labels['referralsConfidence']}: "
                f"{message_labels.get('referralsConfidence_' + resource['confidence'], resource['confidence'])}"
            )
            lines.append(f"  {message_labels['referralsLastVerified']}: {resource['last_verified']}")
            if resource.get("fax"):
                lines.append(f"  {message_labels['referralsFax']}: {resource['fax']}")
            if resource.get("email"):
                lines.append(f"  {message_labels['referralsEmail']}: {resource['email']}")
            if resource.get("website"):
                lines.append(f"  {message_labels['referralsWebsite']}: {resource['website']}")
            if resource.get("notes"):
                lines.append(f"  {resource['notes']}")
            lines.append(f"  {message_labels['referralsSource']}: {resource['source_url']}")
            if resource.get("free_service") is True:
                lines.append(f"  {message_labels['referralsFree']}")
            sections.append("\n".join(lines))
        if referral.get("upper_chitral_contacts_unconfirmed"):
            sections.append(message_labels["referralsUpperNote"])
        sections.append(message_labels["referralsDirectoryNote"])
        sections.append(
            message_labels["referralsCoverageLimits"]
            + ":\n- "
            + "\n- ".join((
                message_labels["referralsCoverage_dlec"],
                message_labels["referralsCoverage_upper"],
                message_labels["referralsCoverage_shelter"],
                message_labels["referralsCoverage_laja"],
            ))
        )
        sections.append(message_labels["referralsQualification"])
        return "\n".join(sections)

    def append_referrals(text: str) -> str:
        referrals = format_referrals()
        return f"{text}\n\n{referrals}" if referrals else text

    def format_references(evidence: list[dict], verification: list[dict]) -> list[str]:
        references = []
        for item in evidence:
            source_url = item.get("source_url")
            reference = item.get("citation") or item.get("source_title") or item.get("source_name")
            if not reference or not source_url:
                continue
            source_status = (
                message_labels["underReview"]
                if item.get("official_status") == "Under Review"
                else f" [{item['official_status']}]" if item.get("official_status")
                else f" [{message_labels['sourceVerified'] if item.get('verified') is True else message_labels['sourceRetrieved']}]"
            )
            lines = [f"- {reference}{source_status}", f"  {source_url}"]
            excerpt = str(item.get("relevant_text") or "").strip()
            if excerpt:
                lines.append(f"  {message_labels['sourceExcerpt']}: {excerpt[:900]}")
            for result in verification:
                matched = any(
                    isinstance(used, dict) and used.get("source_url") == source_url
                    for used in (result.get("evidence_used") or [])
                )
                if matched:
                    status = result.get("status", "unresolved")
                    label = message_labels.get(status, message_labels["unresolved"])
                    lines.append(
                        f"  {message_labels['researchQuestion']} ({label}): {result.get('claim', '')}"
                    )
            references.append("\n".join(lines))
        return references

    if pipeline_result.get("status") == "needs_description":
        return message_labels["needDescription"]

    if pipeline_result.get("status") == "needs_clarification":
        follow_up = pipeline_result.get("follow_up", {})
        conversational_message = str(
            follow_up.get("conversational_message") or ""
        ).strip()
        if conversational_message:
            return append_referrals(conversational_message)

        summary = str(
            pipeline_result.get("intake", {}).get("problem_summary") or ""
        ).strip()
        questions = [
            str(question).strip()
            for question in follow_up.get("questions", [])
            if str(question).strip()
        ]
        fallback = [summary, "\n".join(questions)]
        response = "\n\n".join(part for part in fallback if part) or message_labels["responseUnavailable"]
        return append_referrals(response)

    if pipeline_result.get("status") == "evidence_unavailable":
        intake = pipeline_result.get("intake", {})
        sections = []
        if intake.get("problem_summary"):
            sections.append(str(intake["problem_summary"]))
        sections.extend((
            message_labels["noOfficialEvidence"],
            f"{message_labels['nextSteps']}:\n1. {message_labels['limitedNextStep']}",
        ))
        questions = pipeline_result.get("follow_up", {}).get("questions") or []
        if questions:
            formatted_questions = "\n".join(
                f"{index}. {question}"
                for index, question in enumerate(questions, 1)
            )
            sections.append(f"{message_labels['optionalDetails']}:\n{formatted_questions}")
        referrals = format_referrals()
        if referrals:
            sections.append(referrals)
        sections.append(message_labels["legalDisclaimer"])
        return "\n\n".join(sections)

    if pipeline_result.get("status") == "evidence_unresolved":
        verification = pipeline_result.get("verification", [])
        sections = []
        answer = (pipeline_result.get("response") or {}).get("answer")
        sections.append(answer or "The retrieved official sources do not establish a verified answer to the material questions. Those points remain unresolved.")
        if verification:
            details = "\n".join(
                f"- [{message_labels.get(item.get('status', 'unresolved'), message_labels['unresolved'])}] {item.get('claim', '')}: {item.get('reasoning', '')}"
                for item in verification
            )
            sections.append(f"{message_labels['uncertainty']}:\n{details}")
        references = format_references(
            pipeline_result.get("evidence", []),
            verification,
        )
        if references:
            sections.append(f"{message_labels['officialReferences']}:\n" + "\n".join(references[:8]))
        referrals = format_referrals()
        if referrals:
            sections.append(referrals)
        sections.append(message_labels["legalDisclaimer"])
        return "\n\n".join(sections)

    intake = pipeline_result.get("intake", {})
    response = pipeline_result.get("response", {})
    sections = []

    answer = response.get("answer")
    if answer:
        sections.append(answer)

    next_steps = response.get("next_steps") or [
        "Keep relevant messages, documents, photos, and dates together.",
        "For advice specific to your situation, consult a qualified lawyer or the relevant local authority.",
    ]
    todo_list = "\n".join(f"{index}. {step}" for index, step in enumerate(next_steps, 1))
    sections.append(f"{message_labels['nextSteps']}:\n{todo_list}")

    documents_needed = response.get("documents_needed") or []
    if documents_needed:
        documents = "\n".join(f"- {item}" for item in documents_needed)
        sections.append(f"{message_labels['documentsNeeded']}:\n{documents}")

    questions = pipeline_result.get("follow_up", {}).get("questions") or []
    if questions:
        optional_questions = "\n".join(
            f"{index}. {question}"
            for index, question in enumerate(questions, 1)
        )
        sections.append(f"{message_labels['optionalDetails']}:\n{optional_questions}")

    referrals = format_referrals()
    if referrals:
        sections.append(referrals)

    uncertainty = response.get("uncertainty") or []
    if uncertainty:
        sections.append(f"{message_labels['uncertainty']}:\n" + "\n".join(f"- {item}" for item in uncertainty))

    legal_references = format_references(
        pipeline_result.get("evidence", []),
        pipeline_result.get("verification", []),
    )
    legal_references = list(dict.fromkeys(legal_references))

    if legal_references:
        sections.append(f"{message_labels['officialReferences']}:\n" + "\n".join(legal_references[:8]))
    else:
        sections.append(message_labels["noOfficialEvidence"])
    if any(item.get("official_status") == "Under Review" for item in pipeline_result.get("evidence", [])):
        sections.append(message_labels["underReviewNotice"])

    disclaimer = response.get("disclaimer")
    if disclaimer:
        normalized_disclaimer = str(disclaimer).lower()
        boilerplate = ("not a lawyer", "not legal advice", "not a substitute for")
        if not any(phrase in normalized_disclaimer for phrase in boilerplate):
            sections.append(str(disclaimer))

    sections.append(message_labels["legalDisclaimer"])

    return "\n\n".join(sections) or message_labels["responseUnavailable"]


class CreateConversationRequest(BaseModel):
    title: str | None = None


class CreateMessageRequest(BaseModel):
    content: str
    language: str = "en"
    labels: dict[str, str] = Field(default_factory=dict)
    document_ids: list[str] = Field(default_factory=list, max_length=5)

    @field_validator("content")
    @classmethod
    def validate_content(cls, value: str) -> str:
        value = value.strip()

        if not value:
            raise ValueError("Message content cannot be empty")

        return value


# ---------------------------------------------------------
# CREATE CONVERSATION
# ---------------------------------------------------------

@router.post("")
async def create_conversation(
    data: CreateConversationRequest,
    user=Depends(get_authenticated_user),
):
    query = text("""
        INSERT INTO conversations (
            id,
            user_id,
            title
        )
        VALUES (
            :id,
            :user_id,
            :title
        )
        RETURNING
            id,
            user_id,
            title,
            created_at,
            updated_at
    """)

    with engine.begin() as connection:
        result = connection.execute(
            query,
            {
                "id": str(uuid.uuid4()),
                "user_id": str(user.id),
                "title": data.title,
            },
        )

        conversation = result.mappings().first()

    return {
        "message": "Conversation created successfully",
        "data": dict(conversation),
    }


# ---------------------------------------------------------
# GET USER'S CONVERSATIONS
# ---------------------------------------------------------

@router.get("")
async def get_conversations(
    user=Depends(get_authenticated_user),
):
    query = text("""
        SELECT
            id,
            user_id,
            title,
            created_at,
            updated_at
        FROM conversations
        WHERE user_id = :user_id
        ORDER BY updated_at DESC
    """)

    with engine.connect() as connection:
        result = connection.execute(
            query,
            {
                "user_id": str(user.id),
            },
        )

        conversations = result.mappings().all()

    return {
        "message": "Conversations retrieved successfully",
        "data": [
            dict(conversation)
            for conversation in conversations
        ],
    }


# ---------------------------------------------------------
# GET SINGLE CONVERSATION
# ---------------------------------------------------------

@router.get("/{conversation_id}")
async def get_conversation(
    conversation_id: str,
    user=Depends(get_authenticated_user),
):
    query = text("""
        SELECT
            id,
            user_id,
            title,
            created_at,
            updated_at
        FROM conversations
        WHERE id = :conversation_id
          AND user_id = :user_id
    """)

    with engine.connect() as connection:
        result = connection.execute(
            query,
            {
                "conversation_id": conversation_id,
                "user_id": str(user.id),
            },
        )

        conversation = result.mappings().first()

    if conversation is None:
        raise HTTPException(
            status_code=404,
            detail="Conversation not found",
        )

    return {
        "message": "Conversation retrieved successfully",
        "data": dict(conversation),
    }


# ---------------------------------------------------------
# CREATE MESSAGE + AI RESPONSE
# ---------------------------------------------------------

@router.post("/{conversation_id}/messages")
def create_message(
    conversation_id: str,
    data: CreateMessageRequest,
    user=Depends(get_authenticated_user),
):

    # -----------------------------------------------------
    # 1. Verify conversation ownership
    # -----------------------------------------------------

    conversation_query = text("""
        SELECT id
        FROM conversations
        WHERE id = :conversation_id
          AND user_id = :user_id
    """)

    with engine.connect() as connection:
        conversation_result = connection.execute(
            conversation_query,
            {
                "conversation_id": conversation_id,
                "user_id": str(user.id),
            },
        )

        conversation = conversation_result.mappings().first()

    if conversation is None:
        raise HTTPException(
            status_code=404,
            detail="Conversation not found",
        )

    selected_documents = []
    document_ids = list(dict.fromkeys(data.document_ids))
    if document_ids:
        documents_query = text("""
            SELECT id, name, type, size, extracted_text
            FROM documents
            WHERE user_id = :user_id AND id IN :document_ids
        """).bindparams(bindparam("document_ids", expanding=True))
        with engine.connect() as connection:
            selected_documents = [
                dict(document)
                for document in connection.execute(documents_query, {
                    "user_id": str(user.id),
                    "document_ids": document_ids,
                }).mappings().all()
            ]
        if len(selected_documents) != len(document_ids):
            raise HTTPException(status_code=404, detail="Document not found")

    # -----------------------------------------------------
    # 2. Get previous conversation messages
    # -----------------------------------------------------

    history_query = text("""
        SELECT
            role,
            content
        FROM messages
        WHERE conversation_id = :conversation_id
        ORDER BY created_at ASC
    """)

    with engine.connect() as connection:
        result = connection.execute(
            history_query,
            {
                "conversation_id": conversation_id,
            },
        )

        conversation_history = [
            dict(message)
            for message in result.mappings().all()
        ]

    # -----------------------------------------------------
    # 3. Save user's message
    # -----------------------------------------------------

    user_message_query = text("""
        INSERT INTO messages (
            id,
            conversation_id,
            role,
            content
        )
        VALUES (
            :id,
            :conversation_id,
            'user',
            :content
        )
        RETURNING
            id,
            conversation_id,
            role,
            content,
            created_at
    """)

    with engine.begin() as connection:
        result = connection.execute(
            user_message_query,
            {
                "id": str(uuid.uuid4()),
                "conversation_id": conversation_id,
                "content": data.content,
            },
        )

        user_message = result.mappings().first()

        for document in selected_documents:
            connection.execute(text("""
                INSERT INTO message_documents (message_id, document_id, user_id)
                VALUES (:message_id, :document_id, :user_id)
            """), {
                "message_id": user_message["id"],
                "document_id": document["id"],
                "user_id": str(user.id),
            })

        # Update conversation timestamp
        update_query = text("""
            UPDATE conversations
            SET updated_at = CURRENT_TIMESTAMP
            WHERE id = :conversation_id
              AND user_id = :user_id
        """)

        connection.execute(
            update_query,
            {
                "conversation_id": conversation_id,
                "user_id": str(user.id),
            },
        )

        # -----------------------------------------------------
    # 4. Run complete Apna Wakeel pipeline WITH CONTEXT
    # -----------------------------------------------------

    try:
        pipeline_result = process_case(
            data.content,
            conversation_history,
            language=data.language,
            document_context="\n\n".join(
                f"Document: {document['name']}\n{document['extracted_text'][:12000]}"
                for document in selected_documents
            ),
        )
    except GroqConfigurationError as error:
        logger.error("Legal AI configuration error: %s", error)
        raise HTTPException(status_code=503, detail=str(error)) from None
    except Exception as e:
        logger.exception("Case pipeline failed")
        if isinstance(e, RateLimitError):
            raise HTTPException(
                status_code=429,
                detail="The AI service has reached its current usage limit. Please check your Groq quota and try again later.",
            ) from e
        raise HTTPException(
            status_code=503,
            detail="The legal analysis service is temporarily unavailable. Please try again."
        ) from None

    # -----------------------------------------------------
    # 5. Get AI response
    # -----------------------------------------------------

    try:
        ai_response = format_case_response(pipeline_result, data.labels)
    except Exception as e:
        logger.exception("Case response formatting failed")
        raise HTTPException(
            status_code=500,
            detail="The system could not generate a valid response. Please try again.",
        ) from e

    # -----------------------------------------------------
    # 6. Save AI response
    # -----------------------------------------------------

    assistant_message_query = text("""
        INSERT INTO messages (
            id,
            conversation_id,
            role,
            content
        )
        VALUES (
            :id,
            :conversation_id,
            'assistant',
            :content
        )
        RETURNING
            id,
            conversation_id,
            role,
            content,
            created_at
    """)

    with engine.begin() as connection:
        result = connection.execute(
            assistant_message_query,
            {
                "id": str(uuid.uuid4()),
                "conversation_id": conversation_id,
                "content": ai_response,
            },
        )

        assistant_message = result.mappings().first()

        # Update conversation timestamp again
        update_query = text("""
            UPDATE conversations
            SET updated_at = CURRENT_TIMESTAMP
            WHERE id = :conversation_id
              AND user_id = :user_id
        """)

        connection.execute(
            update_query,
            {
                "conversation_id": conversation_id,
                "user_id": str(user.id),
            },
        )

    # -----------------------------------------------------
    # 7. Return both messages
    # -----------------------------------------------------

    return {
        "message": "Message processed successfully",
        "user_message": {
            **dict(user_message),
            "attachments": [
                {key: document[key] for key in ("id", "name", "type", "size")}
                for document in selected_documents
            ],
        },
        "assistant_message": dict(assistant_message),
    }


# ---------------------------------------------------------
# GET ALL MESSAGES IN A CONVERSATION
# ---------------------------------------------------------

@router.get("/{conversation_id}/messages")
async def get_messages(
    conversation_id: str,
    user=Depends(get_authenticated_user),
):

    # First verify conversation ownership
    conversation_query = text("""
        SELECT id
        FROM conversations
        WHERE id = :conversation_id
          AND user_id = :user_id
    """)

    with engine.connect() as connection:
        conversation_result = connection.execute(
            conversation_query,
            {
                "conversation_id": conversation_id,
                "user_id": str(user.id),
            },
        )

        conversation = conversation_result.mappings().first()

    if conversation is None:
        raise HTTPException(
            status_code=404,
            detail="Conversation not found",
        )

    # Get messages
    messages_query = text("""
        SELECT
            id,
            conversation_id,
            role,
            content,
            created_at
        FROM messages
        WHERE conversation_id = :conversation_id
        ORDER BY created_at ASC
    """)

    with engine.connect() as connection:
        result = connection.execute(
            messages_query,
            {
                "conversation_id": conversation_id,
            },
        )

        messages = result.mappings().all()

    message_items = [dict(message) for message in messages]
    if message_items:
        attachment_query = text("""
            SELECT md.message_id, d.id, d.name, d.type, d.size
            FROM message_documents AS md
            JOIN documents AS d ON d.id = md.document_id
            WHERE md.user_id = :user_id AND md.message_id IN :message_ids
            ORDER BY d.created_at ASC
        """).bindparams(bindparam("message_ids", expanding=True))
        with engine.connect() as connection:
            attachments = connection.execute(attachment_query, {
                "user_id": str(user.id),
                "message_ids": [message["id"] for message in message_items],
            }).mappings().all()
        attachments_by_message = {}
        for attachment in attachments:
            attachments_by_message.setdefault(attachment["message_id"], []).append({
                key: attachment[key] for key in ("id", "name", "type", "size")
            })
        for message in message_items:
            message["attachments"] = attachments_by_message.get(message["id"], [])

    return {
        "message": "Messages retrieved successfully",
        "data": message_items,
    }


# ---------------------------------------------------------
# DELETE CONVERSATION
# ---------------------------------------------------------

@router.delete("/{conversation_id}")
async def delete_conversation(
    conversation_id: str,
    user=Depends(get_authenticated_user),
):
    query = text("""
        DELETE FROM conversations
        WHERE id = :conversation_id
          AND user_id = :user_id
        RETURNING id
    """)

    with engine.begin() as connection:
        owned_conversation = connection.execute(text("""
            SELECT id FROM conversations
            WHERE id = :conversation_id AND user_id = :user_id
        """), {
            "conversation_id": conversation_id,
            "user_id": str(user.id),
        }).first()
        if owned_conversation is None:
            raise HTTPException(status_code=404, detail="Conversation not found")
        connection.execute(text("""
            DELETE FROM message_documents
            WHERE user_id = :user_id
              AND message_id IN (
                  SELECT id FROM messages WHERE conversation_id = :conversation_id
              )
        """), {"user_id": str(user.id), "conversation_id": conversation_id})
        connection.execute(text("""
            DELETE FROM messages WHERE conversation_id = :conversation_id
        """), {"conversation_id": conversation_id})
        result = connection.execute(
            query,
            {
                "conversation_id": conversation_id,
                "user_id": str(user.id),
            },
        )

        deleted_conversation = result.mappings().first()

    if deleted_conversation is None:
        raise HTTPException(
            status_code=404,
            detail="Conversation not found",
        )

    return {
        "message": "Conversation deleted successfully",
        "conversation_id": str(deleted_conversation["id"]),
    }