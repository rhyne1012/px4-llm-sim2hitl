#!/usr/bin/env python3
"""loop_tracking.py's geometry and windows without a ULog: track error sign, Mission stretches, legs and turn ends
taken from the waypoints (also after moving or turning the loop)."""
import json
from pathlib import Path
import unittest

import numpy as np

try:
    from . import loop_tracking as tracking
except ImportError:
    import loop_tracking as tracking

EXAMPLE = Path(__file__).resolve().parents[1] / 'hitl' / 'missions' / 'example_loop.json'


class LoopTrackingTests(unittest.TestCase):
    def test_sign_outside_positive(self):
        square = np.array([[0, 0], [10, 0], [10, 10], [0, 10], [0, 0]], dtype=float)
        d = tracking.path_distance(np.array([5.0, 5.0, -2.0]), np.array([5.0, 1.0, 5.0]), square)
        np.testing.assert_allclose(d, [-5.0, -1.0, 2.0])

    def test_mission_intervals_skip_settling(self):
        t = np.arange(0, 100, 1.0)
        nav = np.where((t >= 10) & (t < 40) | (t >= 50), 3, 14)
        self.assertEqual(tracking.mission_intervals(t, nav), [(20.0, 40.0), (60.0, 99.0)])

    def test_legs_follow_the_waypoints(self):
        points = json.loads(EXAMPLE.read_text())['waypoints_east_north_m']
        legs, shape = tracking.legs(points)
        self.assertEqual([(leg['name'], round(leg['length']), round(leg['bearing'])) for leg in legs],
                         [('south_westbound', 300, 270), ('north_eastbound', 300, 90)])
        self.assertEqual(shape['ends'], (('west', -150.0), ('east', 150.0)))
        on = tracking.on_leg(np.array([-140.0, -95.0, 125.0, 130.0, 0.0]),
                             np.array([70.0, 72.0, 68.0, 70.0, 140.0]), legs[0])
        self.assertEqual(on.tolist(), [False, True, True, False, False])
        moved = [[e + 50 if e < 0 else e, n] for e, n in points]  # one end 50 m in: no longer symmetric about home
        _, shape = tracking.legs(moved)
        self.assertEqual(shape['ends'], (('west', -100.0), ('east', 150.0)))
        turned = [[-n, e] for e, n in points]  # the same loop turned 90 deg left
        legs, shape = tracking.legs(turned)
        self.assertEqual([leg['name'] for leg in legs], ['east_southbound', 'west_northbound'])
        self.assertEqual([name for name, _ in shape['ends']], ['south', 'north'])
        with self.assertRaises(ValueError):
            tracking.legs([[0, 0], [100, 0], [100, 100], [0, 100]])  # a square: no legs stand out

    def test_euler(self):
        half = np.radians(30) / 2
        roll30 = [np.cos(half), np.sin(half), 0, 0]
        np.testing.assert_allclose(tracking.euler_deg([roll30])[0], [30, 0, 0], atol=1e-9)


if __name__ == '__main__':
    unittest.main()
