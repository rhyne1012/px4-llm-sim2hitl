#!/usr/bin/env python3
"""The pilot: a fixed-wing takeoff from a runway, flown like a person with sticks, then a command script.

    <python with pymavlink> tools/pilot.py takeoff --vehicle <folder> --relay-port 14600 --listen-port 14601 \
        --log-dir <run>/pilot [--after <command script.py>] [--climb-bank 30]
    <python with pymavlink> tools/pilot.py status --relay-port 14600 --listen-port 14601 --log-dir <run>/pilot
    <python with pymavlink> tools/pilot.py stop --log-dir <run>/pilot

  takeoff  fly: Stabilized, arm, takeoff throttle, pitch up at the rotate airspeed, climb to the altitude, level off
           with a slow altitude hold, then the --after script once the flight has been steady for a few seconds
  status   the flight state: the running pilot's status.json, or what the FC sends when no pilot runs
  stop     ask the running pilot (the same --log-dir) to let go of the sticks

The pilot is a MAVLink peer of simhost's relay (--relay-port); it binds --listen-port. In HITL there is no receiver, so
its sticks are PX4's RC: MANUAL_CONTROL, or RC_CHANNELS_OVERRIDE through the FC's own RC calibration when the script
says INPUT = 'rc'. Once flying, the sticks go on in every PX4 mode: frozen in OFFBOARD, level flight with altitude hold
in Stabilized, neutral otherwise, so PX4's RC-loss failsafe never replaces the behaviour under test.

It refuses unless the FC reads back SYS_HITL=1 and reports a fixed-wing that is disarmed on the ground. On the ground,
a stop or lost telemetry abandons the takeoff (sticks neutral, disarm); in the air it lets go of the sticks. A
ground station's sticks that reach this pilot's port and move also hand control back. No parameter is written.

The automation numbers come from the vehicle's vehicle.toml [pilot] table (--vehicle), each overridable on the command
line; the pilot refuses to fly without all of them. In lockstep, SIM2HITL_SIMCLOCK and SIM2HITL_PILOTSYNC name
simhost's --simclock and --pilot-sync files (tools/simclock.py). The contract with command scripts is docs/pilot.md.
"""
import argparse
import csv
import json
import math
import os
from pathlib import Path
import signal
import socket
import struct
import sys
import time
import tomllib

os.environ.setdefault('MAVLINK20', '1')
from pymavlink.dialects.v20 import common as mav  # noqa: E402

sys.path.insert(0, str(Path(__file__).resolve().parent))
import rc_output  # noqa: E402
import simclock  # noqa: E402
from sequence import load_script  # noqa: E402

STABILIZED, OFFBOARD = 7, 6           # PX4 custom main modes
SOURCE = (254, 190)                   # this pilot, as a second ground station
TARGET = (1, 1)                       # the FC
TAKEOVER_STICK = 150                  # ground-station stick movement (of 1000) that hands control back
BANK_FROM_M = 20                      # --climb-bank: height above which the climb banks
HOMEWARD_DEG = 45                     # --climb-bank: level off when the course is this close to the bearing home
HOME_NEAR_M = 150                     # --climb-bank: or when this close to the takeoff point, any course
PREARM_WAIT_S = 60.                   # arm: how long to wait for PX4's pre-arm checks to pass before asking
STOP = 'stop requested'
TAKEOVER = 'ground-station sticks moved: a person has control'
COMPLETE = 'command script complete'  # sequence.py, ON_FINISH 'release'

# The automation numbers: [pilot] key -> (help, accepted range). They belong to the vehicle; there are no defaults.
NUMBERS = {
    'takeoff_throttle': ('throttle of the ground roll and the climb, 0-1', lambda x: 0 < x <= 1),
    'cruise_throttle': ('throttle of level flight, 0-1', lambda x: 0 < x <= 1),
    'rotate_cas': ('m/s: pitch up from this calibrated airspeed, 5-30', lambda x: 5 <= x <= 30),
    'climb_pitch': ('deg of pitch in the climb, 0-25', lambda x: 0 < x <= 25),
    'altitude': ('m above the EKF origin, 20-500', lambda x: 20 <= x <= 500),
    'altitude_gain': ('deg of pitch per m of height error, > 0', lambda x: x > 0),
    'climb_damping': ('deg of pitch per m/s of climb rate, >= 0', lambda x: x >= 0),
    'rate': ('stick frames per second, 20-100', lambda x: 20 <= x <= 100),
}


