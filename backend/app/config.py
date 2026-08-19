from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

DEFAULT_JWT_SECRET = "change-me-in-production-min-32-bytes-long"
MIN_JWT_SECRET_BYTES = 32


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    environment: str = "development"

    database_url: str = "postgresql://tailorai:tailorai@localhost:5432/tailorai"

    jwt_secret: str = DEFAULT_JWT_SECRET
    jwt_algorithm: str = "HS256"
    jwt_expire_minutes: int = 60 * 24 * 7

    nvidia_nim_api_key: str = ""
    nim_chat_model: str = "meta/llama-3.1-8b-instruct"
    nim_embed_model: str = "nvidia/nv-embedqa-e5-v5"
    nim_base_url: str = "https://integrate.api.nvidia.com/v1"

    cors_origins: list[str] = ["http://localhost:3000"]

    @model_validator(mode="after")
    def _enforce_real_jwt_secret_outside_dev(self) -> "Settings":
        """The default JWT secret is fine for local development, but must never
        reach a non-development deployment silently — refuse to start instead."""
        if self.environment == "development":
            return self
        if self.jwt_secret == DEFAULT_JWT_SECRET or len(self.jwt_secret.encode("utf-8")) < MIN_JWT_SECRET_BYTES:
            raise ValueError(
                "JWT_SECRET must be set to a real secret of at least 32 bytes when "
                "ENVIRONMENT is not 'development'. Refusing to start with the default "
                "or an undersized secret outside development."
            )
        return self


settings = Settings()
