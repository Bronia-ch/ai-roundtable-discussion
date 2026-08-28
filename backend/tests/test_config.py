from app.config import Settings


def test_settings_reads_env(monkeypatch):
    monkeypatch.setenv("LLM_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("LLM_API_KEY", "sk-test-not-real")
    monkeypatch.setenv("LLM_MODEL", "test-model")
    s = Settings()
    assert s.base_url == "https://example.test/v1"
    assert s.model == "test-model"


def test_settings_default_sqlite():
    assert Settings().sqlite_path.endswith("app.db")
