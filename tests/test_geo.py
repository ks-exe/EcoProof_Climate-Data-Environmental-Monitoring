"""Analytical spherical geometry and synthetic wind cases; no project data."""

import math

import pytest

from ecoproof.graph.geo import (
    EARTH_RADIUS_KM,
    adjacency_matrix,
    haversine_km,
    wind_vector,
    wind_weights,
)


@pytest.mark.parametrize(
    ("start", "end", "expected_km"),
    [
        ((28.6139, 77.2090), (28.6139, 77.2090), 0.0),
        ((0.0, 0.0), (0.0, 1.0), 111.1950802335),
        ((0.0, 0.0), (1.0, 0.0), 111.1950802335),
        ((0.0, 0.0), (0.0, 90.0), 10007.557221018),
        ((0.0, 0.0), (0.0, 180.0), 20015.114442036),
        ((90.0, 0.0), (-90.0, 0.0), 20015.114442036),
        ((0.0, 179.95), (0.0, -179.95), 11.11950802335),
        ((90.0, -20.0), (90.0, 150.0), 0.0),
    ],
)
def test_known_spherical_distances(start, end, expected_km):
    # Rounded analytical arc lengths for radius 6371.0088 km, not road distances.
    assert haversine_km(start, end) == pytest.approx(expected_km, abs=1e-7)
    assert haversine_km(end, start) == pytest.approx(expected_km, abs=1e-7)


def test_near_antipodes_are_finite():
    distance = haversine_km((36.1, -86.7), (-36.10000001, 93.29999999))
    assert math.isfinite(distance)
    assert distance == pytest.approx(math.pi * EARTH_RADIUS_KM, abs=0.001)


def test_adjacency_uses_gaussian_and_default_20_km_cutoff():
    coordinates = [(0.0, 0.0), (0.0, 0.1), (0.0, 0.2)]
    weights = adjacency_matrix(coordinates, sigma_km=10.0)

    # 0.1 degrees at the equator is 11.119508... km, with Gaussian weight ~0.539.
    expected = math.exp(-(11.11950802335 ** 2) / 200.0)
    assert weights[0] == pytest.approx([0.0, expected, 0.0])
    assert weights[1] == pytest.approx([expected, 0.0, expected])
    assert weights[2] == pytest.approx([0.0, expected, 0.0])


def test_cutoff_is_inclusive_and_sigma_controls_decay():
    coordinates = [(0.0, 0.0), (0.0, 0.1)]
    distance = haversine_km(*coordinates)
    narrow = adjacency_matrix(coordinates, sigma_km=distance, tau_km=distance)
    wide = adjacency_matrix(coordinates, sigma_km=2 * distance, tau_km=distance)
    excluded = adjacency_matrix(
        coordinates, sigma_km=distance, tau_km=math.nextafter(distance, 0.0)
    )
    assert narrow[0][1] == pytest.approx(math.exp(-0.5))
    assert wide[0][1] == pytest.approx(math.exp(-0.125))
    assert excluded == [[0.0, 0.0], [0.0, 0.0]]


@pytest.mark.parametrize("coordinates, expected", [([], []), ([(0.0, 0.0)], [[0.0]])])
def test_empty_and_single_node_graphs(coordinates, expected):
    assert adjacency_matrix(coordinates, sigma_km=10.0) == expected
    assert wind_weights(
        coordinates, sigma_km=10.0, speed_m_s=5.0, direction_from_deg=0.0, alpha=1.0
    ) == expected


def test_colocated_nodes_have_no_self_loops_or_directional_boost():
    coordinates = [(28.6, 77.2), (28.6, 77.2)]
    expected = [[0.0, 1.0], [1.0, 0.0]]
    assert adjacency_matrix(coordinates, sigma_km=10.0, tau_km=0.0) == expected
    assert wind_weights(
        coordinates, sigma_km=10.0, speed_m_s=5.0, direction_from_deg=45.0, alpha=2.0
    ) == expected


@pytest.mark.parametrize(
    "direction, expected",
    [(0.0, (0.0, -5.0)), (90.0, (-5.0, 0.0)), (180.0, (0.0, 5.0)),
     (270.0, (5.0, 0.0)), (360.0, (0.0, -5.0))],
)
def test_meteorological_from_direction_becomes_travel_vector(direction, expected):
    assert wind_vector(5.0, direction) == pytest.approx(expected, abs=1e-14)


def test_oblique_and_calm_wind_vectors():
    assert wind_vector(5.0, 45.0) == pytest.approx((-5 / math.sqrt(2),) * 2)
    assert wind_vector(0.0, 123.0) == (0.0, 0.0)


@pytest.mark.parametrize(
    "direction, downwind",
    [(0.0, (-0.05, 0.0)), (90.0, (0.0, -0.05)),
     (180.0, (0.05, 0.0)), (270.0, (0.0, 0.05)), (360.0, (-0.05, 0.0))],
)
def test_only_downwind_edge_is_boosted(direction, downwind):
    coordinates = [(0.0, 0.0), downwind]
    base = adjacency_matrix(coordinates, sigma_km=10.0)
    weighted = wind_weights(
        coordinates, sigma_km=10.0, speed_m_s=5.0,
        direction_from_deg=direction, alpha=0.5,
    )
    assert weighted[0][1] == pytest.approx(1.5 * base[0][1])
    assert weighted[1][0] == pytest.approx(base[1][0])
    assert weighted[0][0] == weighted[1][1] == 0.0


