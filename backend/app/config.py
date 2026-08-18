from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql://tailorai:tailorai@localhost:5432/tailorai"

    jwt_secret: str = "change-me-in-production-min-32-bytes-long"
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7

    nvidia_nim_api_key: str = ""
    nim_chat_model: str = "meta/llama-3.1-8b-instruct"
    nim_embed_model: str = "nvidia/nv-embedqa-e5-v5"
    nim_base_url: str = "https://integrate.api.nvidia.com/v1"

    cors_origins: list[str] = ["http://localhost:3000"]


settings = Settings()
