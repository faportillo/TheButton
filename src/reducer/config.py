import os
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict
from shared import constants
from typing import Any, Dict, Literal
from pydantic import Field, model_validator

load_dotenv()


class ReducerSettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_prefix="REDUCER_",
        extra="ignore",
    )

    # Environment
    env: Literal["dev", "prod"] = "dev"

    # Core connections
    database_url: str = Field(..., alias="DATABASE_URL")
    kafka_bootstrap: str = Field(..., alias="KAFKA_BROKER_URL")
    kafka_api_key: str = Field(None, alias="KAFKA_API_KEY")
    kafka_api_secret: str = Field(None, alias="KAFKA_API_SECRET")

    # Kafka logical settings
    kafka_client_id: str = constants.REDUCER_KAFKA_CLIENT_ID
    kafka_group_id: str = constants.REDUCER_KAFKA_GROUP_ID
    kafka_auto_offset_reset: str = "none"  # we want to fail if no offset
    kafka_enable_auto_commit: bool = False
    kafka_max_batch_size: int = constants.REDUCER_KAFKA_CONSUMER_BATCH_SIZE

    # Redis
    redis_host: str = Field("localhost", alias="REDIS_HOST")
    redis_port: int = Field(6379, alias="REDIS_PORT")
    redis_password: str | None = Field(None, alias="REDIS_PASSWORD")
    redis_url: str | None = Field(None, alias="REDIS_URL")

    # Rules + reducer behavior
    rules_path: str = "/run/secrets/rules.json"
    commit_interval_ms: int = constants.REDUCER_COMMIT_INTERVAL_MS

    backoff_max_attempts: int = 3
    backoff_base_seconds: float = 1.0
    max_backoff_seconds: float = 30.0

    @model_validator(mode="after")
    def validate_prod_credentials(self) -> "ReducerSettings":
        """Fail fast if prod is missing required credentials."""
        if self.env == "prod":
            if not self.kafka_api_key or not self.kafka_api_secret:
                raise ValueError(
                    "KAFKA_API_KEY and KAFKA_API_SECRET are required in production"
                )
        return self

    @property
    def kafka_config(self) -> Dict[str, Any]:
        if self.env == "prod" and self.kafka_api_key and self.kafka_api_secret:
            return {
                "bootstrap.servers": self.kafka_bootstrap,
                "group.id": self.kafka_group_id,
                "auto.offset.reset": self.kafka_auto_offset_reset,
                "enable.auto.commit": self.kafka_enable_auto_commit,
                "security.protocol": "SASL_SSL",
                "sasl.mechanism": "PLAIN",
                "sasl.username": self.kafka_api_key,
                "sasl.password": self.kafka_api_secret,
                "session.timeout.ms": 45000,
                "max.poll.interval.ms": 300000,
                "client.id": self.kafka_client_id,
            }

        else:
            return {
                "bootstrap.servers": self.kafka_bootstrap,
                "group.id": self.kafka_group_id,
                "auto.offset.reset": self.kafka_auto_offset_reset,
                "enable.auto.commit": self.kafka_enable_auto_commit,
                "client.id": self.kafka_client_id,
                # batch size is for your `consume_batch` call, not here
            }

    @property
    def redis_kwargs(self) -> Dict[str, Any]:
        """
        Helper for redis.Redis(...) depending on env.
        """
        if self.env == "prod" and self.redis_url:
            return {
                "url": self.redis_url,
            }
        else:
            return {
                "host": self.redis_host,
                "port": self.redis_port,
                "password": self.redis_password,
                "decode_responses": True,
            }


settings = ReducerSettings()
