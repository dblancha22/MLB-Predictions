"""Shared configuration, date, and Supabase helpers for ingestion commands."""

from __future__ import annotations

import argparse
import os
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, List, Optional
from urllib.parse import urlparse, urlunparse
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


EXPECTED_SUPABASE_PROJECT_REF = "soakgdpuvtxadjextekg"
DEFAULT_ENV_FILE = Path(__file__).resolve().parents[2] / ".env"
DEFAULT_TIMEZONE = "America/Los_Angeles"


class IngestionError(RuntimeError):
    """Raised when source data or configuration cannot be safely ingested."""


def load_env_file(path: Path) -> None:
    """Load simple KEY=VALUE entries without overwriting process variables."""
    if not path.exists():
        return
    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key:
            continue
        if len(value) >= 2 and value[0] == value[-1] and value[0] in {"'", '"'}:
            value = value[1:-1]
        os.environ.setdefault(key, value)


def normalize_supabase_url(value: str) -> str:
    """Return the project base URL, accepting a legacy trailing /rest/v1 path."""
    parsed = urlparse(value.strip().rstrip("/"))
    if parsed.scheme != "https" or not parsed.hostname:
        raise IngestionError("SUPABASE_URL must be a valid HTTPS project URL")
    normalized_path = parsed.path.rstrip("/")
    if normalized_path not in {"", "/rest/v1"}:
        raise IngestionError(
            "SUPABASE_URL must be the project base URL or end with /rest/v1"
        )
    return urlunparse((parsed.scheme, parsed.netloc, "", "", "", ""))


def parse_iso_date(value: str) -> date:
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError(
            f"invalid date {value!r}; expected YYYY-MM-DD"
        ) from exc


def build_date_range(
    single_date: Optional[date], start_date: Optional[date], end_date: Optional[date]
) -> List[date]:
    if single_date is not None:
        if start_date is not None or end_date is not None:
            raise IngestionError("--date cannot be combined with a date range")
        return [single_date]
    if start_date is None or end_date is None:
        raise IngestionError("provide --date or both --start-date and --end-date")
    if start_date > end_date:
        raise IngestionError("--start-date must be on or before --end-date")
    return [
        start_date + timedelta(days=offset)
        for offset in range((end_date - start_date).days + 1)
    ]


def resolve_yesterday(timezone_name: str, now: Optional[datetime] = None) -> date:
    """Resolve the previous local calendar date in an explicit IANA timezone."""
    try:
        timezone = ZoneInfo(timezone_name)
    except ZoneInfoNotFoundError as exc:
        raise IngestionError(f"unknown IANA timezone {timezone_name!r}") from exc
    current = datetime.now(timezone) if now is None else now.astimezone(timezone)
    return current.date() - timedelta(days=1)


def validate_runtime_options(timeout: float, retries: int) -> None:
    if retries < 0:
        raise IngestionError("--retries cannot be negative")
    if timeout <= 0:
        raise IngestionError("--timeout must be positive")


def create_supabase_client(env_file: Path) -> Any:
    load_env_file(env_file)
    raw_url = os.getenv("SUPABASE_URL", "").strip()
    secret_key = (
        os.getenv("SUPABASE_SECRET_KEY", "").strip()
        or os.getenv("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    )
    if not raw_url:
        raise IngestionError("SUPABASE_URL is not set")
    if not secret_key:
        raise IngestionError(
            "SUPABASE_SECRET_KEY or SUPABASE_SERVICE_ROLE_KEY is not set"
        )
    supabase_url = normalize_supabase_url(raw_url)
    project_ref = (urlparse(supabase_url).hostname or "").split(".", 1)[0]
    if project_ref != EXPECTED_SUPABASE_PROJECT_REF:
        raise IngestionError(
            "SUPABASE_URL does not point to the expected BagBrainOfficial project "
            f"({EXPECTED_SUPABASE_PROJECT_REF})"
        )
    try:
        from supabase import create_client
    except ImportError as exc:
        raise IngestionError(
            "supabase-py is not installed; run: "
            "python -m pip install -r requirements-ingestion.txt"
        ) from exc
    return create_client(supabase_url, secret_key)

