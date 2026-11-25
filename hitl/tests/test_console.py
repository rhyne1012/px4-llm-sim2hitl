"""The HITL / flight console (hitl/console/console.py) without an FC: the units file, which readbacks it accepts, the
check of a synthetic readback against a synthetic recipe pair, the switch plan (deploy/flight_switch.py), and the
page's guard (token, local host). The recipes are copies of deploy/02_template_cubeorangeplus with a small synthetic
firmware (image and parameter list) in a temporary deploy folder."""
import contextlib
import copy
import hashlib
import http.client
import importlib.util
import io
import json
import lzma
import shutil
import struct
import tempfile
import threading
import time
import types
import unittest
from pathlib import Path
from unittest import mock

RUNTIME = Path(__file__).resolve().parents[1]
PROJECT = RUNTIME.parent
spec = importlib.util.spec_from_file_location('console', RUNTIME / 'console' / 'console.py')
console = importlib.util.module_from_spec(spec)
spec.loader.exec_module(console)
import check_params  # noqa: E402 - on the path through console
import flight_switch  # noqa: E402

BASE = PROJECT / 'deploy' / '02_template_cubeorangeplus'
KINDS = {'Int32': 6, 'Float': 9}
AIRCRAFT, BENCH = '1111', '2222'
SECTIONS = ('airframe', 'boot', 'verify_only', 'set')


def sha(data):
    return hashlib.sha256(data).hexdigest()


def firmware_list(params):
    """A small parameter list: every name the recipe states, its fc_owned names, the output channels."""
    listing = {}
    for section in SECTIONS:
        for name, entry in params[section].items():
            kind = 'Float' if isinstance(entry['value'], float) else 'Int32'
            listing[name] = {'name': name, 'type': kind, 'default': 0.0 if kind == 'Float' else 0}
    for name in params['fc_owned']['resolved_names']:
        listing[name] = {'name': name, 'type': 'Int32', 'default': 0}
    for bank in ('MAIN', 'AUX'):
        for i in range(1, 9):
            for what, default in (('FUNC', 0), ('DIS', 900), ('MIN', 1000), ('MAX', 2000)):
                listing[f'PWM_{bank}_{what}{i}'] = {'name': f'PWM_{bank}_{what}{i}', 'type': 'Int32', 'default': default}
    listing['GPS_1_CONFIG'] = {'name': 'GPS_1_CONFIG', 'type': 'Int32', 'default': 201}
    listing['SYS_HITL'] = {'name': 'SYS_HITL', 'type': 'Int32', 'default': 0}
    return [listing[n] for n in sorted(listing)]


def servos(params):
    for i in range(1, 5):  # MAIN1-4: the four control surfaces, in HITL and in flight
        params['set'][f'PWM_MAIN_FUNC{i}'] = {'value': 200 + i}


def hitl_recipe(params):
    servos(params)


def flight_recipe(params):
    # SYS_HITL 0, a motor on AUX1, and no GPS_1_CONFIG 0 (only a HITL boot writes it): the firmware default 201
    servos(params)
    params['set']['SYS_HITL'] = {'value': 0}
    params['set']['PWM_AUX_FUNC1'] = {'value': 101}
    del params['boot']['GPS_1_CONFIG']


def make_recipes(deploy):
    """myplane_hitl and myplane_flight (a pair: the same synthetic firmware and SD files) and bench_hitl."""
    base = json.loads((BASE / 'params.json').read_text())
    raw = lzma.compress(json.dumps({'parameters': firmware_list(base)}).encode())
    image = b'synthetic firmware image'
    for name, edit in (('myplane_hitl', hitl_recipe), ('myplane_flight', flight_recipe), ('bench_hitl', hitl_recipe)):
        folder = deploy / name
        shutil.copytree(BASE, folder)
        info = json.loads((folder / 'firmware' / 'firmware.json').read_text())
        (folder / 'firmware' / info['outputs']['firmware']['file']).write_bytes(image)
        (folder / 'firmware' / 'parameters.json.xz').write_bytes(raw)
        info['release'] = name
        info['outputs']['firmware']['sha256'] = sha(image)
        info['outputs']['parameters']['sha256'] = sha(raw)
        (folder / 'firmware' / 'firmware.json').write_text(json.dumps(info, indent=1))
        params = copy.deepcopy(base)
        params['release'] = name
        params['firmware_params']['sha256'] = sha(raw)
        edit(params)
        (folder / 'params.json').write_text(json.dumps(params, indent=1))


