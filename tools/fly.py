#!/usr/bin/env python3
"""Fly a deploy recipe of a vehicle repository: SITL (the recipe's SITL FC, lockstep) or HITL (the flight controller).

    <python with pymavlink> tools/fly.py sitl <recipe> --vehicle <vehicle folder> [--config C.toml]... --instance N
    <python with pymavlink> tools/fly.py hitl <recipe> --vehicle <vehicle folder> [--config C.toml]... \
        --link /dev/serial/by-id/<the FC> [--deploy reuse|flash|none]

The recipe's hitl.json says what to fly (docs/recipes.md): "after" (the command script), "check" (the program that
judges the flight's ULog), "climb_bank", "flight_timeout" (seconds of flight: wall time in HITL, simulated time
in SITL; 900 by default, plus 300 for the takeoff). The vehicle folder is simhost's (its vehicle.toml carries the
pilot's [pilot] numbers). Steps:

  1. The FC.
     SITL: tools/sitl_fc.py stop, then start (the recipe's parameters, boot file and logger topics are written at every
     start), so PX4's clock starts with simhost's.
     HITL: tools/deploy.py (--deploy reuse: the FC must already run the recipe's firmware; every parameter is read and
     checked, what differs is written, the FC rebooted and checked again). Then the FC is read on its own port:
     identity as the recipe's, disarmed, SYS_HITL 1, and the newest log before the flight.
  2. simhost: SITL on the instance's UDP links in lockstep with the simulated clock and the pilot's gate; HITL on the
     serial port in real time. Its MAVLink relay (SITL 14600+2N, HITL 14591) serves the pilot (14601+2N, HITL 14593)
     and this runner.
  3. The pilot (tools/pilot.py takeoff) with the command script. When the script reports complete or failed in the
     pilot's status.json, the pilot is told to stop; while simhost still runs, a force disarm (PX4 logs the disarm; a
     lockstep PX4 without sensor data would stand still); then simhost stops.
  4. HITL: the standard recover on the serial port (disarm, reboot, SYS_HITL 1 again), then the newest log, which must
     be newer than the newest before the flight. SITL: only a log file that appeared after simhost started counts.
  5. The check on that ULog: <python> -B <repo>/<check> <ulog> --out <check.json>, which writes {"verdict": ...}.

PASS needs the check's PASS, the pilot's exit 0 and the script's after_state complete. Everything lands in --out
(default ~/.cache/px4-llm-sim2hitl/v2/runs/<UTC>_<sitl|hitl>_<repo>_<recipe>/): events.json, summary.json, simhost.csv,
the pilot's folder, the FC log and the check.
"""
import argparse
import hashlib
import json
import os
import signal
import struct
import subprocess
import sys
import time
import tomllib
from pathlib import Path

TOOLKIT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLKIT / 'tools'))
from pymavlink import mavutil  # noqa: E402
from fc import FC, FORCE_DISARM  # noqa: E402
from recipe import Recipe  # noqa: E402
from sitl_flight import simhost_vehicle_args  # noqa: E402

CACHE = Path(os.environ.get('XDG_CACHE_HOME') or Path.home() / '.cache') / 'px4-llm-sim2hitl' / 'v2'
SIMHOST = TOOLKIT / 'build' / 'simhost' / 'simhost'


def ports(mode, instance):
    """(relay, pilot) UDP ports: HITL 14591/14593; SITL 14600+2N/14601+2N, so SITL instances can fly side by side."""
    return (14591, 14593) if mode == 'hitl' else (14600 + 2 * instance, 14601 + 2 * instance)


def git_state(path):
    head = subprocess.run(['git', '-C', str(path), 'rev-parse', 'HEAD'], capture_output=True, text=True).stdout.strip()
    dirty = subprocess.run(['git', '-C', str(path), 'status', '--porcelain'], capture_output=True, text=True).stdout.strip()
    return {'commit': head or None, 'dirty': bool(dirty)}


