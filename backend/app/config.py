from pydantic import Field
from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    base_url: str = "https://api.deepseek.com/v1"
    api_key: str = ""
    model: str = "deepseek-chat"
    sqlite_path: str = "./data/app.db"
    # env_prefix=LLM_ 会把 llm_fake 拼成 LLM_LLM_FAKE，显式别名使其由 LLM_FAKE=1 驱动
    llm_fake: bool = Field(False, validation_alias="LLM_FAKE")  # LLM_FAKE=1：挂载离线 FakeLLMProvider（E2E/演示），绝不出网

    model_config = {
        "env_prefix": "LLM_",
        "env_file": ".env",
    }
