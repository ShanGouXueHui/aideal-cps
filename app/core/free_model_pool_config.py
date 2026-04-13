from pathlib import Path
from pydantic_settings import BaseSettings


class FreeModelPoolSettings(BaseSettings):
    FREE_MODEL_POOL_ENABLED: bool = True
    FREE_MODEL_POOL_STATE_FILE: str = "data/free_model_pool_state.json"
    FREE_MODEL_POOL_FAIL_THRESHOLD: int = 3
    FREE_MODEL_POOL_COOLDOWN_SECONDS: int = 1800
    FREE_MODEL_POOL_DEFAULT_TIMEOUT_SECONDS: int = 30

    class Config:
        env_file = ".env"
        extra = "ignore"


free_model_pool_settings = FreeModelPoolSettings()


def state_file_path() -> Path:
    return Path(free_model_pool_settings.FREE_MODEL_POOL_STATE_FILE)
