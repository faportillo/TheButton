import os
from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict
from shared import constants
from typing import Any, Dict, Literal
from pydantic import Field, model_validator

load_dotenv()


class APISettings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env", env_prefix="API_", extra="ignore"
    )

    # Environment
    env: Literal["dev", "prod"] = "dev"

    # Core connections
    database_url: str = Field(..., alias="DATABASE_URL")
    kafka_bootstrap: str = Field(..., alias="KAFKA_BROKER_URL")
    kafka_api_key: str | None = Field(None, alias="KAFKA_API_KEY")
    kafka_api_secret: str | None = Field(None, alias="KAFKA_API_SECRET")

    # Kafka logical settings
    kafka_client_id: str = constants.API_KAFKA_CLIENT_ID

    # Redis
    redis_host: str = Field("localhost", alias="REDIS_HOST")
    redis_port: int = Field(6379, alias="REDIS_PORT")
    redis_password: str | None = Field(None, alias="REDIS_PASSWORD")
    redis_url: str | None = Field(None, alias="REDIS_URL")

    @model_validator(mode="after")
    def validate_prod_credentials(self) -> "APISettings":
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
                "security.protocol": "SASL_SSL",
                "sasl.mechanism": "PLAIN",
                "sasl.username": self.kafka_api_key,
                "sasl.password": self.kafka_api_secret,
                "acks": "1",
                "enable.idempotence": True,  # Prevent duplicates
                "compression.type": "snappy",  # Optimize bandwidth
                "linger.ms": 10,  # Improved batching throughput
                "client.id": self.kafka_client_id,
            }

        else:
            return {
                "bootstrap.servers": self.kafka_bootstrap,
                "client.id": self.kafka_client_id,
            }

    @property
    def redis_kwargs(self) -> Dict[str, Any]:
        """
        Returns keyword arguments for Redis subscriber connection,
        following best practices according to the python-redis docs:
        - In production, use from_url with recommended connection and health params.
        - In dev, use direct connection with minimal params, suitable for local or default Redis.
        """
        if self.env == "prod":
            # Use from_url; health & socket reliability tweaks for production pubsub subscriber
            if self.redis_url:
                return {
                    "url": self.redis_url,
                    "health_check_interval": 10,
                    "socket_connect_timeout": 5,
                    "retry_on_timeout": True,
                    "decode_responses": True,  # recommended for pubsub/subscriber pattern
                }
            else:
                # fallback to host/port/password if URL not given
                return {
                    "host": self.redis_host,
                    "port": self.redis_port,
                    "password": self.redis_password,
                    "health_check_interval": 10,
                    "socket_connect_timeout": 5,
                    "retry_on_timeout": True,
                    "decode_responses": True,
                }
        else:
            # In dev: minimal, safe defaults; python-redis doc doesn't require those kwargs
            if self.redis_url:
                return {
                    "url": self.redis_url,
                    "decode_responses": True,  # still makes sense for most usage
                }
            return {
                "host": self.redis_host,
                "port": self.redis_port,
                "decode_responses": True,
            }

settings = APISettings()
