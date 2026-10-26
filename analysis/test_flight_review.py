#!/usr/bin/env python3
"""flight_review.py's numbers on a synthetic log (numpy only, no ULog file, no imagery, no matplotlib)."""
from types import SimpleNamespace
import math
import unittest

import numpy as np

try:
    from . import flight_review as review
except ImportError:
    import flight_review as review

ORIGIN = (22.9, 120.3)


def rows(dtype, values):
    return np.array([tuple(v) for v in values], dtype=dtype)


def latlon(east, north):
    m_lat, m_lon = review.metres_per_degree(ORIGIN[0])
    return ORIGIN[0] + north / m_lat, ORIGIN[1] + east / m_lon


def synthetic_log():
    """100 s: Stabilized, Mission from 10 s, Offboard 60-65 s, Mission, Loiter from 90 s; armed 1-95 s; a 100 m
    circle about the origin; the FC flies to A (100, 0), then B (0, 100), then A again; home moves twice in the air."""
    us = 1_000_000
    t = np.arange(0, 101)
    nav = np.select([t < 10, t < 60, t < 65, t < 90], [15, 3, 14, 3], 4)
    status = rows([('timestamp', '<u8'), ('nav_state', 'u1'), ('arming_state', 'u1')],
                  [(s * us, m, 2 if 1 <= s <= 95 else 1) for s, m in zip(t, nav)])
    home = rows([('timestamp', '<u8'), ('lat', '<f8'), ('lon', '<f8'), ('alt', '<f4')],
                [(1 * us, *ORIGIN, 0.0), (20 * us, *ORIGIN, 1.0), (30 * us, *ORIGIN, -1.0)])
    tg = np.arange(0, 100, .1)
    lat, lon = latlon(100 * np.cos(tg / 10), 100 * np.sin(tg / 10))
    position = rows([('timestamp', '<u8'), ('lat', '<f8'), ('lon', '<f8'), ('alt', '<f4')],
                    [(int(s * us), a, b, 85.0) for s, a, b in zip(tg, lat, lon)])
    point = np.dtype([('lat', '<f8'), ('lon', '<f8'), ('valid', 'u1'), ('type', 'u1'), ('acceptance_radius', '<f4')])
    triplet = np.zeros(4, dtype=[('timestamp', '<u8'), ('current', point)])
    for i, (s, east, north, kind) in enumerate([(10, 100, 0, 0), (30, 0, 100, 0), (50, 100.5, 0, 0), (90, 0, 0, 2)]):
        triplet[i]['timestamp'] = s * us
        triplet[i]['current'] = (*latlon(east, north), 1, kind, 25.0)
    return SimpleNamespace(topics={('vehicle_status', 0): status, ('home_position', 0): home,
                                   ('vehicle_global_position', 0): position, ('position_setpoint_triplet', 0): triplet})


class FlightReviewTests(unittest.TestCase):
    def setUp(self):
        self.flight = review.Flight(synthetic_log(), ORIGIN, 'synthetic')

    def test_modes_extent_and_home(self):
        f = self.flight
        self.assertEqual(f.offboard(), [(60.0, 65.0)])
        self.assertEqual([m for _, _, m in f.runs], [15, 3, 14, 3, 4])
        self.assertEqual(f.t_end, 97.0)  # last armed sample + 2 s
        whole = f.extent()
        self.assertAlmostEqual(whole['west_m'], -100.0, delta=0.1)
        self.assertAlmostEqual(whole['north_m'], 100.0, delta=0.1)
        self.assertEqual(f.home_updates_in_air(), {'count': 2, 'alt_m': [-1.0, 1.0], 'last_s': 30.0, 'armed_s': 1.0})

    def test_fc_waypoints_are_the_distinct_mission_targets(self):
        f = self.flight
        self.assertEqual(len(f.fc_points), 2)  # A, B; A again within 2 m is the same point; the loiter is not one
        self.assertEqual(f.trip_index.tolist(), [0, 1, 0, -1])
        self.assertEqual(f.acceptance_m, 25.0)
        np.testing.assert_allclose(f.fc_points, [(100, 0), (0, 100)], atol=1e-6)

    def test_numbers_against_a_mission(self):
        report = review.numbers(self.flight, [], [(100, 0), (0, 100)])
        self.assertEqual(report['fc_waypoints'], {'count': 2, 'not_in_mission': 0, 'max_offset_m': 0.0})
        moved = review.numbers(self.flight, [], [(100, 0), (0, 110)])
        self.assertEqual(moved['fc_waypoints']['not_in_mission'], 1)
        self.assertEqual(review.match([(3.0, 4.0)], [(0, 0), (30, 40)]), [(0, 5.0)])
        self.assertEqual(review.numbers(self.flight, [], None)['fc_waypoints'], {'count': 2})

    def test_origin_from_home_without_a_mission(self):
        f = review.Flight(synthetic_log(), None, 'no mission')
        self.assertEqual(f.origin, ORIGIN)
        self.assertTrue(math.isclose(f.extent()['east_m'], 100.0, abs_tol=0.1))


if __name__ == '__main__':
    unittest.main()
