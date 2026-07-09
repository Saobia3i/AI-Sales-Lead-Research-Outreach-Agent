from __future__ import annotations

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    groq_api_key: str | None = Field(default=None, alias="GROQ_API_KEY")
    groq_model: str = Field(default="llama-3.3-70b-versatile", alias="GROQ_MODEL")
    default_budget_usd: float = Field(default=0.50, alias="DEFAULT_BUDGET_USD")
    max_search_calls_per_run: int = Field(default=6, alias="MAX_SEARCH_CALLS_PER_RUN")
    research_cache_ttl_seconds: int = Field(default=172800, alias="RESEARCH_CACHE_TTL_SECONDS")
    cors_origins: str = Field(default="http://localhost:3000", alias="CORS_ORIGINS")
    max_lead_search_results: int = Field(default=20, alias="MAX_LEAD_SEARCH_RESULTS")
    website_check_timeout_seconds: int = Field(default=5, alias="WEBSITE_CHECK_TIMEOUT")
    firecrawl_api_key: str | None = Field(default=None, alias="FIRECRAWL_API_KEY")
    smtp_host: str = Field(default="smtp.gmail.com", alias="SMTP_HOST")
    smtp_port: int = Field(default=587, alias="SMTP_PORT")
    smtp_user: str | None = Field(default=None, alias="SMTP_USER")
    smtp_pass: str | None = Field(default=None, alias="SMTP_PASS")
    smtp_from: str | None = Field(default=None, alias="SMTP_FROM")

    @property
    def cors_origin_list(self) -> list[str]:
        return [origin.strip() for origin in self.cors_origins.split(",") if origin.strip()]


settings = Settings()