def clamp(value, low, high):
    return max(low, min(high, value))


def text(value):
    if isinstance(value, (bytes, bytearray)):
        value = bytes(value).decode('ascii', 'replace')
    return value.rstrip('\0')


class Link:
    """UDP to simhost's relay; decodes what the FC sends."""

    def __init__(self, listen_port, relay_port):
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.bind(('127.0.0.1', listen_port))
        self.sock.setblocking(False)
        self.relay = ('127.0.0.1', relay_port)
        self.mav = mav.MAVLink(None, srcSystem=SOURCE[0], srcComponent=SOURCE[1])
        self.parser = mav.MAVLink(None)
        self.parser.robust_parsing = True

    def send(self, message):
        try:
            self.sock.sendto(message.pack(self.mav), self.relay)
        except ConnectionError:       # the relay port is not open (yet): ICMP refused
            pass

    def receive(self):
        messages = []
        for _ in range(256):
            try:
                raw = self.sock.recv(65536)
            except (BlockingIOError, ConnectionError):
                break
            try:
                messages += self.parser.parse_buffer(raw) or []
            except mav.MAVError:
                pass
        return messages

    def close(self):
        self.sock.close()


class Vehicle:
    """Latest telemetry, with arrival times so stale data is never used."""

    def __init__(self):
        self.mode = self.armed = self.vehicle_type = None
        self.sub_mode = None
        self.cas = self.height = self.climb = self.pitch = self.roll = math.nan
        self.north = self.east = self.v_north = self.v_east = math.nan   # m, m/s from the EKF origin
        self.seen = {}
        self.params = {}
        self.texts = []
        self.text_log = []            # (arrival time, text), for command scripts that react to PX4's messages
        self.mission_seq = None       # MISSION_CURRENT
        self.mission_requests = []    # MISSION_REQUEST(_INT) sequence numbers, consumed by a mission upload
        self.mission_ack = None       # (arrival time, MAV_MISSION_RESULT)
        self.pilot = None             # a ground station's sticks that reached this port: (x, y, z, r)
        self.prearm_ok = None         # SYS_STATUS: PX4's pre-arm checks pass (None: not reported)

    def update(self, message, now):
        kind = message.get_type()
        system = message.get_srcSystem()
        if kind == 'MANUAL_CONTROL' and system != TARGET[0]:
            self.pilot = (message.x, message.y, message.z, message.r)
            self.seen['pilot'] = now
            return
        if (system, message.get_srcComponent()) != TARGET:
            return
        if kind == 'HEARTBEAT':
            self.mode = (message.custom_mode >> 16) & 255
            self.sub_mode = (message.custom_mode >> 24) & 255
            self.armed = bool(message.base_mode & mav.MAV_MODE_FLAG_SAFETY_ARMED)
            self.vehicle_type = message.type
        elif kind == 'SYS_STATUS':
            bit = mav.MAV_SYS_STATUS_PREARM_CHECK
            if message.onboard_control_sensors_present & bit:
                self.prearm_ok = bool(message.onboard_control_sensors_health & bit)
        elif kind == 'VFR_HUD':
            self.cas = message.airspeed
        elif kind == 'LOCAL_POSITION_NED':
            self.height, self.climb = -message.z, -message.vz
            self.north, self.east, self.v_north, self.v_east = message.x, message.y, message.vx, message.vy
        elif kind == 'ATTITUDE':
            self.pitch, self.roll = math.degrees(message.pitch), math.degrees(message.roll)
        elif kind == 'PARAM_VALUE':
            value = message.param_value
            if message.param_type == mav.MAV_PARAM_TYPE_INT32:   # PX4 sends the int32 bytes in the float field
                value = struct.unpack('<i', struct.pack('<f', value))[0]
            self.params[text(message.param_id)] = value
            return
        elif kind == 'STATUSTEXT':
            self.texts = (self.texts + [text(message.text)])[-5:]
            self.text_log = (self.text_log + [(now, text(message.text))])[-500:]
            return
        elif kind == 'MISSION_CURRENT':
            self.mission_seq = message.seq
        elif kind in ('MISSION_REQUEST', 'MISSION_REQUEST_INT'):
            self.mission_requests.append(message.seq)
            return
        elif kind == 'MISSION_ACK':
            self.mission_ack = (now, message.type)
            return
        else:
            return
        self.seen[kind] = now

    def fresh(self, now):
        limits = dict(HEARTBEAT=3., VFR_HUD=1., LOCAL_POSITION_NED=1., ATTITUDE=1.)
        return (all(now - self.seen.get(kind, -math.inf) <= limit for kind, limit in limits.items())
                and all(math.isfinite(value) for value in (self.cas, self.height, self.climb, self.pitch, self.roll)))


