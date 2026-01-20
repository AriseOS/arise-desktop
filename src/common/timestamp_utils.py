"""
Unified Timestamp Utilities

Provides consistent timestamp generation and comparison across the application.
All timestamps use ISO 8601 format with UTC timezone: YYYY-MM-DDTHH:MM:SS.ffffff+00:00
"""

from datetime import datetime, timezone
from typing import Optional


def get_current_timestamp() -> str:
    """
    Get current UTC timestamp in ISO 8601 format

    Returns:
        Timestamp string in format: "2025-12-07T10:16:08.360031+00:00"
        Always uses +00:00 suffix (not Z) for consistency
    """
    return datetime.now(timezone.utc).isoformat()


def parse_timestamp(timestamp_str: str) -> Optional[datetime]:
    """
    Parse ISO 8601 timestamp string to datetime object

    Handles formats:
    - "2025-12-07T10:16:08.360031Z" (Z suffix)
    - "2025-12-07T10:16:08.360031+00:00" (+00:00 suffix)
    - "2025-12-07T10:16:08.360031" (no timezone - assumes UTC)

    Args:
        timestamp_str: ISO 8601 timestamp string

    Returns:
        datetime object with UTC timezone, or None if parsing fails
    """
    if not timestamp_str:
        return None

    try:
        # Handle Z suffix by replacing with +00:00
        if timestamp_str.endswith('Z'):
            timestamp_str = timestamp_str[:-1] + '+00:00'

        dt = datetime.fromisoformat(timestamp_str)

        # If no timezone info, assume UTC
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)

        return dt
    except (ValueError, AttributeError):
        return None


def compare_timestamps(ts1: str, ts2: str) -> int:
    """
    Compare two timestamp strings

    Args:
        ts1: First timestamp string
        ts2: Second timestamp string

    Returns:
        -1 if ts1 < ts2
         0 if ts1 == ts2
         1 if ts1 > ts2
        None if either timestamp is invalid
    """
    dt1 = parse_timestamp(ts1)
    dt2 = parse_timestamp(ts2)

    if dt1 is None or dt2 is None:
        return None

    if dt1 < dt2:
        return -1
    elif dt1 > dt2:
        return 1
    else:
        return 0


def is_timestamp_newer(ts1: str, ts2: str) -> bool:
    """
    Check if ts1 is newer than ts2

    Args:
        ts1: First timestamp string
        ts2: Second timestamp string

    Returns:
        True if ts1 > ts2, False otherwise
    """
    result = compare_timestamps(ts1, ts2)
    return result == 1 if result is not None else False
