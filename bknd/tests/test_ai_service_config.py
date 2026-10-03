import os

import pytest

from app.agents.intake_agent import intake_case
from app.core.config import BASE_DIR, Settings
from app.services import ai_service
from app.services.ai_service import GroqConfigurationError, generate_response


def test_backend_settings_include_the_backend_env_file():
    env_files = Settings.model_config["env_file"]
    assert env_files[-1] == BASE_DIR / ".env"


def test_settings_load_uppercase_groq_variables_from_env_file(tmp_path, monkeypatch):
    monkeypatch.delenv("GROQ_API_KEY", raising=False)
    monkeypatch.delenv("GROQ_MODEL", raising=False)
    api_key = os.urandom(32).hex()
    env_file = tmp_path / ".env"
    env_file.write_text(
        f"GROQ_API_KEY={api_key}\nGROQ_MODEL=test-model\n",
        encoding="utf-8",
    )

    loaded = Settings(_env_file=env_file)

    assert loaded.groq_api_key == api_key
    assert loaded.groq_model == "test-model"


def test_generate_response_reports_missing_groq_configuration(monkeypatch):
    monkeypatch.setattr(ai_service.settings, "groq_api_key", "")

    with pytest.raises(GroqConfigurationError, match="GROQ_API_KEY") as error:
        generate_response("test")

    assert "bknd/.env.example" in str(error.value)


def test_intake_reports_missing_groq_configuration_without_legacy_error(monkeypatch):
    monkeypatch.setattr(ai_service.settings, "groq_api_key", "")

    with pytest.raises(GroqConfigurationError, match="GROQ_API_KEY"):
        intake_case("My employer has not paid my wages.")