def snapshot(vehicle, now, **extra):
    def number(value):
        return round(value, 2) if isinstance(value, float) and math.isfinite(value) else None
    return dict(time=time.strftime('%Y-%m-%d %H:%M:%S'), telemetry_fresh=vehicle.fresh(now),
                px4_mode=vehicle.mode, px4_sub_mode=vehicle.sub_mode, armed=vehicle.armed,
                cas_mps=number(vehicle.cas), height_m=number(vehicle.height), climb_mps=number(vehicle.climb),
                pitch_deg=number(vehicle.pitch), roll_deg=number(vehicle.roll), px4_messages=vehicle.texts, **extra)


def write_json(path, data):
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps(data, indent=2) + '\n')
    temporary.replace(path)


class Takeoff:
    """The flight. Command scripts get this object as `flight` (docs/pilot.md lists what they may use)."""

    def __init__(self, args, link, clock):
        self.a = args
        self.link = link
        self.clock = clock
        self.log_dir = args.log_dir
        self.vehicle = Vehicle()
        self.state = 'connect'
        self.since = clock.monotonic()
        self.reason = ''
        self.sticks = [0, 0, 0, 0]    # x pitch, y roll (-1000..1000), z throttle 0..1000, r yaw
        self.streaming = False
        self.pitch_command = 0.       # deg, positive nose up
        self.pitch_scale = math.nan   # FW_MAN_P_MAX, read back before arming
        self.roll_command = 0.        # deg, positive right wing down (--climb-bank)
        self.roll_scale = math.nan    # FW_MAN_R_MAX, read back before arming
        self.climb_bank = args.climb_bank
        self.levelled = False         # --climb-bank: the circle has ended
        self.pilot_reference = None
        self.next = dict(heartbeat=0., command=0., param=0., status=0., log=0., echo=0.)
        self.airborne = False
        self.stop = False
        self.stop_reason = STOP
        self.after_sequence = args.after_sequence
        self.after_ready_since = self.after_wait_started = None
        self.arm_asked = None         # pilot time of the first arm request
        self.climb_timed_out = False
        self.mode_command_id = mav.MAV_CMD_DO_SET_MODE
        self.rc_mode = getattr(args.after_sequence, 'input', 'manual') == 'rc'
        self.rc = None                # rc_output.RcOutput, built from the FC's RC parameters during the check
        self.rc_paused = False        # a make_script() script emulating receiver loss
        self.dt = 0.

    # --- helpers ---------------------------------------------------------------------------------------------------
    def go(self, state, reason=''):
        self.state, self.since, self.reason = state, self.clock.monotonic(), reason
        print(f'[{time.strftime("%H:%M:%S")}] {state}' + (f': {reason}' if reason else ''), flush=True)

    def command(self, command, *params):
        params = list(params) + [0] * (7 - len(params))
        self.link.send(mav.MAVLink_command_long_message(*TARGET, command, 0, *params))

    def request_param(self, name):
        self.link.send(mav.MAVLink_param_request_read_message(*TARGET, name.encode(), -1))

    def set_pitch(self, target, dt, rate=12.):
        self.pitch_command += clamp(target - self.pitch_command, -rate * dt, rate * dt)
        self.sticks[0] = int(round(-1000 * clamp(self.pitch_command / self.pitch_scale, -1, 1)))

    def set_throttle(self, target, dt, rate=.5):
        current = self.sticks[2] / 1000
        self.sticks[2] = int(round(1000 * (current + clamp(target - current, -rate * dt, rate * dt))))

    def set_roll(self, target, dt, rate=15.):
        self.roll_command += clamp(target - self.roll_command, -rate * dt, rate * dt)
        self.sticks[1] = int(round(1000 * clamp(self.roll_command / self.roll_scale, -1, 1)))

    def altitude_hold(self):
        a, v = self.a, self.vehicle
        return clamp(a.altitude_gain * (a.altitude - v.height) - a.climb_damping * v.climb, -8, 8)

    def homeward(self):
        """--climb-bank: settled near the altitude and heading back toward the takeoff point (the EKF origin)."""
        v = self.vehicle
        if not (self.a.altitude - 10 <= v.height <= self.a.altitude + 5 and abs(v.climb) <= 1.5):
            return False
        distance = math.hypot(v.north, v.east)
        off = math.remainder(math.atan2(-v.east, -v.north) - math.atan2(v.v_east, v.v_north), 2 * math.pi)
        return distance <= HOME_NEAR_M or abs(math.degrees(off)) <= HOMEWARD_DEG

    def build_rc(self, params):
        """Transmitter emulation from the FC's own maps and calibration; the arm switch ON from the first frame."""
        try:
            self.rc = rc_output.RcOutput(params)
            if 'mode' in self.rc.channel:
                self.rc.set_mode('STABILIZED')
        except ValueError as exc:
            self.release('RC emulation impossible: ' + str(exc))
            return False
        print('RC emulation channels: ' + ', '.join(f'{k}=ch{c}' for k, c in sorted(self.rc.channel.items())), flush=True)
        return True

    def hold_level(self, dt):
        """Wings level with the slow altitude hold of cruise (Stabilized); for command scripts as well."""
        self.sticks[1] = self.sticks[3] = 0
        self.roll_command = 0.
        self.set_throttle(self.a.cruise_throttle, dt)
        self.set_pitch(self.altitude_hold(), dt)

    def release(self, reason):
        self.streaming = False
        if self.after_sequence:
            self.after_sequence.cancel(reason)
        self.go('released', reason)

    def after_step(self, now):
        """Run the --after script once the climb has ended and the flight has been steady; True while it runs."""
        script, v, a = self.after_sequence, self.vehicle, self.a
        if not v.armed or script is None or script.state not in ('waiting', 'running'):
            return False
        if script.state == 'waiting':
            if self.after_wait_started is None:
                self.after_wait_started = now
            if self.climb_timed_out:
                script.state, script.reason = 'failed', 'climb timed out; command script not started'
                self.release(script.reason)
                return True
            ready = (self.streaming and v.fresh(now) and v.armed and v.mode == STABILIZED
                     and abs(v.height - a.altitude) <= 5 and a.rotate_cas <= v.cas <= 30
                     and abs(v.roll) <= 5 and abs(v.climb) <= 1.5 and -15 <= v.pitch <= 20)
            if not ready:
                self.after_ready_since = None
            elif self.after_ready_since is None:
                self.after_ready_since = now
            if ready and now - self.after_ready_since >= a.after_stable_seconds:
                script.begin()
                print('Command script started: ' + script.name, flush=True)
            elif now - self.after_wait_started >= a.after_timeout:
                script.state, script.reason = 'failed', 'command script readiness timed out'
                self.release(script.reason)
                return True
        if script.state == 'running':
            script.tick(self, now)
            return True
        return False

    # --- one control step ------------------------------------------------------------------------------------------
    def step(self, now, dt):
        v, a = self.vehicle, self.a
        self.dt = dt
        for message in self.link.receive():
            v.update(message, now)
        if now >= self.next['heartbeat']:
            self.next['heartbeat'] = now + 1
            self.link.send(mav.MAVLink_heartbeat_message(mav.MAV_TYPE_GCS, mav.MAV_AUTOPILOT_INVALID, 0, 0, 0, 3))
        elapsed = now - self.since
        on_ground = not self.airborne

        if self.stop and self.state not in ('released', 'abandon'):
            if self.streaming and on_ground and self.state in ('arm', 'roll'):
                self.go('abandon', self.stop_reason)
            else:
                self.release(self.stop_reason)
        elif self.streaming and self.pilot_takeover(now):
            self.release(TAKEOVER)
        elif self.streaming and not v.fresh(now):
            if on_ground and self.state in ('arm', 'roll'):
                self.go('abandon', 'telemetry lost')
            else:
                self.release('telemetry lost')

        elif self.state == 'connect':
            if v.fresh(now):
                self.go('check')
            elif elapsed > 15:
                self.release('no telemetry from the FC through the relay; is simhost running with --relay-port?')
        elif self.state == 'check':
            extra = rc_output.required_params(v.params) if self.rc_mode else []
            missing = [name for name in extra if name not in v.params]
            if now >= self.next['param']:
                self.next['param'] = now + .5
                self.request_param('SYS_HITL' if 'SYS_HITL' not in v.params else 'FW_MAN_P_MAX')
                if self.climb_bank and 'FW_MAN_R_MAX' not in v.params:
                    self.request_param('FW_MAN_R_MAX')
                for name in missing[:24]:
                    self.request_param(name)
            if 'SYS_HITL' in v.params and v.params['SYS_HITL'] != 1:
                self.release(f'SYS_HITL={v.params["SYS_HITL"]}: not a HIL flight controller, refusing')
            elif ('SYS_HITL' in v.params and 'FW_MAN_P_MAX' in v.params and not missing
                  and (not self.climb_bank or 'FW_MAN_R_MAX' in v.params)):
                self.pitch_scale = float(v.params['FW_MAN_P_MAX'])
                self.roll_scale = float(v.params.get('FW_MAN_R_MAX', math.nan))
                if not math.isfinite(self.pitch_scale) or self.pitch_scale <= 0:
                    self.release('FW_MAN_P_MAX must be finite and positive')
                elif self.climb_bank and not abs(self.climb_bank) <= self.roll_scale < math.inf:
                    self.release(f'--climb-bank {self.climb_bank} needs FW_MAN_R_MAX >= it (FC: {self.roll_scale})')
                elif v.vehicle_type != mav.MAV_TYPE_FIXED_WING:
                    self.release('the FC is not a fixed-wing: this pilot only takes off from a runway')
                elif v.armed or v.cas > 5 or abs(v.height) > 5:
                    self.release('not disarmed on the ground: the takeoff starts only from the ground')
                elif self.rc_mode and not self.build_rc(v.params):
                    pass  # build_rc released with the reason
                else:
                    self.streaming = True
                    self.go('mode')
            elif elapsed > (15 if self.rc_mode else 8):
                self.release('SYS_HITL / FW_MAN_P_MAX' + (' / RC parameters ' + ', '.join(missing[:6]) if missing else '')
                             + ' could not be read back')
        elif self.state == 'mode':
            if v.mode == STABILIZED and elapsed >= 1:      # the sticks are established before arming
                self.go('arm')
            elif now >= self.next['command']:
                self.next['command'] = now + 1
                self.command(mav.MAV_CMD_DO_SET_MODE, 1, STABILIZED)
            if elapsed > 8:
                self.release('PX4 did not enter Stabilized')
        elif self.state == 'arm':
            # Ask only once PX4 reports its pre-arm checks passed (SYS_STATUS PREARM_CHECK): before that the estimator
            # may still be aligning or waiting for GPS, and a refused arm says nothing more. Without the report, ask.
            waiting = v.prearm_ok is False and elapsed < PREARM_WAIT_S
            if v.armed:
                self.go('roll')
            elif not waiting and now >= self.next['command']:
                self.next['command'] = now + 1.5
                self.command(mav.MAV_CMD_COMPONENT_ARM_DISARM, 1)
                self.arm_asked = self.arm_asked or now
            if self.arm_asked and now - self.arm_asked > 10:
                self.go('abandon', 'PX4 did not arm: ' + ' | '.join(v.texts[-2:]))
            elif elapsed > PREARM_WAIT_S + 10:
                self.go('abandon', f'PX4 pre-arm checks did not pass within {PREARM_WAIT_S:.0f} s: ' + ' | '.join(v.texts[-2:]))
        elif self.state == 'roll':
            self.set_throttle(a.takeoff_throttle, dt, rate=1.)
            if v.cas >= a.rotate_cas:
                self.go('climb')
            elif elapsed > 40:
                self.go('abandon', f'rotate airspeed not reached (CAS {v.cas:.1f} m/s)')
        elif self.state == 'climb':
            self.airborne = self.airborne or v.height > 3
            self.set_throttle(a.takeoff_throttle, dt)
            self.set_pitch(a.climb_pitch, dt, rate=30.)
            if self.climb_bank and v.height >= BANK_FROM_M:
                self.set_roll(self.climb_bank, dt)
            if v.height >= a.altitude - 2:
                self.go('cruise')
            elif elapsed > 180:
                self.climb_timed_out = True
                self.go('cruise', f'climb timed out at {v.height:.0f} m')
        elif self.state == 'cruise':
            if self.after_step(now):
                pass                                            # the command script owns the sticks for this tick
            elif v.mode != OFFBOARD:                            # sticks frozen while PX4 is in OFFBOARD
                self.set_throttle(a.cruise_throttle, dt)
                self.set_pitch(self.altitude_hold(), dt)
                if self.climb_bank and (not self.levelled or self.roll_command):
                    if not self.levelled and self.after_sequence and self.homeward():
                        self.levelled = True
                        print(f'Circle ended, wings level: {math.hypot(v.north, v.east):.0f} m from the takeoff '
                              f'point, heading back', flush=True)
                    self.set_roll(0. if self.levelled else self.climb_bank, dt)
        elif self.state == 'abandon':
            self.sticks = [0, 0, 0, 0]
            if now >= self.next['command'] and v.armed:
                self.next['command'] = now + 1
                self.command(mav.MAV_CMD_COMPONENT_ARM_DISARM, 0)
            if not v.armed or elapsed > 5:
                self.release(self.reason)

        script_running = bool(self.after_sequence and self.after_sequence.state == 'running')
        if self.state in ('roll', 'climb', 'cruise', 'loiter'):
            # These sticks are PX4's only RC in HITL: once flying (cruise, loiter) a mode change never stops them, or
            # PX4's RC-loss failsafe (NAV_RCL_ACT) would replace what PX4 or a module chose. Frozen in OFFBOARD,
            # level flight with altitude hold in Stabilized, neutral in every other mode. A stop, a ground station's
            # sticks, lost telemetry, a disarm or a failed command script hand back. During the takeoff (roll, climb)
            # leaving Stabilized hands back too.
            if not v.armed:
                self.release('PX4 disarmed')
            elif self.state == 'loiter' and v.mode == STABILIZED:
                self.go('cruise', 'PX4 in Stabilized: level flight with altitude hold')
            elif self.state == 'loiter':
                pass                                            # neutral input keepalive in any other mode
            elif self.state == 'cruise' and v.mode not in (STABILIZED, OFFBOARD) and not script_running:
                self.sticks[:] = [0, 0, round(1000 * a.cruise_throttle), 0]
                self.pitch_command = self.roll_command = 0.
                self.go('loiter', f'PX4 mode {v.mode}/{v.sub_mode} from cruise: neutral input keepalive')
            elif self.state in ('roll', 'climb') and v.mode not in (STABILIZED, OFFBOARD) and not script_running:
                self.release(f'PX4 left Stabilized (mode {v.mode})')
        if self.streaming and not self.transmitter_off():
            if self.rc is not None:
                self.rc.sticks = list(self.sticks)
                self.link.send(mav.MAVLink_rc_channels_override_message(*TARGET, *self.rc.values()))
            else:
                self.link.send(mav.MAVLink_manual_control_message(TARGET[0], *self.sticks, 0))
        self.report(now)

    def transmitter_off(self):
        """Receiver loss emulated by the command script: rc_paused (a make_script() script), or a running sequence
        between RcOff and RcOn. No stick frames then; heartbeats and mode requests go on."""
        script = self.after_sequence
        return self.rc_paused or bool(script and script.state == 'running' and getattr(script, 'rc_off', False))

    def pilot_takeover(self, now):
        v = self.vehicle
        if v.pilot is None or now - v.seen.get('pilot', -math.inf) > .5:
            self.pilot_reference = None
            return False
        if self.pilot_reference is None:
            self.pilot_reference = v.pilot
        return any(abs(p - r) > TAKEOVER_STICK for p, r in zip(v.pilot, self.pilot_reference))

    def report(self, now):
        v = self.vehicle
        throttle = self.sticks[2] / 1000
        script = self.after_sequence
        if now >= self.next['status']:
            self.next['status'] = now + .5
            write_json(self.log_dir / 'status.json', snapshot(
                v, now, source='pilot', state=self.state, reason=self.reason, pid=os.getpid(),
                clock='simulated' if self.clock.simulated else 'wall', clock_s=round(now, 3),
                script_has_sticks=self.streaming, throttle_percent=round(100 * throttle, 1),
                pitch_command_deg=round(self.pitch_command, 2), pilot_numbers=self.a.numbers,
                after_script=script.name if script else None,
                after_state=script.state if script else 'disabled',
                after_step=script.index if script else None,
                after_reason=script.reason if script else '',
                after_ready_stable_s=round(now - self.after_ready_since, 1) if self.after_ready_since is not None else 0.,
                rc_override=self.rc is not None, rc_paused=self.transmitter_off(),
                rc_switches=dict(self.rc.switch, mode=self.rc.mode) if self.rc is not None else None,
                ground_station_sticks_seen=v.pilot is not None and now - v.seen.get('pilot', -math.inf) < .5))
        if now >= self.next['log']:
            self.next['log'] = now + .1
            self.log.writerow([f'{now - self.start:.2f}', self.state, v.mode, int(bool(v.armed)),
                               *(f'{x:.3f}' for x in (v.cas, v.height, v.climb, v.pitch, v.roll)),
                               *self.sticks, int(self.streaming)])
        if now >= self.next['echo']:
            self.next['echo'] = now + 2
            print(f'  {self.state:8s} mode={v.mode} armed={v.armed} CAS={v.cas:5.1f} h={v.height:6.1f} '
                  f'climb={v.climb:5.1f} pitch={v.pitch:5.1f} roll={v.roll:5.1f} thr={100 * throttle:3.0f}%', flush=True)

    def run(self):
        stop_file = self.log_dir / 'stop'
        stop_file.unlink(missing_ok=True)
        self.start = last = self.clock.monotonic()
        period = 1 / self.a.rate
        with (self.log_dir / f'pilot_{time.strftime("%Y%m%d_%H%M%S")}.csv').open('w', newline='') as f:
            self.log = csv.writer(f)
            self.log.writerow(['t_s', 'state', 'px4_mode', 'armed', 'cas_mps', 'height_m', 'climb_mps',
                               'pitch_deg', 'roll_deg', 'stick_x', 'stick_y', 'stick_z', 'stick_r', 'script_has_sticks'])
            deadline = self.start
            while self.state != 'released':
                now = self.clock.monotonic()
                self.stop = self.stop or stop_file.exists()
                self.step(now, clamp(now - last, 0, .1))
                last = now
                deadline = max(deadline + period, now - period)
                self.clock.allow(deadline)   # lockstep: the simulation may run up to this step's wake-up, not past it
                self.clock.sleep(max(0, deadline - self.clock.monotonic()))
            self.next.update(status=0., log=0., echo=0.)        # the final status and log line
            self.report(self.clock.monotonic())
        print('Sticks released: ' + self.reason, flush=True)
        return 0 if self.reason in (STOP, TAKEOVER, COMPLETE) else 2


