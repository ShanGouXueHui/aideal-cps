from pydantic_settings import BaseSettings, SettingsConfigDict


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

    # 京东联盟导购媒体配置
    JD_SITE_ID: str = ""
    JD_POSITION_ID: str = ""

    # 京东联盟应用配置
    JD_APP_KEY: str = ""
    JD_APP_SECRET: str = ""
    JD_AUTH_KEY: str = ""

    # 京东API网关
    JD_API_BASE: str = "https://api.jd.com/routerjson"

    SECRET_KEY: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
