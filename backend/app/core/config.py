from functools import lru_cache
import secrets

from typing import Literal

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Question Paper Studio API"
    api_prefix: str = "/api/v1"
    secret_key: str = Field(default_factory=lambda: secrets.token_urlsafe(48))
    access_token_expire_minutes: int = 60
    mongodb_uri: str = "mongodb://localhost:27017"
    mongodb_database: str = "question_paper_studio"
    cors_origins: str = "http://localhost:5173"
    gemini_api_key: str = Field(default="", repr=False)
    gemini_model: str = "gemini-3.8-flash"
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3"
    llm_provider_mode: Literal["auto", "gemini", "ollama"] = "auto"
    embedding_model: str = "sentence-transformers/all-MiniLM-L6-v2"
    vector_store_path: str = "./data/vector_store"
    upload_dir: str = "./data/uploads"
    university_name: str = "MGM UNIVERSITY"

    @field_validator("secret_key")
    @classmethod
    def require_private_secret(cls, value: str) -> str:
        if len(value) < 32 or value.startswith("replace-with-"):
            raise ValueError("SECRET_KEY must be a private value of at least 32 characters; replace the example value.")
        return value

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    @property
    def allowed_origins(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()