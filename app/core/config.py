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

    # 一期：京东联盟导购媒体配置（主配置）
    JD_SITE_ID: str = ""
    JD_POSITION_ID: str = ""

    # 二期：京东开放平台API配置（可选）
    JD_APP_KEY: str = ""
    JD_APP_SECRET: str = ""

    SECRET_KEY: str = ""

    model_config = SettingsConfigDict(
        env_file=".env",
        case_sensitive=True,
        extra="ignore",
    )


settings = Settings()
