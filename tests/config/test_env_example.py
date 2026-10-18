from pathlib import Path

from app.config import CONFIG_VARIABLES, get_settings

ROOT = Path(__file__).resolve().parents[2]

# ARCHITECTURE.md "Configuration" contract, one name per entry.
CONTRACT = [
    "OPENROUTER_API_KEY",
    "OPENROUTER_BASE_URL",
    "VIDEO_MODEL",
    "VIDEO_MODEL_FALLBACK",
    "VIDEO_RESOLUTIONS",
    "ENHANCE_MODEL",
    "ENHANCE_MODEL_FALLBACK",
    "QUALITY_CHECK_MODEL",
    "PLANNER_MODEL",
    "BYOK_MODELS",
    "BUCKET_ENDPOINT",
    "BUCKET_NAME",
    "BUCKET_ACCESS_KEY_ID",
    "BUCKET_SECRET_ACCESS_KEY",
    "BUCKET_REGION",
    "DATABASE_PATH",
    "DEMO_PASSPHRASE",
    "FAKE_PROVIDERS",
    "CHECK_MAX_AI_SCORE",
    "CHECK_MIN_MATCH_SCORE",
    "CHECK_FRAMES_PER_SECOND",
    "LABEL_IMAGE_LONG_SIDE",
    "SHOTS_IN_FLIGHT",
]


def parse_env_example() -> dict[str, str]:
    values = {}
    for line in (ROOT / ".env.example").read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        values[key.strip()] = value.strip()
    return values


def test_env_example_lists_every_configuration_variable():
    assert set(CONTRACT) <= set(parse_env_example())


def test_config_variables_are_the_contract_plus_port():
    assert set(CONFIG_VARIABLES) == set(CONTRACT) | {"PORT"}
    assert len(CONFIG_VARIABLES) == len(set(CONFIG_VARIABLES))


def test_secrets_have_no_value_in_env_example():
    values = parse_env_example()
    for key in (
        "OPENROUTER_API_KEY",
        "BUCKET_ACCESS_KEY_ID",
        "BUCKET_SECRET_ACCESS_KEY",
        "DEMO_PASSPHRASE",
    ):
        assert values[key] == ""


def test_bucket_endpoint_and_research_section_kept():
    values = parse_env_example()
    assert values["BUCKET_ENDPOINT"] == "https://t3.storageapi.dev"
    assert "TEST_PHOTOS_URL" in values and "MAX_CLIPS_PER_RUN" in values


def test_settings_defaults_match_env_example(monkeypatch):
    for name in CONFIG_VARIABLES:
        monkeypatch.delenv(name, raising=False)
    from app.config import reset_settings

    reset_settings()
    s = get_settings()
    assert s.OPENROUTER_BASE_URL == "https://openrouter.ai/api/v1"
    assert s.BUCKET_ENDPOINT == "https://t3.storageapi.dev"
    assert s.DATABASE_PATH == "./data/app.db"
    assert s.FAKE_PROVIDERS is False
    assert s.SHOTS_IN_FLIGHT == 8
    assert "secret" not in repr(s)
