"""Service settings, read from LEDGERLENS_* environment variables or a git-ignored .env file.

They are checked when the service starts, so a wrong value stops it at once with a clear error
instead of failing on some later request.
"""

from typing import Literal

from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # extra="ignore": .env may also hold settings for other tools; only LEDGERLENS_* ones are ours.
    model_config = SettingsConfigDict(env_prefix="LEDGERLENS_", env_file=".env", extra="ignore", frozen=True)

    environment: Literal["dev", "test", "prod"] = "dev"
    log_level: Literal["DEBUG", "INFO", "WARNING", "ERROR"] = "INFO"
    # An invoice is a few KB of JSON. A body near this size is a mistake or an attack.
    max_body_bytes: int = Field(default=1_000_000, gt=0)
