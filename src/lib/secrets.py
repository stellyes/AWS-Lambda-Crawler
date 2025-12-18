"""
AWS Secrets Manager client for retrieving website credentials
Implements caching to reduce API calls and costs
"""

import json
import os
import time
from typing import Optional

import boto3
from botocore.exceptions import ClientError

from ..models.types import WebsiteCredentials
from .logger import ContextLogger

# Cache for secrets to reduce API calls
_secrets_cache: dict[str, tuple[WebsiteCredentials, float]] = {}
CACHE_TTL_SECONDS = 300  # 5 minutes


class SecretsManager:
    """Manages retrieval and caching of secrets from AWS Secrets Manager"""

    def __init__(self, logger: ContextLogger, region: str = "us-west-1"):
        self.logger = logger
        self.region = region
        self._client = boto3.client("secretsmanager", region_name=region)
        self._default_secret_arn = os.environ.get("SECRETS_ARN", "")

    def get_credentials(
        self, secret_key: Optional[str] = None
    ) -> WebsiteCredentials:
        """
        Get website credentials from Secrets Manager.
        Uses caching to reduce API calls.
        """
        secret_id = secret_key or self._default_secret_arn

        if not secret_id:
            raise ValueError(
                "No secret ARN provided and SECRETS_ARN environment variable not set"
            )

        # Check cache first
        cached = self._get_cached(secret_id)
        if cached:
            self.logger.debug(
                "Retrieved credentials from cache",
                secret_id=self._mask_secret_id(secret_id),
            )
            return cached

        # Fetch from Secrets Manager
        self.logger.info(
            "Fetching credentials from Secrets Manager",
            secret_id=self._mask_secret_id(secret_id),
        )

        try:
            response = self._client.get_secret_value(SecretId=secret_id)

            if "SecretString" not in response:
                raise ValueError("Secret does not contain a string value")

            secret_data = json.loads(response["SecretString"])
            credentials = WebsiteCredentials(**secret_data)

            # Cache the credentials
            self._set_cache(secret_id, credentials)

            self.logger.info(
                "Credentials retrieved successfully",
                secret_id=self._mask_secret_id(secret_id),
                has_otp_secret=credentials.otp_secret is not None,
            )

            return credentials

        except ClientError as e:
            self.logger.error(
                "Failed to retrieve credentials",
                secret_id=self._mask_secret_id(secret_id),
                error=str(e),
            )
            raise

    def get_credentials_for_domain(self, domain: str) -> WebsiteCredentials:
        """
        Get credentials for a specific domain.
        Falls back to default secret if domain-specific not found.
        """
        domain_secret_key = f"crawler/credentials/{domain}"

        try:
            return self.get_credentials(domain_secret_key)
        except ClientError:
            self.logger.info(
                "Domain-specific secret not found, using default",
                domain=domain,
            )
            return self.get_credentials()

    def clear_cache(self) -> None:
        """Clear the secrets cache (useful for rotation)"""
        global _secrets_cache
        _secrets_cache.clear()
        self.logger.info("Secrets cache cleared")

    def clear_cache_entry(self, secret_id: str) -> None:
        """Clear a specific secret from cache"""
        if secret_id in _secrets_cache:
            del _secrets_cache[secret_id]
            self.logger.debug(
                "Secret cache entry cleared",
                secret_id=self._mask_secret_id(secret_id),
            )

    def _get_cached(self, secret_id: str) -> Optional[WebsiteCredentials]:
        """Get credentials from cache if not expired"""
        if secret_id in _secrets_cache:
            credentials, expires_at = _secrets_cache[secret_id]
            if time.time() < expires_at:
                return credentials
            # Remove expired entry
            del _secrets_cache[secret_id]
        return None

    def _set_cache(self, secret_id: str, credentials: WebsiteCredentials) -> None:
        """Store credentials in cache"""
        expires_at = time.time() + CACHE_TTL_SECONDS
        _secrets_cache[secret_id] = (credentials, expires_at)

    def _mask_secret_id(self, secret_id: str) -> str:
        """Mask the secret ID for logging"""
        if len(secret_id) <= 20:
            return secret_id[:5] + "***"
        return secret_id[:10] + "***" + secret_id[-5:]


def create_secrets_manager(
    logger: ContextLogger, region: Optional[str] = None
) -> SecretsManager:
    """Create a SecretsManager instance"""
    return SecretsManager(logger, region or "us-west-1")
