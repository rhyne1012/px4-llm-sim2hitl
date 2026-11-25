#!/usr/bin/env python3
"""Switch an FC between a flight recipe (SYS_HITL=0) and a HITL recipe by parameters: the step param-deploy cannot do.

From a derived project (2026-10-26, a SkySurfer on a Cube Orange+; generalised 2026-11-22 with the HITL / flight
console, hitl/console/). A recipe pair is a HITL recipe and a flight recipe with the same firmware and the same SD
card files (boot file, logger topic list): pair() checks that, so switching only writes parameters (hitl/
sim_to_flight.md section 1).

  <venv python> -B deploy/flight_switch.py --release deploy/<recipe> --readback <params_*.json> [--write]
  <venv python> -B deploy/flight_switch.py --pair deploy/<hitl recipe> deploy/<flight recipe>

param-deploy writes only to an FC in HITL (its gate reads SYS_HITL=1 before every value) and its reboot check reads
SYS_HITL=1 back, so it can neither turn HITL off nor write to an FC in flight. This script writes the recipe's 'set'
values either way, with the user's approval each time (the console's confirm button; AGENTS section 3: automation does
not turn HITL off on its own).

Plan (default, nothing written): the recipe's 'set' values that differ from the readback (a fresh
./runbridge param-readback of this FC, firmware already the recipe's), then every other value check_params finds
off its firmware default (not_default; fc_owned values are never touched): back to the default. Output functions
first; the values PX4 sets on its own after a function write (host/pwm_defaults.py: a new servo's disarmed value 1500,
a new motor's 1100-1900) are marked 'px4io' with PX4's value, also when the FC holds the recipe's value already (PX4
would change it). GPS_1_CONFIG and SYS_HITL last (a HITL boot writes GPS_1_CONFIG 0, so it can only be set once HITL
is off).
--write: through the owner's agent port (udp 14560, the owner must be running and no automatic pilot on that port):
the FC must answer with the readback's uid and be unarmed; each value is sent with PARAM_SET until the FC echoes
exactly that value (3 tries). After the function writes PX4 acts on, the next value waits pwm_defaults.SETTLE_S; after
the last value (before GPS_1_CONFIG and SYS_HITL) the marked ones are read again and written again where PX4 set its
own (up to 3 rounds); one still not the recipe's stops the switch before SYS_HITL. Then PX4 saves, and the FC
reboots. Afterwards: param-readback, and deploy/check_params.py with the same recipe must PASS. Prints one JSON line
and writes it next to the readback.
"""
import argparse
import hashlib
import json
import math
import os
import struct
import sys
import time
from pathlib import Path

os.environ.setdefault('MAVLINK20', '1')
from pymavlink import mavutil  # noqa: E402

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / 'hitl'))
import check_params  # noqa: E402
from host import pwm_defaults  # noqa: E402

LAST = ['GPS_1_CONFIG', 'SYS_HITL']  # in this order, after every other value
SD_FILES = ['etc/extras.txt', 'etc/logging/logger_topics.txt']  # what deploy-test puts on the card (host/deploy.py)
ROUNDS = 3


def same(a, b):
    if isinstance(a, float) or isinstance(b, float):
        return math.isclose(float(a), float(b), rel_tol=1e-6, abs_tol=1e-9)
    return a == b


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest() if path.is_file() else None


def pair(hitl, flight):
    """A HITL recipe and a flight recipe the switch can go between: the same firmware (firmware.json's image and
    parameter list) and the same SD card files, the HITL one with SYS_HITL 1 and the flight one without (0 is the
    default). problems: why not; differences: the 'set' values that differ (the switch writes these)."""
    hitl, flight = Path(hitl), Path(flight)
    problems = []
    recipes = {}
    for side, path in (('hitl', hitl), ('flight', flight)):
        try:
            recipes[side] = json.loads((path / 'params.json').read_text())
            recipes[side]['_firmware'] = json.loads((path / recipes[side]['firmware']).read_text())['outputs']
        except (OSError, ValueError, KeyError) as exc:
            return {'problems': [f'{path.name}: {exc}'], 'differences': []}
    h, f = recipes['hitl'], recipes['flight']
    for what in ('firmware', 'parameters'):
        if (h['_firmware'].get(what) or {}).get('sha256') != (f['_firmware'].get(what) or {}).get('sha256'):
            problems.append(f'firmware.json {what}: the two recipes differ (a switch writes parameters only)')
    for name in SD_FILES:
        if digest(hitl / 'sd' / name) != digest(flight / 'sd' / name):
            problems.append(f'sd/{name}: the two recipes differ (a switch does not change the SD card)')
    if (h['set'].get('SYS_HITL') or {}).get('value') != 1:
        problems.append(f'{hitl.name}: SYS_HITL is not 1')
    if (f['set'].get('SYS_HITL') or {}).get('value', 0) != 0:
        problems.append(f'{flight.name}: SYS_HITL is not 0')
    differences = []
    for name in sorted(set(h['set']) | set(f['set'])):
        a, b = (h['set'].get(name) or {}).get('value'), (f['set'].get(name) or {}).get('value')
        if a is None or b is None or not same(a, b):
            differences.append({'name': name, 'hitl': a, 'flight': b})
    return {'problems': problems, 'differences': differences}