def flat(recipe):
    p = json.loads((recipe / 'params.json').read_text())
    return {k: v['value'] for s in SECTIONS for k, v in p[s].items()}


def write_readback(path, recipe, values, uid=int(AIRCRAFT), verdict='PASS'):
    """A param-readback file of an FC running recipe's firmware with these values (the rest at the defaults)."""
    listing = check_params.load_firmware(recipe / 'firmware' / 'parameters.json.xz')
    embedded = json.loads((recipe / 'firmware' / 'firmware.json').read_text())['embedded']
    rows = []
    for index, (name, p) in enumerate(sorted(listing.items())):
        kind = KINDS[p['type']]
        value = values.get(name, p.get('default', 0))
        rows.append({'name': name, 'value': value, 'type': kind, 'index': index,
                     'bits': struct.pack('<i' if kind == 6 else '<f', value).hex()})
    data = {'schema_version': 2, 'verdict': verdict, 'consistency': [], 'param_count_used': len(rows),
            'used_received': len(rows), 'used_index_missing': [],
            'param_list': {'sha256': sha((recipe / 'firmware' / 'parameters.json.xz').read_bytes())},
            'autopilot_version': {'board_version': embedded['board_version'], 'git_hash_prefix': embedded['git_hash'][:10],
                                  'os_hash_prefix': embedded['nuttx_git_hash'][:16], 'uid': uid},
            'parameters': rows}
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data))
    return data


def write_units(path, units=None, **extra):
    units = units or {BENCH: {'name': '台上', 'role': 'hitl_only', 'hitl': 'bench_hitl', 'flight': None},
                      AIRCRAFT: {'name': '飛機', 'role': 'aircraft', 'hitl': 'myplane_hitl', 'flight': 'myplane_flight'}}
    path.write_text(json.dumps(dict({'title': '測試台', 'takeoff_m': 30, 'units': units}, **extra), ensure_ascii=False))
    return path


class Synthetic(unittest.TestCase):
    """A temporary deploy folder with the synthetic recipes, used by the console as its deploy/."""
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.dir = Path(self.temp.name)
        self.deploy = self.dir / 'deploy'
        self.deploy.mkdir()
        make_recipes(self.deploy)
        patcher = mock.patch.object(console, 'DEPLOY', self.deploy)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.hitl, self.flight = self.deploy / 'myplane_hitl', self.deploy / 'myplane_flight'

    def tearDown(self):
        self.temp.cleanup()

    def sd(self, recipe):
        return {key: console.sha256(recipe / 'sd' / local) for key, (_, local) in console.SD.items()}


