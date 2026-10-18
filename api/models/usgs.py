"""USGS continuous-parameter codes collected for Fox River at Green Bay."""

REQUESTED_PARAMETER_CODES: tuple[str, ...] = (
    "32319",
    "32316",
    "00300",
    "00400",
    "00010",
    "00671",
    "00631",
    "00608",
    "00060",
    "63680",
    "00095",
)

# Backward-compatible alias used in SQL and status payloads.
PARAMETERS = REQUESTED_PARAMETER_CODES
