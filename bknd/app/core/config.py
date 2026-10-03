from pathlib import Path
from urllib.parse import urlsplit
from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BASE_DIR = Path(__file__).resolve().parent.parent.parent
ROOT_DIR = BASE_DIR.parent


class Settings(BaseSettings):
    database_url: str = "sqlite:///./app.db"
    supabase_url: str = ""
    supabase_key: str = ""

    groq_api_key: str = ""
    groq_model: str = "openai/gpt-oss-20b"
    frontend_url: str = "http://127.0.0.1:5173"
    cors_origins: str = "http://127.0.0.1:5173,http://localhost:5173,http://127.0.0.1:4173,http://localhost:4173,http://127.0.0.1:3000,http://localhost:3000"

    @field_validator("cors_origins")
    @classmethod
    def validate_cors_origins(cls, value: str) -> str:
        origins = [origin.strip() for origin in value.split(",") if origin.strip()]
        if not origins or "*" in origins:
            raise ValueError("CORS_ORIGINS must contain explicit origins and cannot contain '*'")
        for origin in origins:
            parsed = urlsplit(origin)
            if parsed.scheme not in {"http", "https"} or not parsed.netloc or parsed.path not in {"", "/"} or parsed.query or parsed.fragment:
                raise ValueError("CORS_ORIGINS entries must be exact HTTP(S) origins")
        return ",".join(origins)

    model_config = SettingsConfigDict(
        env_file=[
            ROOT_DIR / ".env",
            BASE_DIR / ".env",
        ],
        extra="ignore",
    )


settings = Settings()