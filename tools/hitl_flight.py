#!/usr/bin/env python3
"""Fly a vehicle in HITL on a real flight controller through simhost: identity, parameters, takeoff, loiter, recovery.

    <python with pymavlink> tools/hitl_flight.py --vehicle vehicles/testbird --serial /dev/serial/by-id/<the FC> \
        --simhost build/simhost/simhost --out <new folder> [--loiter 60]

Order:
  1. Identity and state on the serial port: heartbeat, AUTOPILOT_VERSION, disarmed (refuses when armed). All
     parameters are saved to fc_params_before.params.
  2. The vehicle's `[px4.hitl] params` are written, the flight controller reboots, and every value is read back.
  3. simhost takes the serial port in real time (HIL_SENSOR every 4 ms, HIL_GPS every 0.1 s) and relays every other
     MAVLink message to this script over UDP.
  4. Takeoff (AUTO.TAKEOFF), loiter, then recovery: force-disarm while the simulation still runs (HITL drives no real
     outputs), confirm disarmed, stop simhost.
Use the /dev/serial/by-id/ path: after a reboot the flight controller can come back as another /dev/ttyACM number.
The propellers must be off and the ESCs unpowered (AGENTS.md); this script cannot check that.
"""
import argparse
import json
import signal
import subprocess
import sys
import time
import tomllib
from pathlib import Path

from pymavlink import mavutil

sys.path.insert(0, str(Path(__file__).resolve().parent))
from sitl_flight import AUTO, AUTO_LOITER, AUTO_TAKEOFF, decode_param, encode_param, summarize  # noqa: E402

FORCE_DISARM = 21196


