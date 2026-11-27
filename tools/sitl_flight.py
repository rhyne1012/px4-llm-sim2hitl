#!/usr/bin/env python3
"""Fly a vehicle in PX4 SITL through simhost: parameters (set and read back), takeoff, loiter, record.

    <python with pymavlink> tools/sitl_flight.py --vehicle vehicles/testbird --px4-build <PX4>/build/px4_sitl_default_v2 \
        --simhost build/simhost/simhost --out <new folder> [--instance 9] [--loiter 60]

PX4 is stock (the vehicle's `[px4.sitl] airframe`, started by PX4's own rcS, which starts simulator_mavlink on TCP
4560 + instance). simhost runs the vehicle in lockstep with it. The script talks to PX4 on its offboard MAVLink port
(UDP 14540 + instance). Everything lands in --out: simhost.csv / simhost.log, px4.log, PX4's working directory (ULog
under px4/log), events.json and summary.json.
"""
import argparse
import json
import math
import os
import signal
import struct
import subprocess
import sys
import time
import tomllib
from pathlib import Path

from pymavlink import mavutil

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / 'fastcore'))
from fastcore import load_config  # noqa: E402  (the one reader of configuration files, shared with the fast core)

AUTO, AUTO_TAKEOFF, AUTO_LOITER = 4, 2, 3
INT_TYPES = {mavutil.mavlink.MAV_PARAM_TYPE_INT8, mavutil.mavlink.MAV_PARAM_TYPE_UINT8, mavutil.mavlink.MAV_PARAM_TYPE_INT16,
             mavutil.mavlink.MAV_PARAM_TYPE_UINT16, mavutil.mavlink.MAV_PARAM_TYPE_INT32, mavutil.mavlink.MAV_PARAM_TYPE_UINT32}


def encode_param(value, ptype):
    if ptype in INT_TYPES:
        return struct.unpack('<f', struct.pack('<i', int(round(value))))[0]
    return float(value)


def decode_param(raw, ptype):
    if ptype in INT_TYPES:
        return float(struct.unpack('<i', struct.pack('<f', raw))[0])
    return float(raw)


def simhost_vehicle_args(toml, configs=(), events=()):
    """simhost arguments for a vehicle: its actuator map and servo channels (vehicle.toml), its configuration files
    (JSBSim property and servo-chain settings, applied before the start), and scenario events (T:PROPERTY=VALUE)."""
    args = []
    for m in toml['actuators']:
        args += ['--actuator', f"{m['channel']}:{m['property']}:{m['gain']}:{m.get('offset', 0.0)}"]
        if m.get('kind') == 'servo':
            args += ['--servo-channel', str(m['channel'])]
    for k, v in load_config(*configs).items():
        args += ['--set', f'{k}={v!r}']
    for e in events:
        args += ['--at', e]
    return args


