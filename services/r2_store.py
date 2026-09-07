"""
r2_store.py — Cloudflare R2 Storage Service
Handles upload, URL generation, and canonical link management for HTML invoices & ledgers.
All R2 interactions are isolated here. Uses boto3 S3-compatible API.

Canonical URL Strategy:
  - Each upload saves an ARCHIVED versioned copy:   i/{vcode}_{4chars}.html
  - AND overwrites a CANONICAL fixed-URL file:      i/{vcode}.html
  - WhatsApp always receives the canonical URL.
  - Result: Any old link sent previously will auto-show the LATEST bill.
"""

import boto3
import datetime
import io
import logging
import random
import re
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


def delete_objects_by_prefix(prefix: str):
    """
    Delete all existing R2 objects matching a given prefix.
    Example: prefix="i/5454_" or prefix="pdf/GOPALMRKT-Sale-GM4165"
    """
    if not prefix:
        return
    try:
        client = _get_client()
        paginator = client.get_paginator("list_objects_v2")
        pages = paginator.paginate(Bucket=R2_BUCKET_NAME, Prefix=prefix)
        objects_to_delete = []
        for page in pages:
            for obj in page.get("Contents", []):
                objects_to_delete.append({"Key": obj["Key"]})
        
        if objects_to_delete:
            client.delete_objects(
                Bucket=R2_BUCKET_NAME,
                Delete={"Objects": objects_to_delete, "Quiet": True}
            )
            logger.info(f"[R2] Deleted {len(objects_to_delete)} old object(s) with prefix '{prefix}'")
    except Exception as e:
        logger.warning(f"[R2] Could not delete old prefix '{prefix}': {e}")


# ─── Upload ─────────────────────────────────────────────────────────────────

def upload_invoice_html(vcode: int, html_content: str) -> str:
    """
    Upload a sales invoice HTML to R2.

    Two files are written:
      1. Archive copy  → i/{vcode}_{4chars}.html   (versioned, never deleted)
      2. Canonical     → i/{vcode}.html             (always overwritten with latest)

    Returns the CANONICAL URL — so any previously sent WhatsApp link
    automatically opens the latest version of this bill.
    """
    # 1. Archive copy (keep history, unique suffix)
    suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
    archive_key = f"i/{vcode}_{suffix}.html"
    _upload_html(archive_key, html_content, doc_type="invoice_archive", ref_id=str(vcode))
    logger.info(f"[R2] Invoice archive saved → {archive_key}")

    # 2. Canonical file (fixed URL — always latest)
    canonical_key = f"i/{vcode}.html"
    canonical_url = _upload_html(canonical_key, html_content, doc_type="invoice", ref_id=str(vcode))
    logger.info(f"[R2] Invoice canonical updated → {canonical_key}")

    return canonical_url


def upload_ledger_html(party_code: int, html_content: str) -> str:
    """
    Upload a ledger HTML to R2.

    Two files are written:
      1. Archive copy  → l/{party_code}_{4chars}.html  (versioned, never deleted)
      2. Canonical     → l/{party_code}.html            (always overwritten with latest)

    Returns the CANONICAL URL — so any previously sent WhatsApp link
    automatically opens the latest ledger statement.
    """
    # 1. Archive copy
    suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
    archive_key = f"l/{party_code}_{suffix}.html"
    _upload_html(archive_key, html_content, doc_type="ledger_archive", ref_id=str(party_code))
    logger.info(f"[R2] Ledger archive saved → {archive_key}")

    # 2. Canonical file (fixed URL — always latest)
    canonical_key = f"l/{party_code}.html"
    canonical_url = _upload_html(canonical_key, html_content, doc_type="ledger", ref_id=str(party_code))
    logger.info(f"[R2] Ledger canonical updated → {canonical_key}")

    return canonical_url


def upload_receipt_html(vcode: int, html_content: str) -> str:
    """
    Upload a payment receipt HTML to R2.

    Two files are written:
      1. Archive copy  → r/{vcode}_{4chars}.html  (versioned, never deleted)
      2. Canonical     → r/{vcode}.html            (always overwritten with latest)

    Returns the CANONICAL URL — so any previously sent WhatsApp link
    automatically opens the latest receipt.
    """
    # 1. Archive copy
    suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
    archive_key = f"r/{vcode}_{suffix}.html"
    _upload_html(archive_key, html_content, doc_type="receipt_archive", ref_id=str(vcode))
    logger.info(f"[R2] Receipt archive saved → {archive_key}")

    # 2. Canonical file (fixed URL — always latest)
    canonical_key = f"r/{vcode}.html"
    canonical_url = _upload_html(canonical_key, html_content, doc_type="receipt", ref_id=str(vcode))
    logger.info(f"[R2] Receipt canonical updated → {canonical_key}")

    return canonical_url


def upload_pdf_bytes(pdf_bytes: bytes, filename: str = "Invoice.pdf", ref_id: str = "") -> str:
    """
    Upload a PDF document to R2.

    Two files are written:
      1. Archive copy  → pdf/{clean_name}_{4chars}.pdf  (versioned, never deleted)
      2. Canonical     → pdf/{clean_name}.pdf            (always overwritten with latest)

    Returns the CANONICAL URL — so any previously sent PDF link
    automatically downloads the latest version.
    """
    raw_name = filename[:-4] if filename.lower().endswith(".pdf") else filename
    clean_name = "".join(c for c in raw_name if c.isalnum() or c in ('-', '_')).rstrip()
    if not clean_name:
        clean_name = "invoice"

    # 1. Archive copy (versioned)
    suffix = ''.join(random.choices(string.ascii_lowercase + string.digits, k=4))
    archive_key = f"pdf/{clean_name}_{suffix}.pdf"
    _upload_bytes(archive_key, pdf_bytes, content_type="application/pdf", doc_type="invoice_pdf_archive", ref_id=ref_id)
    logger.info(f"[R2] PDF archive saved → {archive_key}")

    # 2. Canonical file (fixed URL — always latest)
    canonical_key = f"pdf/{clean_name}.pdf"
    canonical_url = _upload_bytes(canonical_key, pdf_bytes, content_type="application/pdf", doc_type="invoice_pdf", ref_id=ref_id)
    logger.info(f"[R2] PDF canonical updated → {canonical_key}")

    return canonical_url



def _upload_bytes(key: str, data_bytes: bytes, content_type: str = "application/octet-stream", doc_type: str = "document", ref_id: str = "") -> str:
    """Internal: upload raw bytes to R2 and return public URL."""
    client = _get_client()
    uploaded_at = datetime.datetime.utcnow().isoformat()

    client.put_object(
        Bucket=R2_BUCKET_NAME,
        Key=key,
        Body=io.BytesIO(data_bytes),
        ContentType=content_type,
        ContentLength=len(data_bytes),
        Metadata={
            "uploaded_at": uploaded_at,
            "type": doc_type,
            "ref_id": ref_id
        }
    )

    public_url = f"{R2_PUBLIC_BASE_URL}/{key}"
    logger.info(f"[R2] Uploaded {doc_type} → {public_url}")
    return public_url


def _upload_html(key: str, html_content: str, doc_type: str = "document", ref_id: str = "") -> str:
    """Internal: upload HTML bytes to R2 and return public URL."""
    return _upload_bytes(key, html_content.encode("utf-8"), content_type="text/html; charset=utf-8", doc_type=doc_type, ref_id=ref_id)



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
