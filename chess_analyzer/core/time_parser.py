# chess_analyzer/core/time_parser.py
"""
Provides a pure, stateless utility function to parse PGN clock annotations.

This module is designed to be a robust and efficient utility for extracting
time information from PGN comments. It handles the common `[%clk H:MM:SS.d]`
format and gracefully fails on malformed or missing input. As a pure component,
it has no side effects and is easy to test in isolation.
"""

import re
from typing import Optional

# A robust, pre-compiled regex to capture the [%clk H:MM:SS.d] format.
# Pre-compiling the regex is a performance best practice if it's used frequently.
CLK_PATTERN = re.compile(
    r"\[%clk\s+"               # Literal start of the tag
    r"((?P<h>\d+):)?"          # Optional hours group (e.g., "1:")
    r"(?P<m>\d{1,2}):"         # Minutes group (e.g., "05:")
    r"(?P<s>\d{1,2})"          # Seconds group (e.g., "33")
    r"(\.(?P<ds>\d+))?"        # Optional fractional seconds group (e.g., ".7")
    r"\s*\]"                   # Literal end of the tag
)


def parse_clk_comment_to_seconds(comment: Optional[str]) -> Optional[float]:
    """
    Parses a PGN clock annotation string to the total seconds remaining on the clock.

    Example anntotations handled:
    - "[%clk 0:05:33.7]"
    - "[%clk 1:30:05]"
    - "[%clk 0:01:15]"

    Args:
        comment: The PGN comment string, which may contain a clock tag.

    Returns:
        The total seconds remaining as a float if parsing is successful,
        otherwise None.
    """
    if not comment:
        return None

    match = CLK_PATTERN.search(comment)
    if not match:
        return None

    parts = match.groupdict()
    try:
        hours = int(parts.get("h") or 0)
        minutes = int(parts.get("m") or 0)
        seconds = int(parts.get("s") or 0)
        
        # Handle fractional seconds (e.g., deciseconds, centiseconds).
        deciseconds_str = parts.get("ds") or "0"
        fractional_seconds = float(f"0.{deciseconds_str}")
        
        # Validate that minutes and seconds are within a valid range.
        if minutes >= 60 or seconds >= 60:
            return None 

        total_seconds = (hours * 3600) + (minutes * 60) + seconds + fractional_seconds
        return total_seconds
    except (ValueError, TypeError):
        # This catches cases where a part could not be converted to a number.
        return None