class Flight:
    def __init__(self, a):
        self.a = a
        self.vehicle = Path(a.vehicle).resolve()
        self.toml = tomllib.loads((self.vehicle / 'vehicle.toml').read_text())
        self.out = Path(a.out).resolve()
        self.out.mkdir(parents=True, exist_ok=False)
        self.events = []
        self.procs = []
        self.t0 = time.monotonic()

    def event(self, what, **data):
        row = {'wall_s': round(time.monotonic() - self.t0, 2), 'event': what, **data}
        self.events.append(row)
        print(json.dumps(row), flush=True)

    def start(self):
        i = self.a.instance
        sim = [str(Path(self.a.simhost).resolve()), '--vehicle', str(self.vehicle), '--sitl-port', str(4560 + i), '--lockstep',
               '--record', str(self.out / 'simhost.csv'), '--agl', str(self.toml['start']['agl_m']),
               '--heading', str(self.toml['start']['heading_deg'])]
        sim += simhost_vehicle_args(self.toml, self.a.config, self.a.at)
        self.procs.append(subprocess.Popen(sim, stdout=subprocess.DEVNULL, stderr=open(self.out / 'simhost.log', 'w')))
        build = Path(self.a.px4_build).resolve()
        work = self.out / 'px4'
        work.mkdir()
        env = dict(os.environ, PX4_SYS_AUTOSTART=str(self.toml['px4']['sitl']['airframe']))
        env.pop('PX4_SIM_MODEL', None)
        px4 = [str(build / 'bin/px4'), '-d', '-i', str(i), '-w', str(work), str(build / 'etc')]
        self.procs.append(subprocess.Popen(px4, cwd=work, env=env, stdin=subprocess.DEVNULL, stdout=open(self.out / 'px4.log', 'w'),
                                           stderr=subprocess.STDOUT))
        self.event('started', simhost=' '.join(sim), px4=' '.join(px4), airframe=env['PX4_SYS_AUTOSTART'])
        self.m = mavutil.mavlink_connection(f'udpin:127.0.0.1:{14540 + i}', source_system=254, source_component=190)
        hb = self.m.wait_heartbeat(timeout=120)
        if hb is None:
            raise RuntimeError('no heartbeat from PX4')
        self.event('heartbeat', system=self.m.target_system, autopilot=hb.autopilot, type=hb.type)

    def drain(self, seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            msg = self.m.recv_match(blocking=True, timeout=0.2)
            if msg is not None and msg.get_type() == 'STATUSTEXT':
                self.event('px4', text=msg.text)

    def read_param(self, name):
        # PX4 sends integer parameters bytewise: the int32 bits travel in the float field.
        self.m.mav.param_request_read_send(self.m.target_system, self.m.target_component, name.encode(), -1)
        end = time.monotonic() + 3
        while time.monotonic() < end:
            msg = self.m.recv_match(type='PARAM_VALUE', blocking=True, timeout=0.5)
            if msg is not None and msg.param_id == name:
                return decode_param(msg.param_value, msg.param_type), msg.param_type
        return None, None

    def set_params(self):
        wanted = {}
        for line in (self.vehicle / self.toml['px4']['sitl']['params']).read_text().splitlines():
            line = line.split('#')[0].strip()
            if line:
                k, v = line.split()
                wanted[k] = float(v)
        got = {}
        for k, v in wanted.items():
            _, ptype = self.read_param(k)
            if ptype is None:
                continue
            for _ in range(3):
                self.m.mav.param_set_send(self.m.target_system, self.m.target_component, k.encode(), encode_param(v, ptype), ptype)
                value, _ = self.read_param(k)
                if value is not None and abs(value - v) <= 1e-4 * max(1.0, abs(v)):
                    got[k] = value
                    break
                got[k] = value
        bad = {k: (wanted[k], got.get(k)) for k in wanted if got.get(k) is None or abs(got[k] - wanted[k]) > 1e-4 * max(1, abs(wanted[k]))}
        self.event('params', count=len(wanted), read_back_mismatch=bad)
        if bad:
            raise RuntimeError(f'parameters not read back: {bad}')

    def command(self, cmd, *params, wait=5.0):
        p = list(params) + [0.0] * (7 - len(params))
        self.m.mav.command_long_send(self.m.target_system, self.m.target_component, cmd, 0, *p)
        end = time.monotonic() + wait
        while time.monotonic() < end:
            msg = self.m.recv_match(blocking=True, timeout=0.2)
            if msg is None:
                continue
            if msg.get_type() == 'STATUSTEXT':
                self.event('px4', text=msg.text)
            if msg.get_type() == 'COMMAND_ACK' and msg.command == cmd:
                return msg.result
        return None

    def wait_position(self, timeout=180.0):
        """Arm only with a usable global position: the estimator reports an absolute horizontal position and PX4 has a
        home position. (PX4 may accept arming earlier; COM_ARM_WO_GPS 1 allows it. A takeoff without GPS then fails
        over when it switches to a mode that needs a global position.)"""
        end = time.monotonic() + timeout
        have_home, have_pos, since = False, False, None
        while time.monotonic() < end:
            if not have_home:
                self.m.mav.command_long_send(self.m.target_system, self.m.target_component, mavutil.mavlink.MAV_CMD_REQUEST_MESSAGE, 0,
                                             mavutil.mavlink.MAVLINK_MSG_ID_HOME_POSITION, 0, 0, 0, 0, 0, 0)
            msg = self.m.recv_match(type=['HOME_POSITION', 'EKF_STATUS_REPORT', 'ESTIMATOR_STATUS', 'STATUSTEXT'], blocking=True, timeout=1.0)
            if msg is None:
                continue
            t = msg.get_type()
            if t == 'STATUSTEXT':
                self.event('px4', text=msg.text)
            elif t == 'HOME_POSITION':
                have_home = True
            elif t in ('EKF_STATUS_REPORT', 'ESTIMATOR_STATUS'):
                ok = bool(msg.flags & mavutil.mavlink.EKF_POS_HORIZ_ABS)
                if ok and not have_pos:
                    since = time.monotonic()
                have_pos = ok
            if have_home and have_pos and since is not None and time.monotonic() - since > 2.0:
                self.event('position ready', home=True, ekf_pos_horiz_abs=True)
                return
        raise RuntimeError('no global position and home before the timeout')

    def fly(self):
        self.wait_position()
        # Wait for the estimator: try to switch to takeoff and arm until PX4 accepts (pre-arm checks pass).
        end = time.monotonic() + 180
        while True:
            if time.monotonic() > end:
                raise RuntimeError('PX4 never accepted arming')
            self.drain(2.0)
            r1 = self.command(mavutil.mavlink.MAV_CMD_DO_SET_MODE, mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED, AUTO, AUTO_TAKEOFF)
            r2 = self.command(mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 1)
            self.event('arm attempt', mode_ack=r1, arm_ack=r2)
            if r2 == mavutil.mavlink.MAV_RESULT_ACCEPTED:
                break
        self.event('armed')
        took_off, loiter_from = None, None
        end = time.monotonic() + self.a.timeout
        last = {}
        while time.monotonic() < end:
            msg = self.m.recv_match(blocking=True, timeout=0.5)
            if msg is None:
                continue
            t = msg.get_type()
            if t == 'STATUSTEXT':
                self.event('px4', text=msg.text)
            elif t == 'GLOBAL_POSITION_INT':
                last['rel_alt_m'] = msg.relative_alt / 1000.0
                last['time_boot_s'] = msg.time_boot_ms / 1000.0
            elif t == 'VFR_HUD':
                last['airspeed_m_s'] = msg.airspeed
                last['throttle_pct'] = msg.throttle
            elif t == 'HEARTBEAT' and msg.get_srcSystem() == self.m.target_system:
                main_mode = (msg.custom_mode >> 16) & 0xFF
                sub_mode = (msg.custom_mode >> 24) & 0xFF
                last['mode'] = (main_mode, sub_mode)
                last['armed'] = bool(msg.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED)
                if took_off is None and last.get('rel_alt_m', 0) > 5:
                    took_off = last.get('time_boot_s')
                    self.event('airborne', **last)
                if loiter_from is None and took_off is not None and (main_mode, sub_mode) == (AUTO, AUTO_LOITER):
                    loiter_from = last.get('time_boot_s')
                    self.event('loiter', **last)
                if loiter_from is not None and last.get('time_boot_s', 0) - loiter_from >= self.a.loiter:
                    self.event('done', **last)
                    return {'took_off_s': took_off, 'loiter_from_s': loiter_from, 'last': last}
        raise RuntimeError(f'flight did not finish in {self.a.timeout} s wall: {last}')

    def stop(self):
        for p in reversed(self.procs):
            if p.poll() is None:
                p.send_signal(signal.SIGINT)
        for p in reversed(self.procs):
            try:
                p.wait(timeout=20)
            except subprocess.TimeoutExpired:
                p.kill()
        self.event('stopped', returncodes=[p.returncode for p in self.procs])


def summarize(out, flight):
    rows = []
    if not (out / 'simhost.csv').exists():
        return {'samples': 0, 'flight': flight, 'ulog': []}
    with open(out / 'simhost.csv') as f:
        head = f.readline().strip().split(',')
        for line in f:
            vals = line.strip().split(',')
            if len(vals) == len(head):
                rows.append(dict(zip(head, map(float, vals))))
    s = {'samples': len(rows), 'sim_s': rows[-1]['t_s'] if rows else 0}
    if rows:
        s['max_agl_m'] = round(max(r['agl_m'] for r in rows), 2)
        armed = [r for r in rows if r['armed'] > 0.5]
        if armed:
            air = [r for r in armed if r['on_ground'] < 0.5]
            s['first_airborne_s'] = round(air[0]['t_s'], 2) if air else None
            last60 = [r for r in rows if r['t_s'] >= rows[-1]['t_s'] - 60 and r['on_ground'] < 0.5]
            if last60:
                spd = [r['airspeed_m_s'] for r in last60]
                agl = [r['agl_m'] for r in last60]
                s['last_60s'] = {'airspeed_mean_m_s': round(sum(spd) / len(spd), 2), 'airspeed_min_m_s': round(min(spd), 2),
                                 'airspeed_max_m_s': round(max(spd), 2), 'agl_mean_m': round(sum(agl) / len(agl), 2),
                                 'agl_min_m': round(min(agl), 2), 'agl_max_m': round(max(agl), 2),
                                 'roll_abs_max_deg': round(max(abs(r['roll_deg']) for r in last60), 1),
                                 'alpha_mean_deg': round(sum(r['alpha_deg'] for r in last60) / len(last60), 2),
                                 'throttle_mean': round(sum(r['throttle'] for r in last60) / len(last60), 3)}
    s['flight'] = flight
    s['ulog'] = [str(p.relative_to(out)) for p in sorted((out / 'px4').rglob('*.ulg'))]
    return s


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--vehicle', required=True)
    p.add_argument('--px4-build', required=True)
    p.add_argument('--simhost', required=True)
    p.add_argument('--out', required=True)
    p.add_argument('--instance', type=int, default=9)
    p.add_argument('--loiter', type=float, default=60.0, help='seconds of PX4 time in loiter after the takeoff')
    p.add_argument('--timeout', type=float, default=600.0, help='wall seconds for the whole flight')
    p.add_argument('--config', action='append', default=[], help='vehicle configuration file (TOML [set]); repeatable')
    p.add_argument('--at', action='append', default=[], metavar='T:PROPERTY=VALUE',
                   help='set a JSBSim property at simulated time T, e.g. an actuator failure; repeatable')
    a = p.parse_args()
    f = Flight(a)
    result, error = None, None
    try:
        f.start()
        f.drain(5.0)
        f.set_params()
        result = f.fly()
    except Exception as exc:  # noqa: BLE001  (keep the evidence, report, fail)
        error = str(exc)
        f.event('error', error=error)
    finally:
        f.stop()
    summary = summarize(f.out, result)
    summary['verdict'] = 'FAIL' if error else 'PASS'
    summary['error'] = error
    (f.out / 'events.json').write_text(json.dumps(f.events, indent=1))
    (f.out / 'summary.json').write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary, indent=1))
    sys.exit(1 if error else 0)


if __name__ == '__main__':
    main()
