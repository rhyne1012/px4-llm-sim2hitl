#!/usr/bin/env python3
"""Linearization in trim.py: the transfer-function arithmetic on known systems, then the active model release if there
is one (no PX4, no FC). Run: "$PY" -B sitl/test_trim_linear.py"""
import unittest

import numpy as np

import trim


class TransferFunction(unittest.TestCase):
    def test_second_order_with_a_zero(self):
        # x1' = x2, x2' = -4 x1 - 2 x2 + u, y = x1 + 0.5 x2  ->  (0.5 s + 1) / (s^2 + 2 s + 4)
        a = np.array([[0.0, 1.0], [-4.0, -2.0]])
        num, den = trim.transfer_function(a, np.array([0.0, 1.0]), np.array([1.0, 0.5]))
        np.testing.assert_allclose(num, [0.5, 1.0], atol=1e-12)
        np.testing.assert_allclose(den, [1.0, 2.0, 4.0], atol=1e-12)

    def test_leading_zero_coefficients_are_dropped(self):
        a = np.array([[0.0, 1.0], [-4.0, -2.0]])
        num, _ = trim.transfer_function(a, np.array([0.0, 1.0]), np.array([1.0, 0.0]))
        np.testing.assert_allclose(num, [1.0], atol=1e-12)

    def test_servo_keeps_the_dc_gain(self):
        num, den = trim.with_servo(np.array([3.0]), np.array([1.0, 2.0]), 20.0)
        self.assertAlmostEqual(np.polyval(num, 0.0) / np.polyval(den, 0.0), 1.5)
        np.testing.assert_allclose(den, [1.0, 22.0, 40.0])


class ActiveModel(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        try:
            cls.core = trim.Core(trim.default_plant_lib())
        except Exception as error:  # a machine without a model release
            raise unittest.SkipTest(f'no active model release: {error}')
        cls.result = trim.trim(cls.core, 16.0, 100.0)
        cls.linear = trim.linearize(cls.core, cls.result)

    def test_matches_the_full_model(self):
        check = self.linear['check_against_full_model']
        self.assertTrue(check['passed'], check)

    def test_airframe_modes_are_modes_of_the_full_model(self):
        full = np.linalg.eigvals(np.array(self.linear['A_full']))
        for mode in self.linear['modes']:
            s = complex(mode['real'], mode['imag'])
            self.assertLess(np.min(np.abs(full - s)), 1e-2 * max(1.0, abs(s)), mode['name'])

    def test_the_standard_modes_are_found(self):
        names = {m['name'] for m in self.linear['modes']}
        self.assertEqual(names, {'phugoid', 'short_period', 'dutch_roll', 'spiral', 'roll'})

    def test_servos_are_taken_out_of_the_matrices_not_the_model(self):
        # Each command drives one servo; the airframe inputs act directly, the full ones only through the servo
        b_full = np.array(self.linear['B_full'])
        self.assertTrue(np.all(np.abs(b_full[:trim.X_SERVO]) < 1e-6))
        self.assertEqual(len(self.linear['A_airframe']), 8)
        self.assertEqual(len(self.linear['A_full']), trim.NX)
        q = trim.AIRFRAME_STATES.index('q')
        elevator = trim.INPUTS.index('elevator')
        self.assertGreater(self.linear['B_airframe'][q][elevator], 0.0)  # + elevator noses up

    def test_signs_follow_the_command_convention(self):
        functions = self.linear['transfer_functions']
        self.assertGreater(functions['q/elevator']['airframe']['gain'], 0.0)
        self.assertLess(functions['p/aileron']['airframe']['gain'], 0.0)  # + aileron rolls left
        self.assertGreater(functions['r/rudder']['airframe']['gain'], 0.0)

    def test_a_turn_is_refused(self):
        with self.assertRaises(ValueError):
            trim.linearize(self.core, dict(self.result, bank_deg=20.0))


if __name__ == '__main__':
    unittest.main()
