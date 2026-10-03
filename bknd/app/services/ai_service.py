from groq import Groq

from app.core.config import settings


class GroqConfigurationError(RuntimeError):
    """Raised when the backend has no Groq API key configured."""


def generate_response(user_message: str) -> str:
    if not settings.groq_api_key.strip():
        raise GroqConfigurationError(
            "GROQ_API_KEY is not configured. Set GROQ_API_KEY in bknd/.env "
            "(see bknd/.env.example) before starting the backend."
        )

    client = Groq(api_key=settings.groq_api_key, max_retries=1)
    response = client.chat.completions.create(
        model=settings.groq_model,
        messages=[
            {
                "role": "system",
                "content": "Return only a valid JSON object.",
            },
            {
                "role": "user",
                "content": user_message,
            }
        ],
        response_format={"type": "json_object"},
        max_completion_tokens=2048,
    )

    return response.choices[0].message.content