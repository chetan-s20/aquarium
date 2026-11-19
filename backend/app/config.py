from pydantic_settings import BaseSettings, NoDecode, SettingsConfigDict
from pydantic import field_validator
from typing import Annotated


class Settings(BaseSettings):
    # .env may live in backend/ or the repo root
    model_config = SettingsConfigDict(env_file=(".env", "../.env"), extra="ignore")

    app_env: str = "development"
    app_name: str = "aquarium-monitor"
    database_url: str = "sqlite:///./aquarium.db"
    simulation_mode: bool = True
    # Farm local time vs UTC (India = 5.5). Only used to put the simulated dawn at local dawn.
    farm_utc_offset_hours: float = 5.5
    device_api_key: str = "dev-device-key-change-me"
    operator_api_key: str = "dev-operator-key-change-me"
    cors_origins: Annotated[list[str], NoDecode] = ["http://localhost:5173", "http://127.0.0.1:5173"]

    @field_validator("cors_origins", mode="before")
    @classmethod
    def _split(cls, v):
        return [o.strip() for o in v.split(",") if o.strip()] if isinstance(v, str) else v


settings = Settings()