def plan(release, readback_path):
    recipe = json.loads((release / 'params.json').read_text())
    firmware = check_params.load_firmware(release / recipe['firmware_params']['file'])
    owned = set(check_params.owned_names(firmware, recipe['fc_owned']['patterns']))
    fc = {p['name']: p for p in json.loads(readback_path.read_text())['parameters']}
    writes = []
    for name, entry in recipe['set'].items():
        if name not in fc:
            raise SystemExit(f'{name} is not on the FC: is the recipe firmware flashed?')
        if not same(fc[name]['value'], entry['value']):
            writes.append({'name': name, 'old': fc[name]['value'], 'new': entry['value'], 'type': fc[name]['type']})
    for row in check_params.check(release, readback_path)['not_default']:
        if row['fc'] is None:
            raise SystemExit(f'{row["name"]} reads back as null: not writing over it')
        writes.append({'name': row['name'], 'old': row['fc'], 'new': row['default'], 'type': fc[row['name']]['type'],
                       'why': 'not in the recipe: back to the firmware default'})
    for w in list(writes):
        marked = []
        for name, value in pwm_defaults.automatic_values(w['name'], w['old'], w['new']):
            if name not in fc or name in owned:
                continue
            entry = next((x for x in writes if x['name'] == name), None)
            target = entry['new'] if entry else (recipe['set'][name]['value'] if name in recipe['set']
                                                  else firmware[name].get('default', 0))
            if same(target, value):
                continue  # PX4's value is the recipe's
            if entry is None:
                entry = {'name': name, 'old': fc[name]['value'], 'new': target, 'type': fc[name]['type']}
                writes.append(entry)
            entry['px4io'] = value
            entry['px4io_note'] = f'PX4 sets {name} to {value} after {w["name"]} {w["old"]:g} -> {w["new"]:g}'
            marked.append(name)
        if marked:
            w['px4io_trigger'] = marked
    order = lambda w: (2 + LAST.index(w['name']) if w['name'] in LAST else 0 if pwm_defaults.is_function(w['name'])
                       else 1)
    writes.sort(key=order)
    return writes


def encode(value, kind):
    """PARAM_SET float field: int32 parameters travel as their 4 bytes (PX4 bytewise encoding). kind is the
    readback's MAV_PARAM_TYPE (6 int32, 9 real32)."""
    if kind not in (mavutil.mavlink.MAV_PARAM_TYPE_INT32, mavutil.mavlink.MAV_PARAM_TYPE_REAL32):
        raise SystemExit(f'unexpected parameter type {kind}')
    if kind == mavutil.mavlink.MAV_PARAM_TYPE_INT32:
        return struct.unpack('<f', struct.pack('<i', int(value)))[0], mavutil.mavlink.MAV_PARAM_TYPE_INT32
    return float(value), mavutil.mavlink.MAV_PARAM_TYPE_REAL32


def decode(message):
    if message.param_type == mavutil.mavlink.MAV_PARAM_TYPE_INT32:
        return struct.unpack('<i', struct.pack('<f', message.param_value))[0]
    return message.param_value