@pytest.mark.parametrize(
    "speed, factor", [(0.0, 1.0), (2.5, 1.5), (5.0, 2.0), (10.0, 3.0), (100.0, 3.0)]
)
def test_speed_scaling_saturates_at_10_metres_per_second(speed, factor):
    coordinates = [(0.0, 0.0), (0.0, 0.05)]
    base = adjacency_matrix(coordinates, sigma_km=10.0)
    weighted = wind_weights(
        coordinates, sigma_km=10.0, speed_m_s=speed, direction_from_deg=270.0, alpha=1.0
    )
    assert weighted[0][1] == pytest.approx(factor * base[0][1])
    assert weighted[1][0] == pytest.approx(base[1][0])


def test_oblique_wind_uses_cosine_and_crosswind_keeps_base_weight():
    coordinates = [(0.0, 0.0), (0.0, 0.05)]
    base = adjacency_matrix(coordinates, sigma_km=10.0)
    oblique = wind_weights(
        coordinates, sigma_km=10.0, speed_m_s=5.0, direction_from_deg=225.0, alpha=1.0
    )
    crosswind = wind_weights(
        coordinates, sigma_km=10.0, speed_m_s=5.0, direction_from_deg=0.0, alpha=1.0
    )
    assert oblique[0][1] == pytest.approx((1 + 1 / math.sqrt(2)) * base[0][1])
    assert crosswind == base


def test_station_bearing_uses_local_east_north_at_high_latitude():
    # Generate a destination using the independent spherical direct equations:
    # 0.1 degrees of arc along bearing 45 degrees from (60, 10).
    lat, arc, bearing = map(math.radians, (60.0, 0.1, 45.0))
    end_lat = math.asin(
        math.sin(lat) * math.cos(arc) + math.cos(lat) * math.sin(arc) * math.cos(bearing)
    )
    delta_lon = math.atan2(
        math.sin(bearing) * math.sin(arc) * math.cos(lat),
        math.cos(arc) - math.sin(lat) * math.sin(end_lat),
    )
    coordinates = [(60.0, 10.0), (math.degrees(end_lat), 10.0 + math.degrees(delta_lon))]
    base = adjacency_matrix(coordinates, sigma_km=10.0)
    weighted = wind_weights(
        coordinates, sigma_km=10.0, speed_m_s=5.0, direction_from_deg=225.0, alpha=1.0
    )
    assert haversine_km(*coordinates) == pytest.approx(11.11950802335, abs=1e-7)
    assert weighted[0][1] == pytest.approx(2 * base[0][1], abs=1e-10)


def test_direction_crosses_antimeridian_on_the_short_path():
    coordinates = [(0.0, 179.95), (0.0, -179.95)]
    base = adjacency_matrix(coordinates, sigma_km=10.0)
    weighted = wind_weights(
        coordinates, sigma_km=10.0, speed_m_s=5.0, direction_from_deg=270.0, alpha=1.0
    )
    assert weighted[0][1] == pytest.approx(2 * base[0][1])
    assert weighted[1][0] == pytest.approx(base[1][0])


def test_wind_does_not_create_edges_beyond_cutoff():
    coordinates = [(0.0, 0.0), (0.0, 1.0)]
    assert wind_weights(
        coordinates, sigma_km=10.0, speed_m_s=100.0, direction_from_deg=270.0, alpha=10.0
    ) == [[0.0, 0.0], [0.0, 0.0]]


def test_zero_alpha_disables_wind_and_preserves_coordinate_order():
    coordinates = [(0.0, 0.1), (0.0, 0.0), (0.0, -0.1)]
    original = coordinates.copy()
    base = adjacency_matrix(coordinates, sigma_km=10.0)
    assert wind_weights(
        coordinates, sigma_km=10.0, speed_m_s=5.0, direction_from_deg=270.0, alpha=0.0
    ) == base
    assert coordinates == original
    assert base[0][2] == 0.0
    assert base[0][1] > 0.0


@pytest.mark.parametrize(
    "point", [(91.0, 0.0), (-91.0, 0.0), (0.0, 181.0), (0.0, -181.0),
              (float('nan'), 0.0), (0.0, float('inf')), (True, 0.0), ('0', 0.0)]
)
def test_invalid_coordinates_are_rejected(point):
    with pytest.raises(ValueError):
        haversine_km(point, (0.0, 0.0))
    with pytest.raises(ValueError):
        adjacency_matrix([point], sigma_km=10.0)


@pytest.mark.parametrize(
    "parameter, value",
    [("sigma_km", 0.0), ("sigma_km", -1.0), ("sigma_km", float('nan')),
     ("sigma_km", float('inf')), ("tau_km", -1.0), ("tau_km", float('nan'))],
)
def test_invalid_graph_parameters_are_rejected_even_for_empty_graph(parameter, value):
    arguments = {"sigma_km": 10.0, "tau_km": 20.0, parameter: value}
    with pytest.raises(ValueError, match=parameter):
        adjacency_matrix([], **arguments)


@pytest.mark.parametrize(
    "parameter, value",
    [("speed_m_s", -1.0), ("speed_m_s", float('nan')), ("speed_m_s", float('inf')),
     ("direction_from_deg", -1.0), ("direction_from_deg", 361.0),
     ("direction_from_deg", float('nan')), ("direction_from_deg", None),
     ("alpha", -1.0), ("alpha", float('inf')), ("alpha", True)],
)
def test_invalid_or_missing_wind_is_rejected(parameter, value):
    arguments = {"sigma_km": 10.0, "speed_m_s": 0.0,
                 "direction_from_deg": 0.0, "alpha": 0.0, parameter: value}
    with pytest.raises(ValueError, match=parameter):
        wind_weights([], **arguments)
