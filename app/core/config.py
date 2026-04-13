from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[2]
ENV_FILE = BASE_DIR / ".env"


class Settings(BaseSettings):
    APP_NAME: str = "AIdeal CPS"
    APP_ENV: str = "dev"
    APP_DEBUG: bool = True
    API_V1_PREFIX: str = "/api/v1"
    HOST: str = "0.0.0.0"
    PORT: int = 8000

    DATABASE_URL: str

    QWEN_API_KEY: str = ""
    QWEN_MODEL: str = "qwen-plus"

    JD_PID: str = ""
    JD_SITE_ID: str = ""
    JD_POSITION_ID: str = ""
    JD_APP_KEY: str = ""
    JD_APP_SECRET: str = ""
    JD_AUTH_KEY: str = ""
    JD_API_BASE: str = "https://api.jd.com/routerjson"

    SECRET_KEY: str = ""

    model_config = SettingsConfigDict(
        env_file=str(ENV_FILE),
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
