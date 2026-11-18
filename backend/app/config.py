from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    app_name: str = "aquarium-monitor"
    secret_key: str = "change-me"
    api_host: str = "0.0.0.0"
    api_port: int = 8000
    log_level: str = "INFO"

    database_url: str = "sqlite:///./aquarium.db"

    default_timezone: str = "UTC"
    display_timezone: str = "UTC"

    simulation_mode: bool = True
    simulator_seed: int = 42
    allow_simulated_data: bool = True

    access_token_expire_minutes: int = 60
    device_api_key_header: str = "X-Device-Key"
    device_api_key: str = "dev-device-key-change-me"
    operator_api_key: str = "dev-operator-key-change-me"
    rate_limit_per_minute: int = 120

    alert_email_enabled: bool = False
    alert_webhook_enabled: bool = False


settings = Settings()
