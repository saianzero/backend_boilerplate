"""
S3 helper (boto3, sync client).

boto3 is synchronous; the calls are short so they are used directly. For very
large uploads in request handlers wrap in ``asyncio.to_thread``.

Typical flows
-------------
Browser-direct upload (recommended for large files):
    url = aws.generate_presigned_put_url(object_name, content_type)   # 1. give client a PUT url
    # client PUTs bytes to ``url``
    path = await aws.download_file_from_s3(object_name)                # 2. worker pulls it later

Server-side upload:
    public_url = aws.upload_file(Path("/tmp/x.pdf"), key="uploads/x.pdf", content_type="application/pdf")

Read link for the frontend:
    aws.get_presigned_url(object_name)   # expires after PRESIGNED_URL_EXPIRY_SECONDS

Cleanup:
    aws.delete_object(object_name_or_public_url)
"""

import logging
import tempfile
from pathlib import Path
from urllib.parse import urlparse

import boto3
from botocore.exceptions import ClientError

from src.core.config import (
    AWS_ACCESS_KEY,
    AWS_SECRET_ACCESS_KEY,
    PRESIGNED_URL_EXPIRY_SECONDS,
    S3_BUCKET_NAME,
    S3_BUCKET_REGION,
)

logger = logging.getLogger(__name__)


class AwsUtil:
    def __init__(self, bucket_name: str = S3_BUCKET_NAME, region: str = S3_BUCKET_REGION):
        self.bucket_name = bucket_name
        self.region = region
        # Empty keys -> boto3 falls back to the default credential chain (IAM role, env, ~/.aws).
        self.s3_client = boto3.client(
            "s3",
            aws_access_key_id=AWS_ACCESS_KEY or None,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY or None,
            region_name=region,
            endpoint_url=f"https://s3.{region}.amazonaws.com",
        )

    # ----------------------------------------------------------- presigned --
    def get_presigned_url(self, object_name: str, bucket_name: str | None = None) -> str:
        """Time-limited GET url for a private object."""
        return self.s3_client.generate_presigned_url(
            "get_object",
            Params={"Bucket": bucket_name or self.bucket_name, "Key": object_name},
            ExpiresIn=PRESIGNED_URL_EXPIRY_SECONDS,
        )

    def generate_presigned_put_url(
        self, object_name: str, content_type: str, bucket_name: str | None = None
    ) -> str:
        """Time-limited PUT url so the browser uploads straight to S3."""
        return self.s3_client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": bucket_name or self.bucket_name,
                "Key": object_name,
                "ContentType": content_type,
            },
            ExpiresIn=PRESIGNED_URL_EXPIRY_SECONDS,
        )

    # -------------------------------------------------------------- upload --
    def upload_file(self, filepath: Path | str, key: str, content_type: str) -> str:
        """Upload a local file and return its public URL."""
        self.s3_client.upload_file(
            Filename=str(filepath),
            Bucket=self.bucket_name,
            Key=key,
            ExtraArgs={"ContentType": content_type} if content_type else None,
        )
        return self.public_url(key)

    def public_url(self, key: str) -> str:
        return f"https://{self.bucket_name}.s3.{self.region}.amazonaws.com/{key}"

    # ------------------------------------------------------------ download --
    async def download_file_from_s3(self, object_name: str, bucket_name: str | None = None) -> str:
        """Download to a temp file and return its path. Caller deletes it."""
        temp_file = tempfile.NamedTemporaryFile(delete=False)
        try:
            self.s3_client.download_file(
                bucket_name or self.bucket_name, object_name, temp_file.name
            )
            return temp_file.name
        except ClientError as e:
            raise RuntimeError(f"Failed to download S3 object {object_name}: {e}") from e

    # -------------------------------------------------------------- delete --
    def delete_object(self, key_or_url: str, bucket_name: str | None = None) -> bool:
        """Delete by object key or by the public URL ``upload_file`` returned."""
        key = key_or_url
        if key_or_url.startswith("http"):
            key = urlparse(key_or_url).path.lstrip("/")
        try:
            self.s3_client.delete_object(Bucket=bucket_name or self.bucket_name, Key=key)
            return True
        except ClientError as e:
            logger.warning(f"Failed to delete S3 object {key}: {e}")
            return False