class UnitsTests(Synthetic):
    def test_units_file_is_loaded(self):
        setup = console.load_units(write_units(self.dir / 'units.json'))
        self.assertEqual(setup['problems'], [])
        self.assertEqual((setup['title'], setup['takeoff_m']), ('測試台', 30))
        self.assertEqual(list(setup['units']), [BENCH, AIRCRAFT])  # the file's order: the first one reads back first
        self.assertEqual(setup['units'][AIRCRAFT]['flight'], 'myplane_flight')
        bare = self.dir / 'bare.json'  # without title and takeoff_m: the defaults
        bare.write_text(json.dumps({'units': json.loads((self.dir / 'units.json').read_text())['units']}))
        defaults = console.load_units(bare)
        self.assertEqual((defaults['title'], defaults['takeoff_m'], defaults['problems']),
                         (console.TITLE, console.TAKEOFF_M, []))

    def test_wrong_units_are_refused(self):
        bad = {AIRCRAFT: {'name': '飛機', 'role': 'pilot', 'hitl': 'myplane_hitl', 'flight': None},
               BENCH: {'name': '台上', 'role': 'hitl_only', 'hitl': 'bench_hitl', 'flight': 'myplane_flight'},
               'abc': {'name': 'x', 'role': 'aircraft', 'hitl': 'myplane_hitl', 'flight': None},
               '3333': {'name': 'y', 'role': 'aircraft', 'hitl': '../myplane_hitl', 'flight': 'nothing_here'}}
        setup = console.load_units(write_units(self.dir / 'units.json', bad))
        self.assertIsNone(setup['units'])
        text = '\n'.join(setup['problems'])
        for needle in ('"role"', 'hitl_only', 'abc', '"hitl" 要是', '配方 nothing_here 不存在'):
            self.assertIn(needle, text)
        broken = self.dir / 'broken.json'
        broken.write_text('{')
        self.assertIsNone(console.load_units(broken)['units'])

    def test_the_example_is_valid_but_its_recipes_are_placeholders(self):
        example = json.loads(console.UNITS_EXAMPLE.read_text())
        self.assertEqual((example['title'], example['takeoff_m']), (console.TITLE, console.TAKEOFF_M))
        with mock.patch.object(console, 'DEPLOY', self.dir / 'empty'):  # a deploy folder without those recipes
            problems = console.units_problems(example)
        self.assertTrue(problems)
        self.assertTrue(all('不存在' in p for p in problems), problems)  # only the placeholder recipe names
        self.assertEqual(console.units_problems(example), [])  # recipes of those names: usable as it is
        self.assertEqual({u['role'] for u in example['units'].values()}, set(console.ROLES))

    def test_without_a_units_file_nothing_is_read_and_close_works(self):
        missing = self.dir / 'deploy' / 'units.json'
        with mock.patch.object(console, 'qs') as qs, mock.patch.object(console, 'qgc_running', return_value=False), \
                mock.patch.object(console, 'autoconnect') as autoconnect, contextlib.redirect_stdout(io.StringIO()):
            c = console.Console(self.dir, missing)
            self.assertIn('deploy/units.json', c.setup['problems'][0])
            with self.assertRaises(console.Stop) as stop:
                c.check()
            self.assertIn('把 hitl/console/units.example.json 複製成 deploy/units.json', str(stop.exception))
            for plan in ('hitl', 'flight'):
                self.assertRaises(console.Stop, c.make_plan, plan)
            self.assertRaises(console.Stop, c.sim_start, 'auto')
            with Page(c) as page:
                self.assertEqual(page.ask('POST', '/api/check', token='T0K')[0], 200)  # accepted, then stops
                end = time.monotonic() + 5
                while not (c.op and c.op['done']) and time.monotonic() < end:
                    time.sleep(0.02)
                self.assertIn('units.example.json', c.op['error'])
                status = json.loads(page.ask('GET', '/api/status')[1])
                self.assertTrue(status['setup']['problems'])
                self.assertEqual(page.ask('POST', '/api/quit', token='T0K')[0], 200)
                self.assertTrue(c.quit.is_set())
            qs.status.assert_not_called()  # no owner started, no FC read
            qs.runbridge.assert_not_called()
            autoconnect.assert_not_called()  # QGC's settings untouched


class ReadbackTests(unittest.TestCase):
    def test_which_readbacks_are_used(self):
        good = {'path': 'x.json', 'verdict': 'PASS', 'autopilot_version': {'uid': 7}, 'used_index_missing': [],
                'consistency': []}
        self.assertTrue(console.readback_usable(0, good))
        # another firmware's list: only names differ -> used (it still says which FC)
        names = dict(good, verdict='INCOMPLETE', missing=['HIL_ACT_FUNC1'], missing_count=17, not_in_list=['X'],
                     type_mismatch=['Y'])
        self.assertTrue(console.readback_usable(5, names))
        for change in ({'used_index_missing': [3], 'used_index_missing_count': 1}, {'consistency_count': 2},
                       {'consistency': [{'problem': 'value_changed'}]}, {'identity_missing': True},
                       {'autopilot_version': None}, {'path': None}):
            self.assertFalse(console.readback_usable(5, dict(names, **change)), change)
        self.assertFalse(console.readback_usable(3, names))  # not a completed readback
        self.assertFalse(console.readback_usable(5, None))
        message = console.readback_failure(dict(names, used_index_missing=[3], used_index_missing_count=1,
                                                autopilot_version={'board_version': 4184, 'git_hash_prefix': 'c45268d056'}))
        for needle in ('4184', 'c45268d056', 'used_index_missing 1'):
            self.assertIn(needle, message)
        self.assertIn('板號 56', console.readback_failure({'autopilot_version': {'board_version': 56}, 'error': 'x'}))


