"""
S3 Storage utilities for saving crawl results and screenshots
"""

import json
import os
from datetime import datetime
from typing import Optional
from urllib.parse import urlparse

import boto3
from botocore.exceptions import ClientError

from ..models.types import CrawlerResult, ScreenshotResult
from .logger import ContextLogger


class StorageManager:
    """Manages S3 storage for crawler results"""

    def __init__(self, logger: ContextLogger, region: str = "us-west-1"):
        self.logger = logger
        self.region = region
        self._client = boto3.client("s3", region_name=region)
        self._bucket = os.environ.get("RESULTS_BUCKET", "")

    async def save_result(self, result: CrawlerResult) -> str:
        """Save crawler result to S3"""
        if not self._bucket:
            raise ValueError("RESULTS_BUCKET environment variable not set")

        key = self._generate_result_key(result)

        self.logger.info(
            "Saving crawler result to S3",
            bucket=self._bucket,
            key=key,
            task_id=result.task_id,
        )

        try:
            self._client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=result.model_dump_json(indent=2),
                ContentType="application/json",
                Metadata={
                    "task_id": result.task_id,
                    "url": result.url,
                    "success": str(result.success),
                    "timestamp": result.timestamp.isoformat(),
                },
            )

            s3_url = f"s3://{self._bucket}/{key}"
            self.logger.info("Result saved successfully", s3_url=s3_url)
            return s3_url

        except ClientError as e:
            self.logger.error("Failed to save result", error=str(e))
            raise

    async def save_screenshot(
        self,
        task_id: str,
        name: str,
        data: bytes,
    ) -> ScreenshotResult:
        """Save screenshot to S3"""
        if not self._bucket:
            raise ValueError("RESULTS_BUCKET environment variable not set")

        key = self._generate_screenshot_key(task_id, name)

        self.logger.info(
            "Saving screenshot to S3",
            bucket=self._bucket,
            key=key,
            size=len(data),
        )

        try:
            self._client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=data,
                ContentType="image/png",
                Metadata={
                    "task_id": task_id,
                    "name": name,
                },
            )

            s3_url = f"s3://{self._bucket}/{key}"
            self.logger.info("Screenshot saved successfully", s3_url=s3_url)

            return ScreenshotResult(
                name=name,
                s3_key=key,
                s3_url=s3_url,
            )

        except ClientError as e:
            self.logger.error("Failed to save screenshot", error=str(e))
            raise

    async def save_html(self, task_id: str, url: str, html: str) -> str:
        """Save raw HTML content to S3"""
        if not self._bucket:
            raise ValueError("RESULTS_BUCKET environment variable not set")

        key = self._generate_html_key(task_id, url)

        self.logger.info(
            "Saving HTML to S3",
            bucket=self._bucket,
            key=key,
            size=len(html),
        )

        try:
            self._client.put_object(
                Bucket=self._bucket,
                Key=key,
                Body=html.encode("utf-8"),
                ContentType="text/html",
                Metadata={
                    "task_id": task_id,
                    "url": url,
                },
            )

            return f"s3://{self._bucket}/{key}"

        except ClientError as e:
            self.logger.error("Failed to save HTML", error=str(e))
            raise

    def get_presigned_url(self, key: str, expires_in: int = 3600) -> str:
        """Get a pre-signed URL for downloading a result"""
        return self._client.generate_presigned_url(
            "get_object",
            Params={"Bucket": self._bucket, "Key": key},
            ExpiresIn=expires_in,
        )

    def _generate_result_key(self, result: CrawlerResult) -> str:
        """Generate a unique key for storing results"""
        date_prefix = self._get_date_prefix(result.timestamp)
        domain = self._extract_domain(result.url)
        return f"results/{date_prefix}/{domain}/{result.task_id}.json"

    def _generate_screenshot_key(self, task_id: str, name: str) -> str:
        """Generate a unique key for storing screenshots"""
        date_prefix = self._get_date_prefix(datetime.utcnow())
        sanitized_name = "".join(
            c if c.isalnum() or c in "-_" else "_" for c in name
        )
        return f"screenshots/{date_prefix}/{task_id}/{sanitized_name}.png"

    def _generate_html_key(self, task_id: str, url: str) -> str:
        """Generate a unique key for storing HTML"""
        date_prefix = self._get_date_prefix(datetime.utcnow())
        domain = self._extract_domain(url)
        return f"html/{date_prefix}/{domain}/{task_id}.html"

    def _get_date_prefix(self, dt: datetime) -> str:
        """Get date prefix for organizing S3 objects"""
        return dt.strftime("%Y/%m/%d")

    def _extract_domain(self, url: str) -> str:
        """Extract domain from URL"""
        try:
            parsed = urlparse(url)
            return parsed.hostname.replace(".", "_") if parsed.hostname else "unknown"
        except Exception:
            return "unknown"


def create_storage_manager(
    logger: ContextLogger, region: Optional[str] = None
) -> StorageManager:
    """Create a StorageManager instance"""
    return StorageManager(logger, region or "us-west-1")
