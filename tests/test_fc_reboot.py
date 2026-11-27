#!/usr/bin/env python3
"""Offline checks of tools/fc.py FC.reboot: a refused reboot fails, and a reboot counts only with evidence (the FC's time
since boot started again, or an accepted command when the FC gives no boot time). No flight controller is used.

    <python with pymavlink> -B tests/test_fc_reboot.py
"""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'tools'))
import fc as F  # noqa: E402

mav = F.mav


class Stub(F.FC):
    """An FC whose link is replaced: the reboot command answers `result`, the boot times are given in order."""

    def __init__(self, result, boot_times):
        super().__init__('/dev/null')
        self.serial, self.armed, self.version = True, False, {'uid': 7}
        self._result, self._boot = result, list(boot_times)

    def command(self, cmd, *params, **_):
        return self._result

    def boot_ms(self):
        return self._boot.pop(0)

    def drain(self, seconds):
        pass

    def close(self):
        pass

    def connect(self, timeout=30.0):
        return self

    def identity(self, tries=3):
        return {'uid': 7, 'armed': False}


class Reboot(unittest.TestCase):
    def setUp(self):
        self._sleep, F.time.sleep = F.time.sleep, lambda s: None

    def tearDown(self):
        F.time.sleep = self._sleep

    def test_refused_reboot_fails(self):
        with self.assertRaises(F.FCError):
            Stub(mav.MAV_RESULT_DENIED, [5000, 6000]).reboot(wait_save=False)

    def test_no_reboot_happened(self):
        with self.assertRaises(F.FCError):   # accepted, but the time since boot went on
            Stub(mav.MAV_RESULT_ACCEPTED, [5000, 6000]).reboot(wait_save=False)

    def test_rebooted(self):
        out = Stub(None, [50000, 1200]).reboot(wait_save=False)   # no ack (the port went away), boot time restarted
        self.assertEqual(out['boot_ms_after'], 1200)

    def test_no_evidence_fails(self):
        with self.assertRaises(F.FCError):   # no ack and no boot time: nothing shows a reboot
            Stub(None, [None, None]).reboot(wait_save=False)


if __name__ == '__main__':
    unittest.main(verbosity=2)
