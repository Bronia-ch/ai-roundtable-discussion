from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    base_url: str = "https://api.deepseek.com/v1"
    api_key: str = ""
    model: str = "deepseek-chat"
    sqlite_path: str = "./data/app.db"

    model_config = {
        "env_prefix": "LLM_",
        "env_file": ".env",
    }
