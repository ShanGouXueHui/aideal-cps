from __future__ import annotations

from pydantic_settings import BaseSettings, SettingsConfigDict


class JDUnionSettings(BaseSettings):
    JD_APP_KEY: str = ""
    JD_APP_SECRET: str = ""
    JD_API_BASE: str = "https://api.jd.com/routerjson"
    JD_PID: str = ""
    JD_SITE_ID: str = ""
    JD_POSITION_ID: str = ""
    JD_ACCESS_TOKEN: str = ""
    JD_TIMEOUT_SECONDS: int = 20

    model_config = SettingsConfigDict(env_file=".env", extra="ignore")


jd_union_settings = JDUnionSettings()


def parse_pid_for_site_position(pid: str) -> tuple[str, str]:
    parts = [part for part in (pid or "").split("_") if part]
    if len(parts) < 3:
        raise ValueError(f"invalid JD_PID: {pid!r}")
    return parts[1], parts[2]


def resolved_site_id() -> str:
    if jd_union_settings.JD_SITE_ID:
        return jd_union_settings.JD_SITE_ID
    site_id, _ = parse_pid_for_site_position(jd_union_settings.JD_PID)
    return site_id


def resolved_position_id() -> str:
    if jd_union_settings.JD_POSITION_ID:
        return jd_union_settings.JD_POSITION_ID
    _, position_id = parse_pid_for_site_position(jd_union_settings.JD_PID)
    return position_id