class CheckAndPlanTests(Synthetic):
    def hitl_state(self, name='rb.json'):
        values = flat(self.hitl)
        path = self.dir / name
        return path, write_readback(path, self.hitl, values)

    def test_synthetic_pair(self):
        self.assertEqual(flight_switch.pair(self.hitl, self.flight)['problems'], [])
        self.assertEqual({d['name'] for d in flight_switch.pair(self.hitl, self.flight)['differences']},
                         {'SYS_HITL', 'PWM_AUX_FUNC1'})

    def test_switch_plan_through_flight_switch(self):
        path, _ = self.hitl_state()
        self.assertEqual(check_params.check(self.hitl, path)['verdict'], 'PASS')
        writes = flight_switch.plan(self.flight, path)
        self.assertEqual([(w['name'], w['new']) for w in writes],
                         [('PWM_AUX_FUNC1', 101), ('PWM_AUX_MIN1', 1000), ('PWM_AUX_MAX1', 2000),
                          ('GPS_1_CONFIG', 201), ('SYS_HITL', 0)])  # functions first, GPS_1_CONFIG and SYS_HITL last
        rows = console.plan_rows(writes)
        self.assertIn('配方沒有，改回預設', rows[3])
        self.assertIn('PX4 寫完功能後會自己改成 1100，之後寫回', rows[1])
        self.assertIn('PX4 寫完功能後會自己改成 1900', rows[2])
        self.assertEqual(rows[0], 'PWM_AUX_FUNC1  0 → 101')
        self.assertEqual(rows[4], 'SYS_HITL  1 → 0')

    def info(self, path, readback):
        unit = console.load_units(write_units(self.dir / 'units.json'))['units'][AIRCRAFT]
        info = console.judge(AIRCRAFT, unit, path, readback, self.sd(self.hitl), self.dir / 'check')
        info.update(generation=7, at=time.time())
        return info

    def console_with(self, info):
        c = console.Console(self.dir, write_units(self.dir / 'units.json'))
        c.check = lambda: info
        return c

    def test_judge_and_plan_to_flight(self):
        path, readback = self.hitl_state()
        info = self.info(path, readback)
        hitl, flight = info['checks']['hitl'], info['checks']['flight']
        self.assertEqual((hitl['verdict'], hitl['sd_ok'], hitl['firmware_ok']), ('PASS', True, True))
        self.assertEqual((flight['verdict'], flight['sd_ok'], flight['firmware_ok']), ('FAIL', True, True))
        self.assertTrue((self.dir / 'check' / 'check_flight_myplane_flight.json').is_file())  # the full report
        self.assertEqual(info['SYS_HITL'], 1)
        self.assertEqual(info['outputs'], {'servos': ['MAIN1', 'MAIN2', 'MAIN3', 'MAIN4'], 'motors': []})
        c = self.console_with(info)
        self.assertIn('HITL 和實飛配方差 2 個值', c.check_line(info))
        with contextlib.redirect_stdout(io.StringIO()):
            c.make_plan('flight')
            self.assertEqual((c.plan['kind'], c.plan['target'], c.plan['uid'], c.plan['generation']),
                             ('params', 'flight', AIRCRAFT, 7))
            self.assertEqual(len(c.plan['rows']), 5)
            c.make_plan('hitl')  # already the HITL recipe: nothing to switch
            self.assertIsNone(c.plan)

    def test_a_pair_that_does_not_match_refuses_the_switch(self):
        (self.flight / 'sd' / 'etc' / 'extras.txt').write_text('another boot file\n')
        path, readback = self.hitl_state()
        info = self.info(path, readback)
        self.assertTrue(info['pair']['problems'])
        c = self.console_with(info)
        self.assertIn('配方對有問題', c.check_line(info))
        with self.assertRaises(console.Stop) as stop:
            c.make_plan('flight')
        self.assertIn('sd/etc/extras.txt', str(stop.exception))
        self.assertIsNone(c.plan)
        try:  # back to HITL is not refused for the pair: the HITL recipe's own check guards it
            c.make_plan('hitl')
        except console.Stop as exc:
            self.assertNotIn('sd/etc/extras.txt', str(exc))

    def test_a_recipe_not_built_here_is_named(self):
        # firmware/*.px4 and parameters.json.xz are built locally (not in git): a flight recipe never deployed on
        # this machine may not have them
        (self.flight / 'firmware' / 'parameters.json.xz').unlink()
        self.assertIn('build-firmware --release deploy/myplane_flight', console.recipe_files_missing('myplane_flight'))
        self.assertIsNone(console.recipe_files_missing('myplane_hitl'))
        path, readback = self.hitl_state()
        info = self.info(path, readback)
        self.assertEqual(info['checks']['hitl']['verdict'], 'PASS')
        self.assertEqual(info['checks']['flight']['verdict'], 'INCOMPLETE')
        with self.assertRaises(console.Stop) as stop:
            self.console_with(info).make_plan('flight')
        self.assertIn('build-firmware', str(stop.exception))

    def test_hitl_only_and_unknown_units_do_not_switch_to_flight(self):
        path, readback = self.hitl_state()
        units = console.load_units(write_units(self.dir / 'units.json'))['units']
        bench = console.judge(BENCH, units[BENCH], path, readback, self.sd(self.hitl))
        self.assertIsNone(bench['pair'])
        self.assertEqual(list(bench['checks']), ['hitl'])
        c = self.console_with(dict(bench, generation=7))
        with self.assertRaises(console.Stop) as stop:
            c.make_plan('flight')
        self.assertIn('只做 HITL', str(stop.exception))
        unknown = console.judge('999', {'name': '不認得的飛控', 'role': 'unknown', 'hitl': None, 'flight': None},
                                path, readback, self.sd(self.hitl))
        c = self.console_with(dict(unknown, generation=7))
        self.assertIn('uid 999', c.check_line(unknown))
        for target in ('flight', 'hitl'):
            self.assertRaises(console.Stop, c.make_plan, target)

    def test_check_reads_back_again_with_the_units_own_recipe(self):
        # The first readback uses the first unit's HITL recipe (bench_hitl); on this FC (the aircraft) it is
        # INCOMPLETE by names only, so it is read again with myplane_hitl. The next check starts with myplane_hitl.
        hitl_values = flat(self.hitl)
        answers = []
        calls = []

        def runbridge(*args, timeout=None):
            calls.append(args)
            if args[0] == 'param-readback':
                release, out = Path(args[args.index('--release') + 1]), Path(args[args.index('--out') + 1])
                code, verdict, extra = answers.pop(0)
                path = out / 'params_x.json'
                data = write_readback(path, release, hitl_values, verdict=verdict)
                return code, dict({k: data[k] for k in ('verdict', 'autopilot_version', 'used_index_missing',
                                                         'consistency')}, path=str(path), **extra)
            if args[0] == 'sd-list':
                where = args[args.index('--sd-path') + 1]
                return 0, {'entries': [{'name': 'extras.txt'}] if where == '/fs/microsd/etc' else []}
            if args[0] == 'sd-get':
                return 0, {'sha256': console.sha256(self.hitl / 'sd' / 'etc' / 'extras.txt')}
            raise AssertionError(args)

        status = {'fc': {'state': 'verified', 'armed': False, 'SYS_HITL': 1, 'connection_generation': 7},
                  'model': 'stopped'}
        fake = types.SimpleNamespace(status=lambda: status, runbridge=runbridge, cache=lambda: self.dir)
        releases = lambda: [Path(a[a.index('--release') + 1]).name for a in calls if a[0] == 'param-readback']
        with mock.patch.object(console, 'qs', fake), mock.patch.object(console, 'qgc_running', return_value=False), \
                mock.patch.object(console, 'QGC_INI', self.dir / 'QGroundControl.ini'), \
                contextlib.redirect_stdout(io.StringIO()):
            c = console.Console(self.dir, write_units(self.dir / 'units.json'))
            names_only = {'missing': ['HIL_ACT_FUNC1'], 'missing_count': 1, 'not_in_list': ['X'],
                          'not_in_list_count': 1}
            answers[:] = [(5, 'INCOMPLETE', names_only), (0, 'PASS', {})]
            info = c.check()
            self.assertEqual(releases(), ['bench_hitl', 'myplane_hitl'])
            self.assertEqual((info['uid'], info['unit']['name'], info['checks']['hitl']['verdict']),
                             (AIRCRAFT, '飛機', 'PASS'))
            self.assertEqual(c.last_uid, AIRCRAFT)
            self.assertIn('autoConnectPixhawk=false', (self.dir / 'QGroundControl.ini').read_text())
            calls.clear()
            answers[:] = [(0, 'PASS', {})]
            c.check()
            self.assertEqual(releases(), ['myplane_hitl'])
            calls.clear()
            answers[:] = [(5, 'INCOMPLETE', {'used_index_missing': [3], 'used_index_missing_count': 1})]
            with self.assertRaises(console.Stop) as stop:  # a used index not received: not a list mismatch
                c.check()
            self.assertIn('板號 4184', str(stop.exception))
            git = json.loads((BASE / 'firmware' / 'firmware.json').read_text())['embedded']['git_hash'][:10]
            self.assertIn(f'韌體 git {git}', str(stop.exception))  # the base recipe's firmware, whichever PX4 it is
            self.assertEqual(releases(), ['myplane_hitl'])  # no second readback