class Run:
    def __init__(self, a):
        self.a = a
        self.recipe = Recipe(a.recipe, a.repo)
        self.repo = self.recipe.repo
        self.hitl = self.recipe.hitl
        stamp = time.strftime('%Y%m%d-%H%M%S', time.gmtime())
        self.out = Path(a.out) if a.out else CACHE / 'runs' / f'{stamp}_{a.mode}_{self.repo.name}_{self.recipe.name}'
        self.out.mkdir(parents=True, exist_ok=bool(a.out))
        self.relay, self.pilot_port = ports(a.mode, a.instance)
        self.events, self.procs = [], {}
        self.t0 = time.monotonic()
        self.py = sys.executable
        self.newest_before = None
        self.logs_seen = set()

    def event(self, what, **data):
        row = {'wall_s': round(time.monotonic() - self.t0, 2), 'event': what, **data}
        self.events.append(row)
        print(json.dumps(row, default=str), flush=True)
        (self.out / 'events.json').write_text(json.dumps(self.events, indent=1, default=str) + '\n')

    def sh(self, cmd, timeout=1800, check=True, log=None):
        self.event('run', cmd=' '.join(map(str, cmd)))
        r = subprocess.run(list(map(str, cmd)), capture_output=True, text=True, timeout=timeout)
        if log:
            with open(self.out / log, 'a') as f:
                f.write(r.stdout + r.stderr)
        if check and r.returncode:
            raise RuntimeError(f'{Path(str(cmd[2] if len(cmd) > 2 else cmd[0])).name}: exit {r.returncode}: '
                               f'{(r.stdout + r.stderr).strip()[-600:]}')
        return r

    def last_json(self, r):
        lines = [x for x in r.stdout.splitlines() if x.startswith('{')]
        return json.loads(lines[-1]) if lines else {'exit_code': r.returncode, 'output': (r.stdout + r.stderr)[-400:]}

    def script(self):
        """The command script of hitl.json "after": a path in the repository, or a name in its commands folder
        (sim2hitl.lock "commands", default commands/)."""
        after = self.hitl.get('after')
        if not after:
            return None
        if after.endswith('.py'):
            return self.repo / after
        lock = self.repo / 'sim2hitl.lock'
        folder = (json.loads(lock.read_text()).get('commands') if lock.is_file() else None) or 'commands'
        path = self.repo / folder / f'{after}.py'
        if not path.is_file():
            raise RuntimeError(f'command script {after}: no {path}')
        return path

    # -- 1. the FC -----------------------------------------------------------------------------------------------------
    def sitl_fc(self, *words, check=True):
        r = self.sh([self.py, '-B', TOOLKIT / 'tools' / 'sitl_fc.py', *words], timeout=600, check=check, log='sitl_fc.log')
        return self.last_json(r)

    def sitl_logs(self):
        return set((CACHE / 'sitl_fc' / 'instances' / str(self.a.instance) / 'log').glob('*/*.ulg'))

    def prepare_sitl(self):
        self.sitl_fc('stop', '--instance', self.a.instance, check=False)
        start = ['start', '--recipe', self.recipe.dir, '--repo', self.repo, '--instance', self.a.instance]
        r = self.sh([self.py, '-B', TOOLKIT / 'tools' / 'sitl_fc.py', *start], timeout=600, check=False, log='sitl_fc.log')
        if r.returncode and ('no SITL FC build' in r.stderr + r.stdout or 'is stale' in r.stderr + r.stdout):
            self.event('sitl fc build', **self.sitl_fc('build', '--recipe', self.recipe.dir, '--repo', self.repo))
            r = self.sh([self.py, '-B', TOOLKIT / 'tools' / 'sitl_fc.py', *start], timeout=600, check=True, log='sitl_fc.log')
        elif r.returncode:
            raise RuntimeError(f'sitl_fc start: {(r.stdout + r.stderr).strip()[-600:]}')
        started = self.last_json(r)
        self.event('sitl fc started', **{k: v for k, v in started.items() if k != 'simhost'})
        self.logs_seen = self.sitl_logs()

    def prepare_hitl(self):
        if self.a.deploy != 'none':
            r = self.sh([self.py, '-B', TOOLKIT / 'tools' / 'deploy.py', self.recipe.dir, '--repo', self.repo,
                         '--link', self.a.link, '--' + self.a.deploy, *(['--reset-unmanaged'] if self.a.reset_unmanaged else [])],
                        timeout=3600, check=False, log='deploy.log')
            result = self.last_json(r)
            self.event('deploy', **result)
            if result.get('verdict') != 'PASS':
                raise RuntimeError(f'deploy {result.get("verdict")}: {result.get("error")}')
        fc = FC(self.a.link).connect()
        try:
            ident = fc.identity()
            hitl = fc.get('SYS_HITL')
            logs = fc.logs()
            self.newest_before = max(logs) if logs else -1
        finally:
            fc.close()
        e = self.recipe.firmware_info.get('embedded') or {}
        problems = []
        if ident.get('armed') is not False:
            problems.append('armed')
        if hitl != 1:
            problems.append(f'SYS_HITL {hitl}')
        if ident.get('git_hash_prefix') != e.get('git_hash', '')[:10] or \
                ident.get('board_version') != self.recipe.expected_board_version():
            problems.append(f'firmware {ident.get("git_hash_prefix")} board {ident.get("board_version")} is not the recipe\'s')
        self.event('fc before the flight', identity=ident, sys_hitl=hitl, newest_log=self.newest_before, problems=problems)
        if problems:
            raise RuntimeError('the FC is not ready: ' + '; '.join(problems))
        return {'identity': ident, 'sys_hitl': hitl, 'newest_log_before': self.newest_before}

    # -- 2. simhost ----------------------------------------------------------------------------------------------------
    def start_simhost(self):
        vehicle = Path(self.a.vehicle).resolve()
        toml = tomllib.loads((vehicle / 'vehicle.toml').read_text())
        xml = next((p for p in sorted(vehicle.glob('*.xml'))), None)
        self.event('vehicle', folder=str(vehicle), configs=self.a.config,
                   xml_sha256=hashlib.sha256(xml.read_bytes()).hexdigest() if xml else None)
        sim = [str(SIMHOST), '--vehicle', str(vehicle), '--relay-port', str(self.relay), '--record', str(self.out / 'simhost.csv')]
        env = dict(os.environ)
        if self.a.mode == 'sitl':
            n = self.a.instance
            self.simclock, self.pilot_sync = self.out / 'simclock', self.out / 'pilotsync'
            sim += ['--sitl-udp', f'{4560 + n}:{24740 + n}', '--mavlink-udp', f'{24540 + n}:{24640 + n}', '--lockstep',
                    '--simclock', str(self.simclock), '--pilot-sync', str(self.pilot_sync)]
        else:
            sim += ['--serial', self.a.link, '--baud', str(self.a.baud)]
        sim += simhost_vehicle_args(toml, [str(Path(c).resolve()) for c in self.a.config], self.a.at)
        self.procs['simhost'] = subprocess.Popen(sim, stdout=subprocess.DEVNULL, stderr=open(self.out / 'simhost.log', 'w'),
                                                 env=env)
        self.event('simhost started', cmd=' '.join(sim))

    def mavlink(self):
        m = mavutil.mavlink_connection(f'udpout:127.0.0.1:{self.relay}', source_system=254, source_component=191)
        for _ in range(60):
            if self.procs['simhost'].poll() is not None:
                raise RuntimeError('simhost stopped: ' + (self.out / 'simhost.log').read_text()[-400:])
            m.mav.heartbeat_send(mavutil.mavlink.MAV_TYPE_GCS, mavutil.mavlink.MAV_AUTOPILOT_INVALID, 0, 0, 0)
            hb = m.recv_match(type='HEARTBEAT', blocking=True, timeout=1)
            if hb is not None and hb.autopilot == mavutil.mavlink.MAV_AUTOPILOT_PX4:
                m.target_system, m.target_component = hb.get_srcSystem(), hb.get_srcComponent()
                self.event('fc heartbeat through the relay', base_mode=hb.base_mode, system_status=hb.system_status)
                return m
        raise RuntimeError('no heartbeat from the FC through the relay')

    # -- 3. the pilot --------------------------------------------------------------------------------------------------
    def start_pilot(self):
        cmd = [self.py, '-B', str(TOOLKIT / 'tools' / 'pilot.py'), 'takeoff', '--vehicle', str(Path(self.a.vehicle).resolve()),
               '--relay-port', str(self.relay), '--listen-port', str(self.pilot_port), '--log-dir', str(self.out / 'pilot')]
        script = self.script()
        if script:
            cmd += ['--after', str(script)]
        if self.hitl.get('climb_bank'):
            cmd += ['--climb-bank', str(self.hitl['climb_bank'])]
        env = dict(os.environ)
        if self.a.mode == 'sitl':
            env.update(SIM2HITL_SIMCLOCK=str(self.simclock), SIM2HITL_PILOTSYNC=str(self.pilot_sync))
        self.procs['pilot'] = subprocess.Popen(cmd, env=env, stdout=open(self.out / 'pilot.log', 'w'), stderr=subprocess.STDOUT)
        self.event('pilot started', cmd=' '.join(cmd))

    def sim_seconds(self):
        """SITL: simhost's simulated time (its --simclock file: simulated ns, monotonic ns), or None."""
        try:
            return struct.unpack('<QQ', self.simclock.read_bytes()[:16])[0] / 1e9
        except (OSError, struct.error):
            return None

    def wait_pilot(self, m):
        # flight_timeout is flight time: wall seconds in HITL, simulated seconds in SITL (lockstep runs many times faster
        # than real time; a wall-clock limit there let a stuck flight run for hours of simulated time). A wall-clock
        # limit stays in SITL as a backstop.
        limit = float(self.hitl.get('flight_timeout', 900)) + 300
        wall_limit = limit if self.a.mode == 'hitl' else 4 * limit
        end, last, stopping = time.monotonic() + wall_limit, 0.0, False
        status = self.out / 'pilot' / 'status.json'
        timeout = limit
        while time.monotonic() < end:
            if self.a.mode == 'sitl' and (self.sim_seconds() or 0) > limit:
                break
            rc = self.procs['pilot'].poll()
            if not stopping and status.exists():
                try:
                    after = json.loads(status.read_text()).get('after_state')
                except (json.JSONDecodeError, OSError):
                    after = None
                if after in ('complete', 'failed'):   # the script ended; the pilot holds the sticks until told to stop
                    self.event('command script ended', after_state=after)
                    (self.out / 'pilot' / 'stop').touch()
                    stopping = True
            if rc is not None:
                tail = (self.out / 'pilot.log').read_text().strip().splitlines()[-1:]
                self.event('pilot ended', exit_code=rc, last=tail)
                return rc
            if self.procs['simhost'].poll() is not None:
                raise RuntimeError('simhost stopped during the flight')
            if time.monotonic() - last > 1.0:
                m.mav.heartbeat_send(mavutil.mavlink.MAV_TYPE_GCS, mavutil.mavlink.MAV_AUTOPILOT_INVALID, 0, 0, 0)
                last = time.monotonic()
            m.recv_match(blocking=True, timeout=0.2)
        self.event('flight timed out', seconds=timeout, clock='wall' if self.a.mode == 'hitl' else 'simulated',
                   simulated_s=self.sim_seconds() if self.a.mode == 'sitl' else None)
        (self.out / 'pilot').mkdir(exist_ok=True)
        (self.out / 'pilot' / 'stop').touch()
        try:
            return self.procs['pilot'].wait(timeout=30)
        except subprocess.TimeoutExpired:
            self.procs['pilot'].kill()
            return None

    def force_disarm(self, m):
        for _ in range(5):
            m.mav.command_long_send(m.target_system, m.target_component, mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM, 0,
                                    0, FORCE_DISARM, 0, 0, 0, 0, 0)
            ack = m.recv_match(type='COMMAND_ACK', blocking=True, timeout=2)
            if ack is not None and ack.command == mavutil.mavlink.MAV_CMD_COMPONENT_ARM_DISARM:
                self.event('force disarm', result=ack.result)
                return ack.result
        self.event('force disarm', result=None)
        return None

    def stop(self):
        for name in ('pilot', 'simhost'):
            p = self.procs.get(name)
            if p and p.poll() is None:
                p.send_signal(signal.SIGTERM)
                try:
                    p.wait(timeout=15)
                except subprocess.TimeoutExpired:
                    p.kill()
        log = self.out / 'simhost.log'
        if log.exists():
            tail = [x for x in log.read_text().splitlines() if 'stopped at' in x]
            self.event('simhost stopped', summary=tail[-1] if tail else None)

    # -- 4. the FC log -------------------------------------------------------------------------------------------------
    def recover_and_log(self):
        """HITL: the standard recover, then the newest log, newer than the newest before the flight."""
        fc = FC(self.a.link).connect()
        try:
            recover = fc.recover(force_disarm=True, expect_hitl=1)
            self.event('recover', **{k: v for k, v in recover.items() if k != 'after_reboot'})
            logs = fc.logs()
            newest = max(logs) if logs else None
            if newest is None or self.newest_before is None or newest <= self.newest_before:
                self.event('ulog', problem=f'no log newer than {self.newest_before} (newest {newest})')
                return recover, None
            got = fc.log_download(newest, self.out / 'fc_log.ulg', twice=not self.a.log_once)
            self.event('ulog', **got, newest_before=self.newest_before)
            return recover, self.out / 'fc_log.ulg'
        finally:
            fc.close()

    def sitl_log(self):
        new = sorted(self.sitl_logs() - self.logs_seen, key=lambda p: p.stat().st_mtime)
        if not new:
            self.event('ulog', problem='no new FC log: the flight wrote none (not armed?)')
            return None
        dst = self.out / 'fc_log.ulg'
        dst.write_bytes(new[-1].read_bytes())
        self.event('ulog', source=str(new[-1]), size=dst.stat().st_size, new_logs=len(new))
        return dst

    # -- 5. the check --------------------------------------------------------------------------------------------------
    def check(self, ulog):
        script = self.hitl.get('check')
        if not script or ulog is None:
            return {'verdict': 'NOT_RUN', 'why': 'no check in hitl.json' if not script else 'no ULog of this flight'}
        out = self.out / 'check.json'
        r = self.sh([self.py, '-B', self.repo / script, ulog, '--out', out], timeout=900, check=False, log='check.log')
        result = json.loads(out.read_text()) if out.exists() else {'verdict': 'ERROR', 'exit_code': r.returncode}
        self.event('check', script=script, verdict=result.get('verdict'), exit_code=r.returncode)
        return result

    def go(self):
        summary = {'mode': self.a.mode, 'recipe': self.recipe.name, 'repo': str(self.repo), 'hitl_json': self.hitl,
                   'vehicle': str(Path(self.a.vehicle).resolve()), 'configs': self.a.config, 'events_at': self.a.at,
                   'versions': {'repo': git_state(self.repo), 'toolkit': git_state(TOOLKIT)}}
        m = None
        try:
            summary['fc'] = self.prepare_sitl() if self.a.mode == 'sitl' else self.prepare_hitl()
            self.start_simhost()
            m = self.mavlink()
            self.start_pilot()
            summary['pilot_exit'] = self.wait_pilot(m)
            summary['force_disarm'] = self.force_disarm(m)   # while simhost runs: PX4 logs it, lockstep keeps going
        except Exception as e:  # noqa: BLE001  (every failure ends in the summary)
            summary['error'] = f'{type(e).__name__}: {e}'
            self.event('error', error=summary['error'])
            if m is not None:
                try:
                    self.force_disarm(m)
                except Exception:  # noqa: BLE001
                    pass
        finally:
            self.stop()
        ulog = None
        try:
            if self.a.mode == 'hitl':
                if 'fc' in summary:   # the FC was read before the flight; a recover and the log are owed
                    summary['recover'], ulog = self.recover_and_log()
            else:
                ulog = self.sitl_log()
                self.sitl_fc('stop', '--instance', self.a.instance, check=False)
        except Exception as e:  # noqa: BLE001
            summary['error_after'] = f'{type(e).__name__}: {e}'
            self.event('error', error=summary['error_after'])
        summary['check'] = self.check(ulog)
        status = self.out / 'pilot' / 'status.json'
        summary['pilot_status'] = json.loads(status.read_text()) if status.exists() else None
        summary['after_state'] = (summary['pilot_status'] or {}).get('after_state')
        tail = [x for x in (self.out / 'simhost.log').read_text().splitlines() if 'stopped at' in x] \
            if (self.out / 'simhost.log').exists() else []
        summary['simhost'] = tail[-1] if tail else None
        ok = (summary['check'].get('verdict') == 'PASS' and summary.get('pilot_exit') == 0
              and summary['after_state'] == 'complete' and 'error' not in summary and 'error_after' not in summary)
        summary['verdict'] = 'PASS' if ok else 'FAIL'
        (self.out / 'summary.json').write_text(json.dumps(summary, indent=1, default=str) + '\n')
        self.event('done', verdict=summary['verdict'], out=str(self.out))
        return 0 if ok else 1


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('mode', choices=['sitl', 'hitl'])
    p.add_argument('recipe')
    p.add_argument('--vehicle', required=True, help="simhost's vehicle folder (vehicle.toml with a [pilot] table)")
    p.add_argument('--config', action='append', default=[], help='a model configuration file ([set] property = value)')
    p.add_argument('--at', action='append', default=[], metavar='T:PROPERTY=VALUE', help='a scenario event for simhost')
    p.add_argument('--repo', help='the vehicle repository (default: found from the recipe)')
    p.add_argument('--instance', type=int, default=0, help='SITL FC instance')
    p.add_argument('--link', help='HITL: the FC serial device')
    p.add_argument('--baud', type=int, default=2000000)
    p.add_argument('--deploy', choices=['reuse', 'flash', 'none'], default='reuse', help='HITL: tools/deploy.py first')
    p.add_argument('--reset-unmanaged', action='store_true', help='HITL: passed to tools/deploy.py')
    p.add_argument('--log-once', action='store_true', help='HITL: download the log once (no second read to compare)')
    p.add_argument('--out')
    a = p.parse_args()
    if a.mode == 'hitl' and not a.link:
        p.error('hitl needs --link')
    if not SIMHOST.is_file():
        sys.exit(f'{SIMHOST} missing: build simhost first (docs/architecture.md)')
    sys.exit(Run(a).go())


if __name__ == '__main__':
    main()
