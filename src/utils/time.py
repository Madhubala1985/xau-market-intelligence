"""Timestamp normalization helpers.

Per 06_DATA_POLICY.md:
- All data must be normalized to one internal timezone (UTC).
- The system must preserve the broker timestamp and the normalized timestamp.
- Naive (timezone-unaware) datetimes are treated as malformed and rejected,
  because an unknown timezone is a timezone-mismatch / look-ahead risk.
"""

from __future__ import annotations

from datetime import datetime, timezone

# The single internal timezone used for all normalized timestamps.
INTERNAL_TZ = timezone.utc


def is_aware(value: datetime) -> bool:
    """Return True if the datetime carries an explicit UTC offset."""
    return value.tzinfo is not None and value.tzinfo.utcoffset(value) is not None


def ensure_aware(value: datetime, field_name: str = "timestamp") -> datetime:
    """Require a timezone-aware datetime, preserving its original offset.

    Used for broker timestamps, which must be preserved as reported by the
    broker but must still be unambiguous about their timezone.
    """
    if not isinstance(value, datetime):
        raise TypeError(f"{field_name} must be a datetime, got {type(value).__name__}")
    if not is_aware(value):
        raise ValueError(f"{field_name} must be timezone-aware (got naive datetime)")
    return value


def to_utc(value: datetime, field_name: str = "timestamp") -> datetime:
    """Normalize a timezone-aware datetime to the internal timezone (UTC).

    Naive datetimes are rejected to avoid silent timezone assumptions.
    """
    return ensure_aware(value, field_name).astimezone(INTERNAL_TZ)