class Hitl:
    def __init__(self, a):
        self.a = a
        self.vehicle = Path(a.vehicle).resolve()
        self.toml = tomllib.loads((self.vehicle / 'vehicle.toml').read_text())
        self.out = Path(a.out).resolve()
        self.out.mkdir(parents=True, exist_ok=False)
        self.events, self.procs = [], []
        self.t0 = time.monotonic()

    def event(self, what, **data):
        row = {'wall_s': round(time.monotonic() - self.t0, 2), 'event': what, **data}
        self.events.append(row)
        print(json.dumps(row), flush=True)

    # --- direct serial (before simhost owns the port) ---
    def serial(self):
        for _ in range(60):
            try:
                m = mavutil.mavlink_connection(self.a.serial, baud=self.a.baud, source_system=254, source_component=190)
                if m.wait_heartbeat(timeout=5):
                    return m
                m.close()
            except Exception:  # noqa: BLE001  (port not back yet after a reboot)
                pass
            time.sleep(1)
        raise RuntimeError(f'no heartbeat on {self.a.serial}')

    def identity(self, m, tag):
        m.mav.command_long_send(m.target_system, m.target_component, mavutil.mavlink.MAV_CMD_REQUEST_MESSAGE, 0,
                                mavutil.mavlink.MAVLINK_MSG_ID_AUTOPILOT_VERSION, 0, 0, 0, 0, 0, 0)
        v = m.recv_match(type='AUTOPILOT_VERSION', blocking=True, timeout=5)
        hb = m.recv_match(type='HEARTBEAT', blocking=True, timeout=3)
        sw = v.flight_sw_version if v else 0
        ident = {'flight_sw': f'{sw >> 24 & 255}.{sw >> 16 & 255}.{sw >> 8 & 255}', 'px4_git': bytes(v.flight_custom_version[::-1]).hex() if v else None,
                 'os_git': bytes(v.os_custom_version[::-1]).hex() if v else None, 'board_version': v.board_version if v else None,
                 'uid': v.uid if v else None, 'armed': bool(hb.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED) if hb else None}
        self.event('identity ' + tag, **ident)
        if ident['armed'] is not False:
            raise RuntimeError('flight controller is armed or silent; refusing')
        return ident

    def read_all(self, m):
        m.mav.param_request_list_send(m.target_system, m.target_component)
        params, total, last = {}, None, time.monotonic()
        while time.monotonic() - last < 3.0:
            p = m.recv_match(type='PARAM_VALUE', blocking=True, timeout=0.5)
            if p is None:
                continue
            last = time.monotonic()
            total = p.param_count
            params[p.param_id] = (decode_param(p.param_value, p.param_type), p.param_type)
            if total and len(params) >= total:
                break
        return params, total

    def read_param(self, m, name):
        for _ in range(3):
            m.mav.param_request_read_send(m.target_system, m.target_component, name.encode(), -1)
            end = time.monotonic() + 2
            while time.monotonic() < end:
                p = m.recv_match(type='PARAM_VALUE', blocking=True, timeout=0.5)
                if p is not None and p.param_id == name:
                    return decode_param(p.param_value, p.param_type), p.param_type
        return None, None

    def wanted(self):
        out = {}
        for line in (self.vehicle / self.toml['px4']['hitl']['params']).read_text().splitlines():
            line = line.split('#')[0].strip()
            if line:
                k, v = line.split()
                out[k] = float(v)
        return out

    def prepare(self):
        m = self.serial()
        self.ident_before = self.identity(m, 'before')
        params, total = self.read_all(m)
        with open(self.out / 'fc_params_before.params', 'w') as f:
            for k in sorted(params):
                f.write(f'{k}\t{params[k][0]:.9g}\n')
        self.event('saved parameters', count=len(params), reported=total)
        changed = {}
        for k, v in self.wanted().items():
            old, ptype = params.get(k, (None, None))
            if ptype is None:
                old, ptype = self.read_param(m, k)
            if ptype is None:
                raise RuntimeError(f'parameter {k} not on the flight controller')
            if old is not None and abs(old - v) <= 1e-6 * max(1, abs(v)):
                continue
            # One at a time: send, then wait for the flight controller's PARAM_VALUE carrying the new value.
            for _ in range(5):
                m.mav.param_set_send(m.target_system, m.target_component, k.encode(), encode_param(v, ptype), ptype)
                end, now_value = time.monotonic() + 1.5, None
                while time.monotonic() < end:
                    pv = m.recv_match(type='PARAM_VALUE', blocking=True, timeout=0.3)
                    if pv is not None and pv.param_id == k:
                        now_value = decode_param(pv.param_value, pv.param_type)
                        break
                if now_value is not None and abs(now_value - v) <= 1e-4 * max(1, abs(v)):
                    break
            changed[k] = {'from': old, 'to': v, 'echo': now_value}
        self.event('parameters written', changed=changed)
        (self.out / 'parameters_changed.json').write_text(json.dumps(changed, indent=1))
        # Save to storage explicitly and give PX4 time to finish before the reboot.
        m.mav.command_long_send(m.target_system, m.target_component, mavutil.mavlink.MAV_CMD_PREFLIGHT_STORAGE, 0, 1, 0, 0, 0, 0, 0, 0)
        ack = m.recv_match(type='COMMAND_ACK', blocking=True, timeout=3)
        self.event('parameters stored', ack=ack.result if ack else None)
        time.sleep(3)
        m.mav.command_long_send(m.target_system, m.target_component, mavutil.mavlink.MAV_CMD_PREFLIGHT_REBOOT_SHUTDOWN, 0, 1, 0, 0, 0, 0, 0, 0)
        self.event('reboot requested')
        m.close()
        time.sleep(5)
        m = self.serial()
        self.identity(m, 'after reboot')
        bad = {}
        for k, v in self.wanted().items():
            got, _ = self.read_param(m, k)
            if got is None or abs(got - v) > 1e-4 * max(1, abs(v)):
                bad[k] = (v, got)
        self.event('parameters read back', count=len(self.wanted()), mismatch=bad)
        m.close()
        if bad:
            raise RuntimeError(f'parameters not read back: {bad}')

    # --- through simhost ---
    def start_simhost(self):
        sim = [str(Path(self.a.simhost).resolve()), '--vehicle', str(self.vehicle), '--serial', self.a.serial, '--baud', str(self.a.baud),
               '--relay-port', str(self.a.relay_port), '--record', str(self.out / 'simhost.csv'),
               '--agl', str(self.toml['start']['agl_m']), '--heading', str(self.toml['start']['heading_deg'])]
        for mp in self.toml['actuators']:
            sim += ['--actuator', f"{mp['channel']}:{mp['property']}:{mp['gain']}:{mp.get('offset', 0.0)}"]
        self.procs.append(subprocess.Popen(sim, stdout=subprocess.DEVNULL, stderr=open(self.out / 'simhost.log', 'w')))
        self.event('simhost started', cmd=' '.join(sim))
        time.sleep(2)
        self.m = mavutil.mavlink_connection(f'udpout:127.0.0.1:{self.a.relay_port}', source_system=254, source_component=190)
        for _ in range(20):
            self.m.mav.heartbeat_send(mavutil.mavlink.MAV_TYPE_GCS, mavutil.mavlink.MAV_AUTOPILOT_INVALID, 0, 0, 0)
            if self.m.wait_heartbeat(timeout=1):
                break
        else:
            raise RuntimeError('no heartbeat through the relay')
        self.event('relay connected', system=self.m.target_system)

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
        end = time.monotonic() + 240
        while True:
            if time.monotonic() > end:
                raise RuntimeError('PX4 never accepted arming')
            self.m.mav.heartbeat_send(mavutil.mavlink.MAV_TYPE_GCS, mavutil.mavlink.MAV_AUTOPILOT_INVALID, 0, 0, 0)
            r1 = self.command(mavutil.mavlink.MAV_CMD_DO_SET_MODE, mavutil.mavlink.MAV_MODE_FLAG_CUSTOM_MODE_ENABLED, AUTO, AUTO_TAKEOFF)
            r2 = self.command(mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 1)
            self.event('arm attempt', mode_ack=r1, arm_ack=r2)
            if r2 == mavutil.mavlink.MAV_RESULT_ACCEPTED:
                break
            time.sleep(3)
        self.event('armed')
        took_off, loiter_from, last = None, None, {}
        end = time.monotonic() + self.a.timeout
        next_hb = 0
        while time.monotonic() < end:
            if time.monotonic() > next_hb:
                self.m.mav.heartbeat_send(mavutil.mavlink.MAV_TYPE_GCS, mavutil.mavlink.MAV_AUTOPILOT_INVALID, 0, 0, 0)
                next_hb = time.monotonic() + 1
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
                last['airspeed_m_s'] = round(msg.airspeed, 2)
                last['throttle_pct'] = msg.throttle
            elif t == 'HEARTBEAT' and msg.get_srcSystem() == self.m.target_system and msg.get_srcComponent() == 1:
                mode = ((msg.custom_mode >> 16) & 0xFF, (msg.custom_mode >> 24) & 0xFF)
                last['mode'] = mode
                if took_off is None and last.get('rel_alt_m', 0) > 5:
                    took_off = last.get('time_boot_s')
                    self.event('airborne', **last)
                if loiter_from is None and took_off is not None and mode == (AUTO, AUTO_LOITER):
                    loiter_from = last.get('time_boot_s')
                    self.event('loiter', **last)
                if loiter_from is not None and last.get('time_boot_s', 0) - loiter_from >= self.a.loiter:
                    self.event('done', **last)
                    return {'took_off_s': took_off, 'loiter_from_s': loiter_from, 'last': last}
        raise RuntimeError(f'flight did not finish in {self.a.timeout} s: {last}')

    def recover(self):
        # HITL drives no real outputs, so the flight controller is force-disarmed while the simulation still runs.
        ok = False
        for _ in range(5):
            r = self.command(mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0, FORCE_DISARM)
            hb = self.m.recv_match(type='HEARTBEAT', blocking=True, timeout=2)
            if hb is not None and not hb.base_mode & mavutil.mavlink.MAV_MODE_FLAG_SAFETY_ARMED:
                ok = True
                break
        self.event('recovery', disarm_ack=r, disarmed=ok)
        return ok

    def stop(self):
        for p in self.procs:
            if p.poll() is None:
                p.send_signal(signal.SIGINT)
        for p in self.procs:
            try:
                p.wait(timeout=20)
            except subprocess.TimeoutExpired:
                p.kill()
        tail = (self.out / 'simhost.log').read_text().strip().splitlines()[-1:] if (self.out / 'simhost.log').exists() else []
        self.event('simhost stopped', returncodes=[p.returncode for p in self.procs], last_line=tail)


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--vehicle', required=True)
    p.add_argument('--serial', required=True)
    p.add_argument('--baud', type=int, default=2000000)
    p.add_argument('--simhost', required=True)
    p.add_argument('--out', required=True)
    p.add_argument('--relay-port', type=int, default=14561)
    p.add_argument('--loiter', type=float, default=60.0)
    p.add_argument('--timeout', type=float, default=600.0)
    a = p.parse_args()
    h = Hitl(a)
    result, error, recovered = None, None, None
    try:
        h.prepare()
        h.start_simhost()
        result = h.fly()
    except Exception as exc:  # noqa: BLE001  (keep the evidence, recover, report)
        error = str(exc)
        h.event('error', error=error)
    finally:
        if getattr(h, 'm', None) is not None:
            try:
                recovered = h.recover()
            except Exception as exc:  # noqa: BLE001
                h.event('recovery error', error=str(exc))
        h.stop()
    summary = summarize(h.out, result)
    summary.update(verdict='FAIL' if error or recovered is False else 'PASS', error=error, recovered=recovered)
    (h.out / 'events.json').write_text(json.dumps(h.events, indent=1))
    (h.out / 'summary.json').write_text(json.dumps(summary, indent=1))
    print(json.dumps(summary, indent=1))
    sys.exit(0 if summary['verdict'] == 'PASS' else 1)


if __name__ == '__main__':
    main()
