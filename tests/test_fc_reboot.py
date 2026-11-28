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


class Msg:
    def __init__(self, kind, **fields):
        self.kind = kind
        self.__dict__.update(fields)

    def get_type(self):
        return self.kind


class BootTime(unittest.TestCase):
    def fc(self, messages):
        fc = F.FC('/dev/null')
        fc.target = (1, 1)
        asked = []

        class Mav:
            def command_long_send(self, *args):
                asked.append(args)
        fc.m = type('M', (), {'mav': Mav()})()
        fc.wait = lambda match, timeout, any_source=False: next((m for m in messages if match(m)), None)
        return fc, asked

    def test_from_px4_timesync(self):   # PX4's own request (tc1 0): ts1 is its time since boot in ns
        fc, asked = self.fc([Msg('TIMESYNC', tc1=5, ts1=9), Msg('TIMESYNC', tc1=0, ts1=125_908_146_000)])
        self.assertEqual(fc.boot_ms(), 125_908)
        self.assertEqual(asked, [])

    def test_system_time_when_no_timesync(self):
        fc, asked = self.fc([Msg('SYSTEM_TIME', time_boot_ms=4200)])
        self.assertEqual(fc.boot_ms(), 4200)
        self.assertEqual(len(asked), 1)

    def test_none(self):
        fc, _ = self.fc([])
        self.assertIsNone(fc.boot_ms())


if __name__ == '__main__':
    unittest.main(verbosity=2)
