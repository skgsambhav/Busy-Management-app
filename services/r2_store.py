"""
r2_store.py — Cloudflare R2 Storage Service
Handles upload, URL generation, and 30-day TTL cleanup for HTML invoices & ledgers.
All R2 interactions are isolated here. Uses boto3 S3-compatible API.
"""

import boto3
import datetime
import io
import logging
import random
import string
from botocore.config import Config

# ─── Inline credentials (from config.py) ────────────────────────────────────
from config import (
    R2_ACCESS_KEY_ID,
    R2_SECRET_ACCESS_KEY,
    R2_ENDPOINT_URL,
    R2_BUCKET_NAME,
    R2_PUBLIC_BASE_URL,
    R2_TTL_DAYS
)

logger = logging.getLogger(__name__)

# ─── R2 Client (lazy init) ──────────────────────────────────────────────────
_r2_client = None

def _get_client():
    """Get or create the boto3 R2 client (thread-safe lazy init)."""
    global _r2_client
    if _r2_client is None:
        _r2_client = boto3.client(
            "s3",
            endpoint_url=R2_ENDPOINT_URL,
            aws_access_key_id=R2_ACCESS_KEY_ID,
            aws_secret_access_key=R2_SECRET_ACCESS_KEY,
            region_name="auto",
            config=Config(
                signature_version="s3v4",
                retries={"max_attempts": 3, "mode": "standard"}
            )
        )
    return _r2_client


# ─── Upload ─────────────────────────────────────────────────────────────────

def upload_invoice_html(vcode: int, html_content: str) -> str:
    """
    Upload a sales invoice HTML to R2.
    Returns the public URL.
    Key pattern: i/{vcode}_{4chars}.html
    """
    suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
    key = f"i/{vcode}_{suffix}.html"
    return _upload_html(key, html_content, doc_type="invoice", ref_id=str(vcode))


def upload_ledger_html(party_code: int, html_content: str) -> str:
    """
    Upload a ledger HTML to R2.
    Returns the public URL.
    Key pattern: l/{party_code}_{4chars}.html
    """
    suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
    key = f"l/{party_code}_{suffix}.html"
    return _upload_html(key, html_content, doc_type="ledger", ref_id=str(party_code))


def _upload_html(key: str, html_content: str, doc_type: str = "document", ref_id: str = "") -> str:
    """Internal: upload HTML bytes to R2 and return public URL."""
    client = _get_client()
    uploaded_at = datetime.datetime.utcnow().isoformat()

    html_bytes = html_content.encode("utf-8")

    client.put_object(
        Bucket=R2_BUCKET_NAME,
        Key=key,
        Body=io.BytesIO(html_bytes),
        ContentType="text/html; charset=utf-8",
        ContentLength=len(html_bytes),
        Metadata={
            "uploaded_at": uploaded_at,
            "type": doc_type,
            "ref_id": ref_id
        }
    )

    public_url = f"{R2_PUBLIC_BASE_URL}/{key}"
    logger.info(f"[R2] Uploaded {doc_type} → {public_url}")
    return public_url


# ─── Public URL ─────────────────────────────────────────────────────────────

def get_public_url(key: str) -> str:
    """Construct the public URL for a given R2 object key."""
    return f"{R2_PUBLIC_BASE_URL}/{key}"


# ─── 30-Day Cleanup ─────────────────────────────────────────────────────────

def delete_old_objects(days: int = None) -> dict:
    """
    Delete all R2 objects older than `days` days (based on LastModified timestamp).
    Returns stats dict: { deleted: int, skipped: int, errors: int }
    """
    if days is None:
        days = R2_TTL_DAYS

    client = _get_client()
    cutoff = datetime.datetime.utcnow() - datetime.timedelta(days=days)
    # Make cutoff timezone-aware (UTC)
    cutoff = cutoff.replace(tzinfo=datetime.timezone.utc)

    stats = {"deleted": 0, "skipped": 0, "errors": 0}

    paginator = client.get_paginator("list_objects_v2")
    pages = paginator.paginate(Bucket=R2_BUCKET_NAME)

    objects_to_delete = []
    for page in pages:
        for obj in page.get("Contents", []):
            last_modified = obj["LastModified"]
            if last_modified < cutoff:
                objects_to_delete.append({"Key": obj["Key"]})
            else:
                stats["skipped"] += 1

    # Batch delete in chunks of 1000 (S3 limit)
    chunk_size = 1000
    for i in range(0, len(objects_to_delete), chunk_size):
        chunk = objects_to_delete[i:i + chunk_size]
        try:
            resp = client.delete_objects(
                Bucket=R2_BUCKET_NAME,
                Delete={"Objects": chunk, "Quiet": True}
            )
            deleted = len(chunk) - len(resp.get("Errors", []))
            stats["deleted"] += deleted
            stats["errors"] += len(resp.get("Errors", []))
        except Exception as e:
            logger.error(f"[R2] Batch delete error: {e}")
            stats["errors"] += len(chunk)

    logger.info(f"[R2] Cleanup done: {stats}")
    return stats


# ─── Connection Test ─────────────────────────────────────────────────────────

def test_connection() -> dict:
    """Test R2 connectivity by listing bucket objects (limit 1)."""
    try:
        client = _get_client()
        client.list_objects_v2(Bucket=R2_BUCKET_NAME, MaxKeys=1)
        return {"success": True, "message": f"Connected to R2 bucket: {R2_BUCKET_NAME}"}
    except Exception as e:
        return {"success": False, "error": str(e)}