def apply(writes, set_value, get_value, sleep=time.sleep, clock=time.monotonic):
    """Write the plan in its order. set_value(w): write w['new'], return the FC's echo (it equals w['new']) or raise
    SystemExit; get_value(w): the FC's value of w['name']. Returns the writes done (with their echo), rewrites after
    PX4's own value included (marked rewritten_after_px4io)."""
    done = []
    trigger_at = None
    body = [w for w in writes if w['name'] not in LAST]
    for w in body:
        if w.get('px4io') is not None and trigger_at is not None:
            sleep(max(0.0, trigger_at + pwm_defaults.SETTLE_S - clock()))
        done.append(dict(w, echo=set_value(w)))
        if w.get('px4io_trigger'):
            trigger_at = clock()
    late = [w for w in body if w.get('px4io') is not None and not same(w['px4io'], w['new'])]
    last = clock()
    for _ in range(ROUNDS if late else 0):
        sleep(max(0.0, last + pwm_defaults.SETTLE_S - clock()))
        again = False
        for w in late:
            if same(get_value(w), w['px4io']):
                done.append(dict(w, echo=set_value(w), rewritten_after_px4io=True))
                last, again = clock(), True
        if not again:
            break
    wrong = [w['name'] for w in late if not same(get_value(w), w['new'])]
    if wrong:
        raise SystemExit(json.dumps({'status': 'FAIL', 'px4_changed': wrong, 'written': done}))
    for w in writes:
        if w['name'] in LAST:
            done.append(dict(w, echo=set_value(w)))
    return done


class Link:
    """PARAM_SET with echo and PARAM_REQUEST_READ through the owner's agent port."""

    def __init__(self, m):
        self.m = m

    def set(self, w):
        value, kind = encode(w['new'], w['type'])
        for _ in range(3):
            self.m.mav.param_set_send(1, 1, w['name'].encode(), value, kind)
            echo = self._wait(w['name'], lambda v: same(v, w['new']))
            if echo is not None and same(echo, w['new']):
                return echo
        raise SystemExit(json.dumps({'status': 'FAIL', 'stopped_at': w['name']}))

    def get(self, w):
        for _ in range(3):
            self.m.mav.param_request_read_send(1, 1, w['name'].encode(), -1)
            value = self._wait(w['name'], lambda v: True)
            if value is not None:
                return value
        raise SystemExit(json.dumps({'status': 'FAIL', 'not_read': w['name']}))

    def _wait(self, name, done, seconds=2.0):
        end = time.monotonic() + seconds
        value = None
        while time.monotonic() < end:
            msg = self.m.recv_match(type='PARAM_VALUE', blocking=True, timeout=0.3)
            if msg is not None and msg.param_id.rstrip('\0') == name:
                value = decode(msg)
                if done(value):
                    break
        return value


def write(writes, uid, port):
    m = mavutil.mavlink_connection(f'udpin:127.0.0.1:{port}', source_system=254, source_component=192)
    heartbeat = m.wait_heartbeat(timeout=10)
    if heartbeat is None or heartbeat.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED:
        raise SystemExit('no heartbeat, or the FC is armed')
    m.mav.command_long_send(1, 1, mavutil.mavlink.MAV_CMD_REQUEST_MESSAGE, 0, 148, 0, 0, 0, 0, 0, 0)
    version = m.recv_match(type='AUTOPILOT_VERSION', blocking=True, timeout=5)
    if version is None or version.uid != uid:
        raise SystemExit(f'the FC is not the readback\'s (uid {getattr(version, "uid", None)}, expected {uid})')
    link = Link(m)
    done = apply(writes, link.set, link.get)
    time.sleep(3)  # PX4 saves changed parameters on its own (param autosave)
    m.mav.command_long_send(1, 1, mavutil.mavlink.MAV_CMD_PREFLIGHT_REBOOT_SHUTDOWN, 0, 1, 0, 0, 0, 0, 0, 0)
    return done


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--release', type=Path)
    parser.add_argument('--readback', type=Path)
    parser.add_argument('--pair', type=Path, nargs=2, metavar=('HITL', 'FLIGHT'), help='check a recipe pair only')
    parser.add_argument('--write', action='store_true', help='write and reboot (default: plan only)')
    parser.add_argument('--port', type=int, default=14560, help="the owner's agent port")
    args = parser.parse_args()
    if args.pair:
        result = pair(*args.pair)
        print(json.dumps(result))
        return 3 if result['problems'] else 0
    if not args.release or not args.readback:
        parser.error('--release and --readback (or --pair)')
    readback = json.loads(args.readback.read_text())
    writes = plan(args.release, args.readback)
    result = {'status': 'PLAN', 'release': str(args.release), 'readback': str(args.readback), 'writes': writes}
    if args.write:
        result['written'] = write(writes, readback['autopilot_version']['uid'], args.port)
        result['status'] = 'WRITTEN, rebooting: restart the owner, param-readback, check_params'
    line = json.dumps(result)
    (args.readback.parent / f'flight_switch_{time.strftime("%Y%m%d_%H%M%S")}.json').write_text(line + '\n')
    print(line)
    return 0


if __name__ == '__main__':
    sys.exit(main())
