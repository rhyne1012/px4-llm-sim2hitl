#!/usr/bin/env python3
"""Checks of tools/linear.py on Testbird: the trims converge, the actuator and engine poles are where Testbird's
definition puts them, the linear model agrees with the nonlinear model, and --compare tells a changed vehicle apart.
JSBSim's FGTrim is expected to fail on Testbird (docs/architecture.md, known limits).

    JSBSIM_PYTHON=<unpacked jsbsim 1.3.3 wheel> <python with numpy> -B tests/test_linear.py
"""
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

TOOLKIT = Path(__file__).resolve().parents[1]
TESTBIRD = TOOLKIT / 'vehicles' / 'testbird'
SERVO_LAG = 25.0  # rad/s, Systems/controls.xml


def run(*args):
    return subprocess.run([sys.executable, '-B', str(TOOLKIT / 'tools' / 'linear.py'), *map(str, args)],
                          capture_output=True, text=True)


class TestLinear(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix='test_linear_'))
        cls.base = cls.tmp / 'base.json'
        cls.aft = cls.tmp / 'aft.json'
        for out, extra in ((cls.base, []), (cls.aft, ['--config', TESTBIRD / 'configs' / 'aft_cg.toml'])):
            r = run(TESTBIRD, *extra, '--level', 17, '--linear', 17, '--turn', '17:30', '--out', out)
            if r.returncode:
                raise RuntimeError(r.stderr[-2000:])
        cls.a = json.loads(cls.base.read_text())

    def test_trims_converge(self):
        for t in self.a['trims']:
            self.assertTrue(t['converged'], t)
            self.assertLess(t['residual_max'], 1e-6)
        level = self.a['trims'][0]
        self.assertFalse(level['fgtrim_check']['converged'])  # the known FGTrim limit with Testbird's motor
        turn = self.a['trims'][1]
        self.assertAlmostEqual(turn['bank_deg'], 30.0, places=6)

    def test_servo_poles(self):
        servo = self.a['linear'][0]['servo']
        for name in ('aileron', 'elevator', 'rudder'):
            self.assertLess(abs(servo[name]['pole_rad_s'] / SERVO_LAG - 1.0), 0.05, servo[name])
            self.assertLess(abs(servo[name]['gain'] - 1.0), 0.02, servo[name])
            self.assertEqual(servo[name]['delay_s'], 0.0)
        self.assertGreater(servo['throttle']['pole_rad_s'], 1.0)  # the motor and propeller lag

    def test_linear_matches_nonlinear(self):
        check = self.a['linear'][0]['check']
        self.assertTrue(check['passed'], (check['worst_db'], check['worst_deg']))
        modes = {m['name'] for m in self.a['linear'][0]['modes']}
        self.assertTrue({'phugoid', 'short_period', 'dutch_roll', 'roll'} <= modes, modes)

    def test_compare(self):
        same = run('--compare', self.base, self.base)
        self.assertEqual(same.returncode, 0, same.stdout)
        moved = run('--compare', self.base, self.aft)
        self.assertEqual(moved.returncode, 1, moved.stdout)
        failed = {f['item'] for f in json.loads(moved.stdout)['failed']}
        self.assertTrue(any('short_period' in f for f in failed), failed)

    def test_no_check(self):
        out = self.tmp / 'nocheck.json'
        r = run(TESTBIRD, '--level', 17, '--linear', 17, '--no-check', '--out', out)
        self.assertEqual(r.returncode, 0, r.stderr[-800:])
        self.assertIn('skipped', json.loads(out.read_text())['linear'][0]['check'])

    def test_compare_catches_failed_or_missing_evidence(self):
        def changed(edit):
            d = json.loads(self.base.read_text())
            edit(d)
            f = self.tmp / 'changed.json'
            f.write_text(json.dumps(d))
            return run('--compare', self.base, f).returncode
        self.assertEqual(changed(lambda d: d['trims'][0].update(converged=False)), 1)
        self.assertEqual(changed(lambda d: d['linear'][0]['check'].pop('rows')), 1)
        self.assertEqual(changed(lambda d: d['outputs']['elevator'][0].update(gain=1.0)), 1)
        self.assertEqual(changed(lambda d: d['trims'].pop()), 1)


if __name__ == '__main__':
    unittest.main()
