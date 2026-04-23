def meters_to_kilometers(value: float | int | None) -> float | None:
    if value is None:
        return None

    return round(float(value) / 1000, 3)


def seconds_to_int(value: float | int | None) -> int | None:
    if value is None:
        return None

    return round(float(value))


def speed_mps_to_pace_min_per_km(value: float | int | None) -> float | None:
    if value is None:
        return None

    speed = float(value)
    if speed <= 0:
        return None

    return 1000 / speed / 60


def duration_distance_to_pace_min_per_km(
    duration_seconds: float | int | None,
    distance_meters: float | int | None,
) -> float | None:
    if duration_seconds is None or distance_meters is None:
        return None

    distance_km = float(distance_meters) / 1000
    if distance_km <= 0:
        return None

    return float(duration_seconds) / 60 / distance_km

