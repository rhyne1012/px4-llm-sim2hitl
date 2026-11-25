"""deploy/flight_switch.py on synthetic recipes and a simulated FC (no FC, no PX4 tree): the recipe pair check, the
plan's order and PX4's own output values, and the writes against PX4's timing (host/pwm_defaults.py)."""

import hashlib
import json
import lzma
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import flight_switch as fs  # noqa: E402
from host import pwm_defaults  # noqa: E402 - on the path through flight_switch

FIRMWARE = [
    {'name': 'SYS_HITL', 'type': 'Int32', 'default': 0, 'rebootRequired': True},
    {'name': 'GPS_1_CONFIG', 'type': 'Int32', 'default': 201},
    {'name': 'FW_R_TC', 'type': 'Float', 'default': 0.4},
    {'name': 'CAL_ACC0_XOFF', 'type': 'Float', 'default': 0.0},
] + [{'name': f'PWM_MAIN_{what}{ch}', 'type': 'Int32', 'default': default}
     for ch in (1, 2, 3) for what, default in (('FUNC', 0), ('DIS', 1000), ('MIN', 1000), ('MAX', 2000))]
KIND = {'Int32': 6, 'Float': 9}


class FakeFC:
    """PX4's output driver as px4io / pwm_out behave (PX4 v1.17 update_params): it looks at parameter changes at
    most once a second; the first change after a quiet second is seen at once. A channel whose function went from 0
    to a servo gets DIS 1500, to a motor MIN 1100 / MAX 1900. Time is simulated (clock, sleep)."""

    def __init__(self, values):
        self.values = dict(values)
        self.t = 0.0
        self.next_look = 0.0
        self.dirty = False
        self.seen = {n for n, v in values.items() if n.startswith('PWM_MAIN_FUNC') and v}
        self.log = []

    def clock(self):
        return self.t

    def sleep(self, seconds):
        self.t += seconds
        self.look()

    def look(self):
        if not self.dirty or self.t < self.next_look:
            return
        self.dirty, self.next_look = False, self.t + 1.0
        for name, function in sorted(self.values.items()):
            if not name.startswith('PWM_MAIN_FUNC') or not function or name in self.seen:
                continue
            channel = name[len('PWM_MAIN_FUNC'):]
            own = ({'DIS': 1500} if 201 <= function <= 208 else {'MIN': 1100, 'MAX': 1900} if 101 <= function <= 112
                   else {})
            for what, value in own.items():
                self.values[f'PWM_MAIN_{what}{channel}'] = value
                self.log.append((round(self.t, 2), f'PWM_MAIN_{what}{channel}', value))
        self.seen = {n for n, v in self.values.items() if n.startswith('PWM_MAIN_FUNC') and v}

    def set(self, w):
        self.values[w['name']] = w['new']
        self.log.append((round(self.t, 2), w['name'], w['new']))
        self.dirty = True
        self.sleep(0.02)  # the echo's round trip
        return w['new']

    def get(self, w):
        self.sleep(0.02)
        return self.values[w['name']]


class FlightSwitchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.hitl = self.recipe('hitl', {'SYS_HITL': 1}, boot={'GPS_1_CONFIG': 0})
        self.flight = self.recipe('flight', {'PWM_MAIN_FUNC1': 201, 'PWM_MAIN_DIS1': 1425, 'PWM_MAIN_FUNC3': 101})

    def tearDown(self):
        self.temp.cleanup()

    def recipe(self, name, values, boot=None):
        folder = self.root / name
        (folder / 'firmware').mkdir(parents=True)
        raw = lzma.compress(json.dumps({'parameters': FIRMWARE}).encode())
        (folder / 'firmware/parameters.json.xz').write_bytes(raw)
        (folder / 'firmware/fw.px4').write_bytes(b'image')
        sha = lambda b: hashlib.sha256(b).hexdigest()
        (folder / 'firmware/firmware.json').write_text(json.dumps({
            'outputs': {'firmware': {'file': 'fw.px4', 'sha256': sha(b'image')}, 'parameters': {'sha256': sha(raw)}},
            'embedded': {'board_id': 1, 'git_hash': '0' * 40}}))
        (folder / 'sd/etc').mkdir(parents=True)
        (folder / 'sd/etc/extras.txt').write_text('my_module start\n')
        (folder / 'params.json').write_text(json.dumps({
            'schema_version': 1, 'firmware': 'firmware/firmware.json',
            'firmware_params': {'file': 'firmware/parameters.json.xz', 'sha256': sha(raw)},
            'fc_owned': {'patterns': ['^CAL_'], 'resolved_names': ['CAL_ACC0_XOFF']},
            'boot': {k: {'value': v} for k, v in (boot or {}).items()},
            'set': {k: {'value': v} for k, v in values.items()}}))
        return folder

    def readback(self, values):
        params = []
        for i, p in enumerate(FIRMWARE):
            kind, value = KIND[p['type']], values.get(p['name'], p['default'])
            bits = struct.pack('<i' if kind == 6 else '<f', value).hex()
            params.append({'name': p['name'], 'type': kind, 'value': value, 'bits': bits, 'index': i})
        path = self.root / 'readback.json'
        path.write_text(json.dumps({'parameters': params, 'autopilot_version': {'uid': 7}}))
        return path

    def test_a_pair_shares_firmware_and_sd_card(self):
        result = fs.pair(self.hitl, self.flight)
        self.assertEqual(result['problems'], [])
        self.assertEqual({d['name'] for d in result['differences']},
                         {'SYS_HITL', 'PWM_MAIN_FUNC1', 'PWM_MAIN_DIS1', 'PWM_MAIN_FUNC3'})
        (self.flight / 'sd/etc/extras.txt').write_text('other_module start\n')
        (self.flight / 'sd/etc/logging').mkdir()
        (self.flight / 'sd/etc/logging/logger_topics.txt').write_text('sensor_combined 0 0\n')
        problems = fs.pair(self.hitl, self.flight)['problems']
        self.assertEqual(len(problems), 2, problems)
        self.assertTrue(all('sd/etc/' in p for p in problems))
        info = json.loads((self.flight / 'firmware/firmware.json').read_text())
        info['outputs']['firmware']['sha256'] = 'f' * 64
        (self.flight / 'firmware/firmware.json').write_text(json.dumps(info))
        self.assertIn('firmware.json firmware', ' '.join(fs.pair(self.hitl, self.flight)['problems']))
        self.assertIn('SYS_HITL is not 1', ' '.join(fs.pair(self.flight, self.hitl)['problems']))

    def hitl_fc(self):
        return {'SYS_HITL': 1, 'GPS_1_CONFIG': 0, 'PWM_MAIN_DIS1': 1425, 'CAL_ACC0_XOFF': 0.12}

    def test_plan_to_flight_marks_what_px4_sets_itself(self):
        writes = fs.plan(self.flight, self.readback(self.hitl_fc()))
        self.assertEqual([w['name'] for w in writes],
                         ['PWM_MAIN_FUNC1', 'PWM_MAIN_FUNC3', 'PWM_MAIN_DIS1', 'PWM_MAIN_MIN3', 'PWM_MAIN_MAX3',
                          'GPS_1_CONFIG', 'SYS_HITL'])
        by = {w['name']: w for w in writes}
        self.assertEqual(by['PWM_MAIN_FUNC1']['px4io_trigger'], ['PWM_MAIN_DIS1'])
        self.assertEqual(by['PWM_MAIN_FUNC3']['px4io_trigger'], ['PWM_MAIN_MIN3', 'PWM_MAIN_MAX3'])
        # DIS1 already the recipe's, MIN3/MAX3 the firmware default (not in the recipe): PX4 would change them
        self.assertEqual([(by[n]['old'], by[n]['new'], by[n]['px4io']) for n in ('PWM_MAIN_DIS1', 'PWM_MAIN_MIN3', 'PWM_MAIN_MAX3')],
                         [(1425, 1425, 1500), (1000, 1000, 1100), (2000, 2000, 1900)])
        self.assertEqual(by['GPS_1_CONFIG']['new'], 201)  # back to the default (a HITL boot wrote 0)
        self.assertNotIn('CAL_ACC0_XOFF', by)  # fc_owned: never touched

    def fc(self):
        return FakeFC({p['name']: p['default'] for p in FIRMWARE} | self.hitl_fc())

    def test_writes_survive_px4_and_fail_without_the_wait(self):
        writes = fs.plan(self.flight, self.readback(self.hitl_fc()))
        fc = self.fc()
        done = fs.apply(writes, fc.set, fc.get, sleep=fc.sleep, clock=fc.clock)
        fc.sleep(5)  # PX4 still looking afterwards changes nothing
        want = {'PWM_MAIN_FUNC1': 201, 'PWM_MAIN_DIS1': 1425, 'PWM_MAIN_FUNC3': 101, 'PWM_MAIN_MIN3': 1000,
                'PWM_MAIN_MAX3': 2000, 'GPS_1_CONFIG': 201, 'SYS_HITL': 0}
        self.assertEqual({n: fc.values[n] for n in want}, want, fc.log)
        self.assertEqual([d['name'] for d in done][-2:], ['GPS_1_CONFIG', 'SYS_HITL'])
        # Without the wait: PX4 acts on the second function write about 1 s later, after its values were written,
        # as on the derived project's Cube; the check after the reboot would then fail.
        settle = pwm_defaults.SETTLE_S
        try:
            pwm_defaults.SETTLE_S = 0.0
            fc = self.fc()
            fs.apply(writes, fc.set, fc.get, sleep=fc.sleep, clock=fc.clock)
            fc.sleep(5)
            self.assertEqual((fc.values['PWM_MAIN_MIN3'], fc.values['PWM_MAIN_MAX3']), (1100, 1900), fc.log)
        finally:
            pwm_defaults.SETTLE_S = settle

    def test_a_value_px4_keeps_changing_stops_before_sys_hitl(self):
        writes = fs.plan(self.flight, self.readback(self.hitl_fc()))
        fc = self.fc()
        get = lambda w: 1100 if w['name'] == 'PWM_MAIN_MIN3' else fc.get(w)
        with self.assertRaises(SystemExit) as stop:
            fs.apply(writes, fc.set, get, sleep=fc.sleep, clock=fc.clock)
        self.assertIn('"px4_changed": ["PWM_MAIN_MIN3"]', str(stop.exception))
        self.assertEqual((fc.values['SYS_HITL'], fc.values['GPS_1_CONFIG']), (1, 0))  # still in HITL
        self.assertEqual(sum(1 for _, n, v in fc.log if n == 'PWM_MAIN_MIN3' and v == 1000), 1 + fs.ROUNDS)

    def test_plan_back_to_hitl(self):
        flight_fc = {'SYS_HITL': 0, 'GPS_1_CONFIG': 201, 'PWM_MAIN_FUNC1': 201, 'PWM_MAIN_DIS1': 1425,
                     'PWM_MAIN_FUNC3': 101, 'PWM_MAIN_MIN3': 1100, 'PWM_MAIN_MAX3': 1900}
        writes = fs.plan(self.hitl, self.readback(flight_fc))
        by = {w['name']: w['new'] for w in writes}
        self.assertEqual(by, {'SYS_HITL': 1, 'PWM_MAIN_FUNC1': 0, 'PWM_MAIN_DIS1': 1000, 'PWM_MAIN_FUNC3': 0,
                              'PWM_MAIN_MIN3': 1000, 'PWM_MAIN_MAX3': 2000})
        self.assertFalse(any('px4io' in w for w in writes))  # functions to 0: PX4 sets nothing
        self.assertEqual(writes[-1]['name'], 'SYS_HITL')


if __name__ == '__main__':
    unittest.main()
