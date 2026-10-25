"""Station distances and directed wind weights from SPEC section 5, steps 1–2.

Coordinates are (latitude, longitude) degrees. Matrices preserve input order:
entry [i][j] describes the edge from i to j. No database or network access.
"""

from collections.abc import Sequence
import math


EARTH_RADIUS_KM = 6371.0088  # Mean spherical radius, not an ellipsoidal geodesic.
Coordinate = tuple[float, float]
WeightMatrix = list[list[float]]


def haversine_km(start: Coordinate, end: Coordinate) -> float:
    """Great-circle distance in km, using a spherical Earth."""
    return _distance_km(_coordinate(start), _coordinate(end))


def adjacency_matrix(
    coordinates: Sequence[Coordinate], *, sigma_km: float, tau_km: float = 20.0
) -> WeightMatrix:
    """Return symmetric Gaussian weights with zero diagonal and inclusive cutoff.

    sigma_km must be positive; tau_km must be nonnegative. Sigma has no tuned
    default in the spec, so callers must supply it. Distinct colocated nodes
    receive weight 1. Matrix indices, rather than coordinates, identify nodes.
    """
    points = [_coordinate(point) for point in coordinates]
    sigma = _nonnegative(sigma_km, "sigma_km")
    if sigma == 0:
        raise ValueError("sigma_km must be positive")
    cutoff = _nonnegative(tau_km, "tau_km")
    weights = [[0.0] * len(points) for _ in points]
    for i, start in enumerate(points):
        for j in range(i + 1, len(points)):
            distance = _distance_km(start, points[j])
            if distance <= cutoff:
                scaled = distance / sigma
                weight = math.exp(-0.5 * scaled * scaled)
                weights[i][j] = weights[j][i] = weight
    return weights


def wind_vector(speed_m_s: float, direction_from_deg: float) -> tuple[float, float]:
    """Return (east, north) travel components in m/s from meteorological wind.

    Direction is clockwise from north and tells where wind COMES FROM:
    0/360 -> south, 90 -> west, 180 -> north, 270 -> east.
    """
    speed = _nonnegative(speed_m_s, "speed_m_s")
    direction = _finite(direction_from_deg, "direction_from_deg")
    if not 0 <= direction <= 360:
        raise ValueError("direction_from_deg must be between 0 and 360")
    angle = math.radians(direction % 360)
    return -speed * math.sin(angle), -speed * math.cos(angle)


def wind_alignment(
    start: Coordinate, end: Coordinate, *, direction_from_deg: float
) -> float:
    """Signed cosine of i -> j with wind travel; positive means downwind.

    Direction alone cannot establish transport during calm weather; callers
    testing plume propagation must also require a positive wind speed.
    """
    east, north = wind_vector(1.0, direction_from_deg)
    return _alignment(_coordinate(start), _coordinate(end), east, north)


def wind_weights(
    coordinates: Sequence[Coordinate],
    *,
    speed_m_s: float,
    direction_from_deg: float,
    alpha: float,
    sigma_km: float,
    tau_km: float = 20.0,
) -> WeightMatrix:
    """Return wind-weighted adjacency for one regional weather observation.

    A[i][j] = W[i][j] * (1 + alpha * max(0, cosine) * min(speed_m_s / 5, 2)).
    Cosine compares the initial great-circle direction i -> j with wind travel.
    Alpha must be nonnegative and is explicitly supplied for later tuning.
    Calm wind and alpha=0 return the base weights. Missing/invalid weather is
    rejected, not treated as calm. No direction boost applies to coincident or
    antipodal coordinates, whose initial bearing is undefined.
    """
    weights = adjacency_matrix(coordinates, sigma_km=sigma_km, tau_km=tau_km)
    speed = _nonnegative(speed_m_s, "speed_m_s")
    strength = _nonnegative(alpha, "alpha")
    # Use a unit travel vector to keep the cosine stable even at tiny speeds.
    east, north = wind_vector(1.0, direction_from_deg)
    if speed == 0 or strength == 0:
        return weights
    speed_factor = min(speed / 5.0, 2.0)
    for i, start in enumerate(coordinates):
        for j, end in enumerate(coordinates):
            if weights[i][j] == 0:
                continue
            alignment = max(0.0, _alignment(start, end, east, north))
            weight = weights[i][j] * (1.0 + strength * alignment * speed_factor)
            if not math.isfinite(weight):
                raise ValueError("alpha is too large for finite wind weights")
            weights[i][j] = weight
    return weights


def _distance_km(start: Coordinate, end: Coordinate) -> float:
    lat1, lon1 = map(math.radians, start)
    lat2, lon2 = map(math.radians, end)
    delta_lon = math.remainder(lon2 - lon1, math.tau)
    hav = (
        math.sin((lat2 - lat1) / 2.0) ** 2
        + math.cos(lat1) * math.cos(lat2) * math.sin(delta_lon / 2.0) ** 2
    )
    # Floating-point roundoff near antipodes must not escape the asin domain.
    return 2.0 * EARTH_RADIUS_KM * math.asin(math.sqrt(min(1.0, max(0.0, hav))))


def _alignment(start: Coordinate, end: Coordinate, east: float, north: float) -> float:
    """Signed cosine in the local east/north tangent plane at the source node."""
    lat1, lon1 = map(math.radians, start)
    lat2, lon2 = map(math.radians, end)
    delta_lon = math.remainder(lon2 - lon1, math.tau)
    toward_east = math.cos(lat2) * math.sin(delta_lon)
    toward_north = (
        math.cos(lat1) * math.sin(lat2)
        - math.sin(lat1) * math.cos(lat2) * math.cos(delta_lon)
    )
    length = math.hypot(toward_east, toward_north)
    if length < 1e-15:
        return 0.0
    cosine = (toward_east * east + toward_north * north) / length
    return min(1.0, max(-1.0, cosine))


def _coordinate(point: Coordinate) -> Coordinate:
    if len(point) != 2:
        raise ValueError("coordinates must contain latitude and longitude")
    lat = _finite(point[0], "latitude")
    lon = _finite(point[1], "longitude")
    if not -90 <= lat <= 90 or not -180 <= lon <= 180:
        raise ValueError("latitude/longitude outside valid coordinate range")
    return lat, lon


def _finite(value: float, name: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{name} must be a finite number")
    try:
        result = float(value)
    except OverflowError:
        raise ValueError(f"{name} must be a finite number") from None
    if not math.isfinite(result):
        raise ValueError(f"{name} must be a finite number")
    return result


def _nonnegative(value: float, name: str) -> float:
    result = _finite(value, name)
    if result < 0:
        raise ValueError(f"{name} must be nonnegative")
    return result