def status(args):
    clock = simclock.from_env(sync=False)   # only the flying pilot gates the simulation
    try:
        link = Link(args.listen_port, args.relay_port)
    except OSError:                          # the port is held by a running pilot: use what it publishes
        path = args.log_dir / 'status.json'
        if not path.exists() or time.time() - path.stat().st_mtime > 3:
            print(json.dumps(dict(error=f'port {args.listen_port} busy and no fresh {path}')))
            return 2
        print(path.read_text(), end='')
        return 0
    vehicle = Vehicle()
    end, beat = clock.monotonic() + args.listen, -math.inf
    while clock.monotonic() < end:
        now = clock.monotonic()
        if now - beat >= 1:                  # the relay sends only to peers it has heard from
            beat = now
            link.send(mav.MAVLink_heartbeat_message(mav.MAV_TYPE_GCS, mav.MAV_AUTOPILOT_INVALID, 0, 0, 0, 3))
        for message in link.receive():
            vehicle.update(message, now)
        clock.sleep(.02)
    link.close()
    now = clock.monotonic()
    print(json.dumps(snapshot(vehicle, now, source='listen_only', state='no pilot running'), indent=2))
    return 0 if vehicle.fresh(now) else 2


def pilot_numbers(args):
    """The automation numbers: the command line over the vehicle's [pilot] table; {name: value}, {name: source}."""
    table, where = {}, None
    if args.vehicle:
        where = Path(args.vehicle).expanduser().resolve() / 'vehicle.toml'
        table = tomllib.loads(where.read_text()).get('pilot', {})
        unknown = sorted(set(table) - set(NUMBERS))
        if unknown:
            raise ValueError(f'{where} [pilot]: unknown keys {", ".join(unknown)}')
    values, sources = {}, {}
    for name, (_, accepted) in NUMBERS.items():
        given = getattr(args, name)
        if given is not None:
            values[name], sources[name] = given, 'command line'
        elif name in table:
            values[name], sources[name] = table[name], f'{where} [pilot]'
        else:
            continue
        value = values[name]
        if not (isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value)
                and accepted(value)):
            raise ValueError(f'{name} = {value!r} ({sources[name]}): {NUMBERS[name][0]}')
    missing = [name for name in NUMBERS if name not in values]
    if missing:
        raise ValueError('missing automation numbers: ' + ', '.join(missing) + ' (the vehicle.toml [pilot] table of '
                         '--vehicle, or --' + ' / --'.join(m.replace('_', '-') for m in missing) + ')')
    return {name: float(value) for name, value in values.items()}, sources


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('action', choices=['takeoff', 'status', 'stop'])
    p.add_argument('--log-dir', type=Path, required=True, help='status.json, the stop file and the flight log')
    p.add_argument('--relay-port', type=int, help="simhost's --relay-port (takeoff, status)")
    p.add_argument('--listen-port', type=int, help="this pilot's own UDP port (takeoff, status)")
    p.add_argument('--vehicle', help='vehicle folder whose vehicle.toml has the [pilot] table (takeoff)')
    for name, (text_, _) in NUMBERS.items():
        p.add_argument('--' + name.replace('_', '-'), type=float, help=f'[pilot] {name}: {text_}')
    p.add_argument('--climb-bank', type=float, default=0., help='deg, positive right: climb and wait for --after in '
                   f'a banked circle from {BANK_FROM_M} m, level off heading home; 0 climbs straight')
    p.add_argument('--after', type=Path, metavar='SCRIPT', help='command script (.py) to run after a steady takeoff')
    p.add_argument('--after-stable-seconds', type=float, default=3., help='steady time before the script starts')
    p.add_argument('--after-timeout', type=float, default=60., help='longest wait for that steady time')
    p.add_argument('--listen', type=float, default=2.5, help='status: seconds to listen when no pilot runs')
    args = p.parse_args()
    args.log_dir = args.log_dir.expanduser().resolve()
    if args.action == 'stop':
        args.log_dir.mkdir(parents=True, exist_ok=True)
        (args.log_dir / 'stop').touch()
        print('Stop requested')
        return 0
    if args.relay_port is None or args.listen_port is None:
        p.error(f'{args.action} needs --relay-port and --listen-port')
    if not (1 <= args.relay_port <= 65535 and 1 <= args.listen_port <= 65535 and args.relay_port != args.listen_port):
        p.error('--relay-port and --listen-port must be distinct and in 1..65535')
    if args.action == 'status':
        if not (math.isfinite(args.listen) and args.listen > 0):
            p.error('--listen must be finite and positive')
        try:
            return status(args)
        except RuntimeError as exc:          # a clock file named but missing
            p.error(str(exc))
    if not all(math.isfinite(x) and x > 0 for x in (args.after_stable_seconds, args.after_timeout)):
        p.error('--after-stable-seconds and --after-timeout must be finite and positive')
    if args.after_timeout < args.after_stable_seconds:
        p.error('--after-timeout must be at least --after-stable-seconds')
    if not (math.isfinite(args.climb_bank) and abs(args.climb_bank) <= 35):
        p.error('--climb-bank must be within +-35 deg')
    try:
        numbers, sources = pilot_numbers(args)
    except (OSError, ValueError, tomllib.TOMLDecodeError) as exc:
        p.error(str(exc))
    vars(args).update(numbers)
    args.numbers = {name: dict(value=numbers[name], source=sources[name]) for name in NUMBERS}
    args.after_sequence = None
    if args.after:
        try:
            args.after_sequence = load_script(args.after)
        except Exception as exc:  # noqa: BLE001  (any error in a script refuses the flight before it starts)
            p.error(f'cannot load command script {args.after}: {type(exc).__name__}: {exc}')
    try:
        clock = simclock.from_env()
    except (OSError, RuntimeError) as exc:
        p.error(str(exc))
    args.log_dir.mkdir(parents=True, exist_ok=True)
    try:
        link = Link(args.listen_port, args.relay_port)
    except OSError as exc:
        print(f'Port {args.listen_port} unavailable ({exc}); another pilot or status is running', file=sys.stderr)
        return 2
    print('Pilot numbers: ' + ', '.join(f'{k}={v["value"]:g} ({v["source"]})' for k, v in args.numbers.items())
          + f'; climb_bank={args.climb_bank:g}; clock: {"simulated" if clock.simulated else "wall"}', flush=True)
    flight = Takeoff(args, link, clock)

    def interrupt(_signum, _frame):
        flight.stop = True
    signal.signal(signal.SIGINT, interrupt)
    signal.signal(signal.SIGTERM, interrupt)
    try:
        return flight.run()
    finally:
        link.close()


if __name__ == '__main__':
    raise SystemExit(main())
