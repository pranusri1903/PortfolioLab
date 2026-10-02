from decimal import Decimal
from functools import lru_cache

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "sqlite:///./portfoliolab.db"
    cors_origins: str = "http://localhost:3000"

    # "clerk" validates Clerk-issued JWTs against the JWKS endpoint.
    # "dev" accepts "Bearer dev:<user_id>" tokens and must never be used in production.
    auth_mode: str = "dev"
    clerk_jwks_url: str = ""
    clerk_issuer: str = ""

    risk_free_rate: Decimal = Decimal("0.02")  # annual, used for the Sharpe ratio
    benchmark_usd: str = "BNCH"  # set to e.g. SPY when live data is enabled
    benchmark_inr: str = "NIFB"  # e.g. NIFTYBEES.NS
    twelve_data_api_key: str = ""
    cron_secret: str = ""  # shared secret for POST /api/v1/admin/update-prices
    stale_price_days: int = 7

    def benchmark_for(self, currency: str) -> str:
        return self.benchmark_inr if currency == "INR" else self.benchmark_usd

    @field_validator("database_url")
    @classmethod
    def _driver(cls, v: str) -> str:
        # Hosted providers hand out postgres:// or postgresql:// URLs; use the psycopg 3 driver.
        for prefix in ("postgres://", "postgresql://"):
            if v.startswith(prefix):
                return "postgresql+psycopg://" + v[len(prefix) :]
        return v


@lru_cache
def get_settings() -> Settings:
    return Settings()