class PureTests(unittest.TestCase):
    def test_outputs_main_and_aux(self):
        readback = {'parameters': [{'name': f'PWM_MAIN_FUNC{i}', 'value': v} for i, v in
                                   zip(range(1, 9), (202, 203, 0, 204, 201, 0, 0, 0))]
                    + [{'name': f'PWM_AUX_FUNC{i}', 'value': v} for i, v in zip(range(1, 9), (101, 0, 205, 0, 0, 0, 0, 112))]
                    + [{'name': 'PWM_MAIN_FUNC10', 'value': 206}, {'name': 'SYS_HITL', 'value': 1},
                       {'name': 'PWM_MAIN_DIS1', 'value': 1500}]}
        self.assertEqual(console.outputs(readback), {'servos': ['MAIN1', 'MAIN2', 'MAIN4', 'MAIN5', 'MAIN10', 'AUX3'],
                                                     'motors': ['AUX1', 'AUX8']})
        readback['parameters'][2]['value'] = 101
        self.assertEqual(console.outputs(readback)['motors'], ['MAIN3', 'AUX1', 'AUX8'])

    def test_qgc_autoconnect_keys(self):
        ini = ('[General]\nfoo=1\n\n[AutoConnect]\nautoConnectLibrePilot=false\nautoConnectPixhawk=true\n'
               'autoConnectUDP=false\n\n[FlightMapPosition]\nlat=22\n')
        off = console.with_autoconnect(ini, console.QGC_OFF)
        self.assertIn('autoConnectPixhawk=false', off)
        self.assertIn('autoConnectSiKRadio=false', off)       # missing key added inside the section
        self.assertIn('autoConnectUDP=true', off)
        self.assertIn('autoConnectLibrePilot=false', off)     # untouched
        self.assertLess(off.index('autoConnectSiKRadio'), off.index('[FlightMapPosition]'))
        self.assertIn('[FlightMapPosition]\nlat=22', off)
        on = console.with_autoconnect(off, console.QGC_ON)
        self.assertIn('autoConnectPixhawk=true', on)
        self.assertIn('autoConnectSiKRadio=true', on)
        self.assertIn('autoConnectUDP=true', on)              # UDP stays on
        fresh = console.with_autoconnect('', console.QGC_ON)
        self.assertEqual(fresh, '[AutoConnect]\nautoConnectPixhawk=true\nautoConnectSiKRadio=true\n')
        self.assertEqual(console.with_autoconnect(on, console.QGC_ON), on)  # nothing to change

    def test_cpu_pinning_follows_the_machine(self):
        self.assertEqual(console.cpu_list('7,15\n'), [7, 15])
        self.assertEqual(console.cpu_list('0-6,8-14'), list(range(7)) + list(range(8, 15)))
        self.assertEqual(console.cpu_list('\n'), [])
        self.assertEqual(console.cpu_text([0, 1, 2, 3, 4, 5, 6, 8, 9, 10, 11, 12, 13, 14]), '0-6,8-14')
        self.assertEqual(console.cpu_text([3]), '3')
        online = list(range(16))
        # 7 and 15 isolated (isolcpus) -> the owner on 7, the rest off both
        self.assertEqual(console.pinning([7, 15], online), (7, [c for c in online if c not in (7, 15)]))
        # no isolated CPUs -> nothing pinned
        self.assertEqual(console.pinning([], list(range(12))), (None, None))
        self.assertEqual(console.pinning([0, 1], [0, 1]), (None, None))  # nothing left for the rest

    def test_mode_names(self):
        self.assertEqual(console.mode_name(7 << 16), 'Stabilized')
        self.assertEqual(console.mode_name((4 << 16) | (5 << 24)), 'Return')
        self.assertEqual(console.mode_name((4 << 16) | (3 << 24)), 'Hold')
        self.assertEqual(console.mode_name(None), '?')

    def test_long_findings_are_counted(self):
        report = {'wrong_value': [], 'not_default': [{'name': f'P{i}', 'fc': i, 'default': 0} for i in range(30)],
                  'not_read': [f'N{i}' for i in range(500)]}
        rows = console.summary(report, 'check.json')
        self.assertEqual(len(rows), console.SHOWN)
        self.assertIn('共 31 項', rows[-1])
        self.assertIn('check.json', rows[-1])
        self.assertIn('not_read: 500 項', console.summary({'wrong_value': [], 'not_default': [],
                                                          'not_read': [f'N{i}' for i in range(500)]})[0])


