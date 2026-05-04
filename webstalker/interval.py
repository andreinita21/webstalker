INTERVAL_UNITS: dict[str, int] = {
    "seconds": 1,
    "minutes": 60,
    "hours": 3600,
    "days": 86400,
    "weeks": 604800,
    "months": 30 * 86400,
}

UNIT_ORDER = ["seconds", "minutes", "hours", "days", "weeks", "months"]


def to_seconds(value: int, unit: str) -> int:
    if unit not in INTERVAL_UNITS:
        raise ValueError(f"unknown interval unit: {unit}")
    if value < 1:
        raise ValueError("interval value must be >= 1")
    return int(value) * INTERVAL_UNITS[unit]


def humanize(value: int, unit: str) -> str:
    if value == 1:
        return f"every {unit[:-1]}"
    return f"every {value} {unit}"
