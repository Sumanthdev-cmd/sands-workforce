import os
from pathlib import Path
from typing import Any


DEFAULT_PRESIGN_EXPIRY_SECONDS = 900


def load_backend_env() -> None:
    """Load simple KEY=VALUE entries from backend/.env into os.environ."""

    backend_root = Path(__file__).resolve().parents[2]
    env_path = backend_root / ".env"

    if not env_path.exists():
        return

    for raw_line in env_path.read_text(encoding="utf-8-sig").splitlines():
        line = raw_line.strip()

        if not line or line.startswith("#") or "=" not in line:
            continue

        key, value = line.split("=", 1)
        key = key.strip().lstrip("\ufeff")
        value = value.strip().strip('"').strip("'")

        if key:
            os.environ.setdefault(key, value)


def get_storage_config() -> tuple[str, str]:
    load_backend_env()

    bucket = os.getenv("S3_DOCUMENT_BUCKET", "").strip()
    region = os.getenv("AWS_REGION", "ap-south-2").strip()

    if not bucket:
        raise RuntimeError(
            "S3_DOCUMENT_BUCKET is not configured in the backend .env file."
        )

    return bucket, region


def get_s3_client() -> Any:
    load_backend_env()

    try:
        import boto3
    except ImportError as error:
        raise RuntimeError(
            "boto3 is not installed. Run: pip install boto3"
        ) from error

    _, region = get_storage_config()

    return boto3.client(
    "s3",
    region_name=region,
    endpoint_url=f"https://s3.{region}.amazonaws.com",
)


def create_upload_url(
    *,
    bucket: str,
    key: str,
    content_type: str,
    expires_in: int = DEFAULT_PRESIGN_EXPIRY_SECONDS,
) -> str:
    client = get_s3_client()

    return client.generate_presigned_url(
        "put_object",
        Params={
            "Bucket": bucket,
            "Key": key,
            "ContentType": content_type,
        },
        ExpiresIn=expires_in,
    )


def create_download_url(
    *,
    bucket: str,
    key: str,
    file_name: str,
    expires_in: int = DEFAULT_PRESIGN_EXPIRY_SECONDS,
) -> str:
    client = get_s3_client()

    return client.generate_presigned_url(
        "get_object",
        Params={
            "Bucket": bucket,
            "Key": key,
            "ResponseContentDisposition": (
                f'attachment; filename="{file_name}"'
            ),
        },
        ExpiresIn=expires_in,
    )



def create_preview_url(
    *,
    bucket: str,
    key: str,
    file_name: str,
    content_type: str,
    expires_in: int = DEFAULT_PRESIGN_EXPIRY_SECONDS,
) -> str:
    # Short-lived browser preview URL. Supported images and PDFs
    # open inline instead of being forced to download.
    client = get_s3_client()

    return client.generate_presigned_url(
        "get_object",
        Params={
            "Bucket": bucket,
            "Key": key,
            "ResponseContentDisposition": (
                f'inline; filename="{file_name}"'
            ),
            "ResponseContentType": content_type,
        },
        ExpiresIn=expires_in,
    )