class Stub:
    """What the page handler needs of Console."""
    def __init__(self):
        self.state_lock = threading.Lock()
        self.plan = {'x': 1}
        self.started = []
        self.quit = threading.Event()

    def view(self):
        return {'ok': True}

    def start(self, name, fn):
        self.started.append(name)

    check = do_switch = sim_restart = sim_end = make_plan = sim_start = None


class Page:
    """The console's page server on a free local port."""
    def __init__(self, target, page='<p>__TOKEN__</p>'):
        self.server = console.ThreadingHTTPServer(('127.0.0.1', 0), console.handler(target, 'T0K', page))

    def __enter__(self):
        threading.Thread(target=self.server.serve_forever, daemon=True).start()
        self.port = self.server.server_address[1]
        return self

    def __exit__(self, *exc):
        self.server.shutdown()
        self.server.server_close()

    def ask(self, method, path, token=None, host=None, body=b'{}'):
        c = http.client.HTTPConnection('127.0.0.1', self.port, timeout=5)
        headers = {'Content-Type': 'application/json'}
        if token:
            headers['X-Console-Token'] = token
        if host:
            headers['Host'] = host
        c.request(method, path, body=body if method == 'POST' else None, headers=headers)
        r = c.getresponse()
        return r.status, r.read()


class PageGuardTests(unittest.TestCase):
    def setUp(self):
        self.stub = Stub()
        self.page = Page(self.stub).__enter__()
        self.ask = self.page.ask

    def tearDown(self):
        self.page.__exit__()

    def test_page_carries_the_token_and_status_is_open_locally(self):
        self.assertEqual(self.ask('GET', '/'), (200, b'<p>T0K</p>'))
        self.assertEqual(self.ask('GET', '/api/status')[0], 200)

    def test_actions_need_the_token_and_a_local_host(self):
        self.assertEqual(self.ask('POST', '/api/check')[0], 403)
        self.assertEqual(self.ask('POST', '/api/check', token='wrong')[0], 403)
        self.assertEqual(self.ask('POST', '/api/check', token='T0K', host='evil.example:80')[0], 403)
        self.assertEqual(self.ask('GET', '/', host='evil.example:80')[0], 403)  # DNS rebinding
        self.assertEqual(self.stub.started, [])
        self.assertEqual(self.ask('POST', '/api/check', token='T0K')[0], 200)
        self.assertEqual(self.stub.started, ['重新核對'])

    def test_plan_target_and_cancel(self):
        self.assertEqual(self.ask('POST', '/api/plan', token='T0K', body=b'{"target": "moon"}')[0], 400)
        self.assertEqual(self.ask('POST', '/api/plan', token='T0K', body=b'{"target": "flight"}')[0], 200)
        self.assertEqual(self.ask('POST', '/api/cancel', token='T0K')[0], 200)
        self.assertIsNone(self.stub.plan)
        self.assertEqual(self.ask('POST', '/api/nothing', token='T0K')[0], 404)

    def test_close_button_needs_the_token(self):
        self.assertEqual(self.ask('POST', '/api/quit')[0], 403)
        self.assertFalse(self.stub.quit.is_set())
        self.assertEqual(self.ask('POST', '/api/quit', token='T0K')[0], 200)
        self.assertTrue(self.stub.quit.is_set())

    def test_the_page_has_the_title_and_token_slots(self):
        page = (RUNTIME / 'console' / 'console.html').read_text()
        self.assertEqual(page.count('__TITLE__'), 2)  # <title> and the header
        self.assertIn("const TOKEN = '__TOKEN__';", page)


if __name__ == '__main__':
    unittest.main()
