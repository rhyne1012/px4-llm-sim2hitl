#!/usr/bin/env python3
"""HITL / flight console: one desktop launcher, one window (from a derived project, 2026-11-21).

  <venv python> -B hitl/console/console.py [--units deploy/units.json] [--port 8765] [--no-browser]

A page on 127.0.0.1 only (each action carries a token made at start, so another web page cannot press its buttons):
  - which FC is on USB (AUTOPILOT_VERSION uid, the project's units file: deploy/units.json, the format in
    hitl/console/units.example.json), HITL or flight (SYS_HITL), and whether its parameters, boot file and logger
    topic list are its recipe's (param-readback + deploy/check_params.py, the SD card's files against the recipe's
    sd/). Without a units file nothing is read or written: the page says how to make one;
  - 'switch to HITL' / 'switch to flight': the plan first (deploy/flight_switch.py: the values to write; when the SD
    card's files are not the recipe's, deploy-test --reuse --no-hitl of the HITL recipe instead, only in HITL), then
    the user's confirm button writes, the FC reboots and is checked again. Only a unit of role 'aircraft' with a
    HITL and a flight recipe that pair (flight_switch.pair) switches to flight; 'hitl_only' units never do;
  - in HITL: the simulation (as hitl/qgc_session.py): QGC opened, the model on the ground, an automatic takeoff to
    the units file's takeoff_m that then holds (after_takeoff_loiter) or the user's own takeoff; restart from the
    ground; end (model stop, recover, the FC log kept twice).
The readback uses the parameter list of the HITL recipe of the unit identified last in this run (else of the first
unit in the file whose firmware files are built on this machine). On another firmware that list does not match the
FC's: the readback is INCOMPLETE only by names (missing, not_in_list, type_mismatch) and still says which FC it is
(uid); it is read again with that unit's own HITL recipe. Whether the firmware is the recipe's is check_params'
judgement.
CPU pinning follows the machine: with isolated CPUs (the kernel's isolcpus, /sys/devices/system/cpu/isolated) the
owner it starts runs on the first isolated CPU and the console with everything it runs on the CPUs that are not
isolated; without isolated CPUs nothing is pinned. The HITL owner is started when it is not running, and shut down
when the console ends. One console or HITL session window at a time (hitl/qgc_session.py's lock).

QGC: while the console runs, QGC must not auto-connect over USB or the telemetry radio (it would take the FC's
serial port from the owner): before its first FC access the console asks for QGC to be closed, then turns those two
off in QGroundControl.ini (UDP stays on: QGC reaches the FC through the owner). When the console ends (its 'close'
button, closing its terminal, Ctrl-C) it closes QGC (QGC writes its settings when it quits, so the file is edited
after that) and turns USB and radio auto-connect back on.
"""
import argparse
import hashlib
import html
import json
import os
import re
import secrets
import signal
import subprocess
import sys
import threading
import time
import traceback
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
PROJECT = HERE.parents[1]
sys.path.insert(0, str(PROJECT / 'hitl'))
sys.path.insert(0, str(PROJECT / 'deploy'))
import qgc_session as qs  # noqa: E402 - owner IPC status, runbridge, QGC, the one-window lock, FC log records
import check_params  # noqa: E402
import flight_switch  # noqa: E402
from host import pwm_defaults  # noqa: E402 - which output functions are servos and motors

DEPLOY = PROJECT / 'deploy'
UNITS_FILE = DEPLOY / 'units.json'  # the project's own; --units overrides
UNITS_EXAMPLE = HERE / 'units.example.json'
TITLE = 'HITL／實飛控制台'
TAKEOFF_M = 40
ROLES = ('aircraft', 'hitl_only')
HOWTO = ('做法：把 hitl/console/units.example.json 複製成 deploy/units.json，改成自己的飛控，存檔後按「重新核對」'
         '（uid：./runbridge param-readback 結果的 autopilot_version；清單裡已經有一塊時，沒列的飛控核對後會顯示'
         '完整 uid。說明在 hitl/console/README.md）')
SD = {'boot': ('/fs/microsd/etc/extras.txt', 'etc/extras.txt'),
      'topics': ('/fs/microsd/etc/logging/logger_topics.txt', 'etc/logging/logger_topics.txt')}
AGENT_PORT = 14560
CPU_ISOLATED = Path('/sys/devices/system/cpu/isolated')
CPU_ONLINE = Path('/sys/devices/system/cpu/online')
QGC_INI = qs.QGC_INI
QGC_OFF = {'autoConnectPixhawk': 'false', 'autoConnectSiKRadio': 'false', 'autoConnectUDP': 'true'}
QGC_ON = {'autoConnectPixhawk': 'true', 'autoConnectSiKRadio': 'true'}
MODES = {1: 'Manual', 2: 'Altitude', 3: 'Position', 4: 'Auto', 5: 'Acro', 6: 'Offboard', 7: 'Stabilized'}
AUTO_SUB = {2: 'Takeoff', 3: 'Hold', 4: 'Mission', 5: 'Return', 6: 'Land'}
OUTPUT = re.compile(r'PWM_(MAIN|AUX)_FUNC(\d+)')
SHOWN = 12  # problem rows kept per recipe check (the full report is saved next to the readback)


class Stop(Exception):
    """Not done, with the reason for the page."""


def cpu_list(text):
    """The CPUs of a kernel CPU list ('7,15', '0-6,8-14', ''), sorted."""
    cpus = set()
    for part in text.strip().split(','):
        part = part.strip()
        if not part:
            continue
        lo, _, hi = part.partition('-')
        cpus.update(range(int(lo), int(hi or lo) + 1))
    return sorted(cpus)


def cpu_text(cpus):
    """A kernel CPU list for these CPUs ([0..6, 8..14] -> '0-6,8-14')."""
    runs, out = [], []
    for c in sorted(cpus):
        if runs and c == runs[-1][1] + 1:
            runs[-1][1] = c
        else:
            runs.append([c, c])
    for lo, hi in runs:
        out.append(str(lo) if lo == hi else f'{lo}-{hi}')
    return ','.join(out)


def pinning(isolated, online):
    """(owner CPU, work CPUs) for these CPU lists: the first isolated CPU for the owner and the CPUs that are not
    isolated for the rest; (None, None) without isolated CPUs (or none left for the rest): nothing pinned."""
    work = [c for c in online if c not in isolated]
    if not isolated or not work:
        return None, None
    return isolated[0], work


def machine_pinning():
    try:
        return pinning(cpu_list(CPU_ISOLATED.read_text()), cpu_list(CPU_ONLINE.read_text()))
    except (OSError, ValueError):
        return None, None


OWNER_CPU, WORK_CPUS = machine_pinning()


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest() if Path(path).is_file() else None


def shown_path(path):
    """A path as the page shows it: relative to the project when inside it."""
    try:
        return str(Path(path).resolve().relative_to(PROJECT))
    except ValueError:
        return str(path)


def units_problems(data):
    """Why a units file cannot be used (empty when it can); recipes are directories of DEPLOY."""
    if not isinstance(data, dict) or not isinstance(data.get('units'), dict) or not data['units']:
        return ['要有 "units"：uid → 飛控（格式見 hitl/console/units.example.json）']
    problems = []
    if not isinstance(data.get('title', TITLE), str) or not data.get('title', TITLE).strip():
        problems.append('"title" 要是文字')
    m = data.get('takeoff_m', TAKEOFF_M)
    if isinstance(m, bool) or not isinstance(m, (int, float)) or not 0 < m <= 10000:
        problems.append('"takeoff_m" 要是正的數字（公尺）')
    for uid, unit in data['units'].items():
        if not uid.isdigit():
            problems.append(f'{uid}：uid 要是 AUTOPILOT_VERSION 的 uid（數字）')
            continue
        if not isinstance(unit, dict):
            problems.append(f'{uid}：要是一個物件')
            continue
        if not isinstance(unit.get('name'), str) or not unit['name'].strip():
            problems.append(f'{uid}：沒有 "name"')
        if unit.get('role') not in ROLES:
            problems.append(f'{uid}："role" 要是 aircraft 或 hitl_only')
        if unit.get('role') == 'hitl_only' and unit.get('flight') is not None:
            problems.append(f'{uid}：hitl_only 不切到實飛，"flight" 要是 null')
        for key in ('hitl', 'flight'):
            name = unit.get(key)
            if name is None and key == 'flight':
                continue
            if not isinstance(name, str) or not name or name != Path(name).name or name in ('.', '..'):
                problems.append(f'{uid}："{key}" 要是 deploy/ 下的配方資料夾名稱')
            elif not (DEPLOY / name / 'params.json').is_file():
                problems.append(f'{uid}：配方 {name} 不存在（deploy/{name}/params.json）')
    return problems


def load_units(path):
    """The units file: title, takeoff_m, units (None when the file is missing or wrong: then problems say why)."""
    path = Path(path)
    setup = {'path': shown_path(path), 'title': TITLE, 'takeoff_m': TAKEOFF_M, 'units': None, 'problems': []}
    if not path.is_file():
        setup['problems'] = [f'沒有飛控清單 {setup["path"]}']
        return setup
    try:
        data = json.loads(path.read_text())
    except (OSError, ValueError) as exc:
        setup['problems'] = [f'{setup["path"]} 讀不了：{exc}']
        return setup
    problems = units_problems(data)
    if isinstance(data, dict) and isinstance(data.get('title'), str) and data['title'].strip():
        setup['title'] = data['title'].strip()
    if problems:
        setup['problems'] = [f'{setup["path"]}：{p}' for p in problems]
        return setup
    setup.update(takeoff_m=data.get('takeoff_m', TAKEOFF_M),
                 units={uid: {'name': u['name'], 'role': u['role'], 'hitl': u['hitl'], 'flight': u.get('flight')}
                        for uid, u in data['units'].items()})
    return setup


def recipe_files_missing(name):
    """Why recipe name cannot be checked here (None when it can): its firmware image and parameter list are built
    locally (px4/build_firmware.py), not kept in git."""
    recipe = DEPLOY / name
    try:
        params = json.loads((recipe / 'params.json').read_text())
        info = json.loads((recipe / params['firmware']).read_text())
        files = [recipe / params['firmware_params']['file'], recipe / 'firmware' / info['outputs']['firmware']['file']]
    except (OSError, ValueError, KeyError, TypeError) as exc:
        return f'配方 {name} 讀不了：{exc}'
    missing = [shown_path(f) for f in files if not f.is_file()]
    return (f'配方 {name} 的韌體檔不在這台電腦（{"、".join(missing)}）：先 ./runbridge build-firmware --release '
            f'deploy/{name}') if missing else None


def readback_usable(code, value):
    """A param-readback result the check can use: PASS, or INCOMPLETE only because the FC's parameter list is not
    the one asked with (missing, not_in_list, type_mismatch: another firmware), with its file and the FC's uid,
    every used index received and a consistent PARAM_VALUE stream."""
    if not isinstance(value, dict) or not value.get('path') or (value.get('autopilot_version') or {}).get('uid') is None:
        return False
    if code == 0 and value.get('verdict') == 'PASS':
        return True
    return (code == 5 and value.get('verdict') == 'INCOMPLETE' and not value.get('identity_missing')
            and not value.get('used_index_missing') and not value.get('used_index_missing_count')
            and not value.get('consistency') and not value.get('consistency_count'))


def readback_failure(value):
    """The page's message for a readback the check cannot use."""
    value = value if isinstance(value, dict) else {}
    av = value.get('autopilot_version') or {}
    who = f'（板號 {av.get("board_version")}，韌體 git {av.get("git_hash_prefix")}）' if av else ''
    if value.get('verdict') == 'INCOMPLETE':
        why = [f'{k} {value.get(k + "_count", len(value.get(k) or []))}' for k in
               ('used_index_missing', 'consistency', 'missing', 'not_in_list', 'type_mismatch')
               if value.get(k + '_count') or value.get(k)]
        why += ['沒有 AUTOPILOT_VERSION'] if value.get('identity_missing') else []
        return f'參數讀回不完整{who}：{"、".join(why) or "原因不明"}。再按一次「重新核對」'
    return f'參數讀回沒有完成{who}：' + json.dumps(value, ensure_ascii=False)[:200]


def mode_name(custom_mode):
    main, sub = ((custom_mode or 0) >> 16) & 0xFF, ((custom_mode or 0) >> 24) & 0xFF
    return AUTO_SUB.get(sub, 'Auto') if main == 4 else MODES.get(main, '?')


def with_autoconnect(text, values):
    """QGroundControl.ini text with these [AutoConnect] keys set (the section added when missing), the rest kept."""
    lines = text.splitlines()
    start = next((i for i, x in enumerate(lines) if x.strip() == '[AutoConnect]'), None)
    if start is None:
        lines += ([''] if lines and lines[-1].strip() else []) + ['[AutoConnect]'] + [f'{k}={v}' for k, v in values.items()]
        return '\n'.join(lines) + '\n'
    end = next((i for i in range(start + 1, len(lines)) if lines[i].startswith('[')), len(lines))
    seen = set()
    for i in range(start + 1, end):
        key = lines[i].split('=', 1)[0].strip()
        if key in values:
            lines[i] = f'{key}={values[key]}'
            seen.add(key)
    last = end
    while last > start + 1 and not lines[last - 1].strip():
        last -= 1
    lines[last:last] = [f'{k}={v}' for k, v in values.items() if k not in seen]
    return '\n'.join(lines) + '\n'


def autoconnect(values):
    """Set QGC's auto-connect keys in its settings file (QGC closed: it rewrites the file when it quits)."""
    text = QGC_INI.read_text() if QGC_INI.is_file() else ''
    new = with_autoconnect(text, values)
    if new != text:
        QGC_INI.parent.mkdir(parents=True, exist_ok=True)
        temp = QGC_INI.with_suffix('.ini.console')
        temp.write_text(new)
        os.replace(temp, QGC_INI)


def qgc_running():
    return subprocess.run(['pgrep', '-x', 'QGroundControl'], capture_output=True).returncode == 0


def close_qgc(grace=5, seconds=10):
    """Close QGC; True when it is gone. QGC 5.1.5 (AppImage) ignores SIGTERM and SIGINT, with or without a vehicle
    (derived project, 2026-11-21), so after the grace period it is killed: its settings are written as they change
    (QSettings), and the AppImage unmounts itself."""
    if not qgc_running():
        return True
    for sig, wait in (('-TERM', grace), ('-KILL', seconds)):
        subprocess.run(['pkill', sig, '-x', 'QGroundControl'], capture_output=True)
        end = time.monotonic() + wait
        while time.monotonic() < end:
            if not qgc_running():
                return True
            time.sleep(0.5)
    return False


def outputs(readback):
    """What the outputs drive, from the FC's own PWM_MAIN_FUNCn and PWM_AUX_FUNCn (servos 201-208, motors 101-112):
    channel labels such as 'MAIN3', 'AUX1', MAIN first."""
    found = []
    for p in readback['parameters']:
        m = OUTPUT.fullmatch(p['name'])
        if m:
            found.append(((m.group(1) != 'MAIN', int(m.group(2))), m.group(1) + m.group(2), round(p['value'] or 0)))
    found.sort()
    pick = lambda functions: [label for _, label, value in found if value in functions]
    return {'servos': pick(pwm_defaults.SERVO), 'motors': pick(pwm_defaults.MOTOR)}


def not_ready(s):
    """Why the FC cannot be read or written now."""
    fc = s.get('fc') or {}
    problems = []
    if fc.get('state') != 'verified':
        problems.append(f'飛控狀態 {fc.get("state")}（要已驗證）')
    if fc.get('armed') is not False:
        problems.append('已解鎖或狀態不明（要未解鎖）')
    if s.get('model') == 'running':
        problems.append('模擬在跑（先按「結束」）')
    if s.get('recovery_required'):
        problems.append('有待恢復')
    if s.get('param_deploy_pending'):
        problems.append('有沒做完的參數部署')
    if (s.get('pilot') or {}).get('running'):
        problems.append('自動飛手還在跑')
    return problems


def fmt(value):
    return 'null' if value is None else f'{value:.6g}' if isinstance(value, float) else str(value)


def summary(report, saved=None):
    """The page's rows for a check_params report: values first, then the other findings (long lists counted)."""
    rows = [f'{r["name"]} {fmt(r["fc"])}（要 {fmt(r["expected"])}）' for r in report['wrong_value']]
    rows += [f'{r["name"]} {fmt(r["fc"])}（要預設 {fmt(r["default"])}）' for r in report['not_default']]
    for key in ('identity', 'local_mismatch', 'structure', 'not_read', 'not_in_firmware', 'unknown_name',
                'fc_owned_set_changed'):
        items = [x if isinstance(x, str) else json.dumps(x, ensure_ascii=False) for x in report.get(key) or []]
        if len(items) > 3:
            rows.append(f'{key}: {len(items)} 項（{"、".join(x[:40] for x in items[:3])}…）')
        else:
            rows += [f'{key}: {x[:80]}' for x in items]
    if len(rows) > SHOWN:
        rows = rows[:SHOWN - 1] + [f'…共 {len(rows)} 項' + (f'（完整的在 {saved}）' if saved else '')]
    return rows


def plan_rows(writes):
    """The confirm dialog's rows for flight_switch.plan's writes."""
    rows = []
    for w in writes:
        row = f'{w["name"]}  {fmt(w["old"])} → {fmt(w["new"])}'
        if w.get('why'):
            row += '（配方沒有，改回預設）'
        if w.get('px4io') is not None:
            row += f'（PX4 寫完功能後會自己改成 {fmt(w["px4io"])}，之後寫回）'
        rows.append(row)
    return rows


def judge(uid, unit, readback_path, readback, sd, folder=None):
    """The check of one readback against the unit's recipes (no FC): per recipe the check_params verdict, the SD
    card's files, whether the firmware is the recipe's; the recipe pair of an aircraft unit; its outputs."""
    checks = {}
    if folder is not None:
        Path(folder).mkdir(parents=True, exist_ok=True)
    for target in ('hitl', 'flight'):
        name = unit.get(target)
        if not name:
            continue
        recipe = DEPLOY / name
        missing = recipe_files_missing(name)
        if missing:
            checks[target] = {'recipe': name, 'verdict': 'INCOMPLETE', 'sd_ok': False, 'firmware_ok': False,
                              'unavailable': missing, 'problems': [missing]}
            continue
        report = check_params.check(recipe, readback_path)
        saved = None
        if folder is not None:
            saved = Path(folder) / f'check_{target}_{name}.json'
            saved.write_text(json.dumps(report, indent=1, ensure_ascii=False) + '\n')
        want = {key: sha256(recipe / 'sd' / local) for key, (_, local) in SD.items()}
        sd_ok = want == sd
        checks[target] = {'recipe': name, 'verdict': report['verdict'], 'sd_ok': sd_ok,
                          'firmware_ok': not report['identity'] and not report['local_mismatch'],
                          'problems': summary(report, saved and shown_path(saved)) + ([] if sd_ok else [
                              f'記憶卡：開機檔 {"對" if want["boot"] == sd["boot"] else "不對"}、記錄清單 '
                              f'{"對" if want["topics"] == sd["topics"] else "不對"}'])}
    pair = None
    if unit.get('role') == 'aircraft' and unit.get('hitl') and unit.get('flight'):
        pair = flight_switch.pair(DEPLOY / unit['hitl'], DEPLOY / unit['flight'])
    sys_hitl = next((p['value'] for p in readback['parameters'] if p['name'] == 'SYS_HITL'), None)
    return {'uid': uid, 'unit': unit, 'SYS_HITL': sys_hitl, 'checks': checks, 'pair': pair,
            'readback': str(readback_path), 'outputs': outputs(readback)}


class Console:
    def __init__(self, out, units_path=UNITS_FILE):
        self.out = out
        self.units_path = Path(units_path)
        self.setup = load_units(self.units_path)
        self.last_uid = None    # the unit identified last: its HITL recipe's parameter list for the next readback
        self.state_lock = threading.Lock()
        self.busy = threading.Lock()
        self.op = None          # the current or last operation: name, log, done, error
        self.info = None        # the last check of the FC
        self.plan = None        # a switch waiting for the confirm button
        self.sim = None         # the simulation: takeoff, record
        self.live = None        # the owner's last status
        self.closing = False
        self.quit = threading.Event()  # the page's close button, the terminal, Ctrl-C
        self.qgc_off = False    # QGC's USB / radio auto-connect turned off by this console

    # ---- operations: one at a time, in a thread ----
    def log(self, text):
        with self.state_lock:
            if self.op is not None:
                self.op['log'].append(time.strftime('%H:%M:%S ') + text)
        print(text, flush=True)

    def start(self, name, fn, *args):
        if not self.busy.acquire(blocking=False):
            raise Stop('上一個動作還沒做完')
        with self.state_lock:
            self.op = {'name': name, 'log': [], 'done': False, 'error': None, 'started': time.time()}

        def run():
            try:
                fn(*args)
            except Stop as exc:
                with self.state_lock:
                    self.op['error'] = str(exc)
                print('停下：' + str(exc), flush=True)
            except Exception as exc:  # noqa: BLE001 - shown on the page, traceback kept
                with self.state_lock:
                    self.op['error'] = f'{type(exc).__name__}: {exc}'
                with (self.out / 'errors.log').open('a') as stream:
                    stream.write(time.strftime('%F %T\n') + traceback.format_exc() + '\n')
            finally:
                with self.state_lock:
                    self.op['done'] = True
                self.busy.release()
        threading.Thread(target=run, daemon=True).start()

    # ---- owner ----
    def ensure_owner(self):
        s = qs.status()
        if s:
            return s
        self.log('開 HITL 主程式' + (f'（CPU {OWNER_CPU}）…' if OWNER_CPU is not None else '…'))
        log = qs.cache() / 'manual'
        log.mkdir(parents=True, exist_ok=True)
        stream = open(log / f'console_owner_{time.strftime("%Y%m%d_%H%M%S")}.log', 'a')
        pin = ['taskset', '-c', str(OWNER_CPU)] if OWNER_CPU is not None else []
        subprocess.Popen(pin + [qs.RUNBRIDGE, 'bridge'], cwd=PROJECT, stdout=stream,
                         stderr=subprocess.STDOUT, stdin=subprocess.DEVNULL, start_new_session=True)
        return self.settled()

    def settled(self, seconds=90, generation=None):
        """The owner's status once the FC is verified with SYS_HITL read (and, after a reboot, a new connection)."""
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            s = qs.status()
            fc = (s or {}).get('fc') or {}
            if fc.get('state') == 'verified' and fc.get('SYS_HITL') is not None and \
                    (generation is None or fc.get('connection_generation') != generation):
                return s
            time.sleep(1)
        raise Stop(f'{seconds} 秒內飛控沒有連上（USB 有接嗎？QGC 不要用 USB 連飛控）')

    def call(self, *args, timeout=600):
        code, value = qs.runbridge(*args, timeout=timeout)
        if code:
            raise Stop(f'{args[0]} 沒有完成：' + json.dumps(value, ensure_ascii=False)[:300])
        return value or {}

    # ---- QGC ----
    def qgc_ready(self):
        """Before the FC is touched: QGC closed (unless this console already turned its USB / radio auto-connect
        off), then auto-connect off."""
        if self.qgc_off:
            return
        if qgc_running():
            raise Stop('請先關掉 QGC：它的 USB／數傳自動連線可能佔住飛控。關掉後按「重新核對」')
        autoconnect(QGC_OFF)
        self.qgc_off = True
        self.log('QGC 的 USB／數傳自動連線先關掉（只留 UDP，經 HITL 主程式連飛控）；關閉控制台時會打開')

    def qgc_restore(self):
        """When the console ends: QGC closed, then its USB / radio auto-connect on again."""
        if not self.qgc_off:
            return True
        if qgc_running():
            print('關掉 QGC（它關閉時會寫設定，要先關才能改；QGC 不理會一般的關閉訊號，5 秒後強制結束）…', flush=True)
            if not close_qgc():
                print('QGC 沒有關掉：自動連線沒有改回。關掉 QGC 後，在 QGC 的 Application Settings → General → '
                      'AutoConnect 勾回 Pixhawk 和 SiK Radio', flush=True)
                return False
        autoconnect(QGC_ON)
        self.qgc_off = False
        print('QGC 的 USB（飛控）和數傳（SiK radio）自動連線已打開', flush=True)
        return True

    # ---- check ----
    def read_back(self, name, folder):
        """param-readback with the parameter list of recipe name; Stop when the result cannot be used."""
        missing = recipe_files_missing(name)
        if missing:
            raise Stop(missing)
        code, value = qs.runbridge('param-readback', '--release', str(DEPLOY / name), '--out', str(folder),
                                   timeout=600)
        if not readback_usable(code, value):
            raise Stop(readback_failure(value))
        return value

    def check(self):
        self.setup = setup = load_units(self.units_path)  # read again: an edited file counts at the next check
        if setup['units'] is None:
            raise Stop('；'.join(setup['problems']) + '。' + HOWTO)
        units = setup['units']
        self.qgc_ready()
        s = self.ensure_owner()
        s = self.settled() if (s.get('fc') or {}).get('state') != 'verified' else s
        problems = not_ready(s)
        if problems:
            raise Stop('現在不能讀飛控：' + '；'.join(problems))
        self.log('讀回參數與記憶卡（約 10 秒）…')
        folder = self.out / time.strftime('check_%H%M%S')
        order = [u['hitl'] for u in ([units[self.last_uid]] if self.last_uid in units else []) + list(units.values())]
        first = next((name for name in order if not recipe_files_missing(name)), order[0])  # built on this machine
        value = self.read_back(first, folder / first)
        uid = str(value['autopilot_version']['uid'])
        unit = units.get(uid)
        if unit and unit['hitl'] != first:
            self.log(f'這塊是 {unit["name"]}：用它的配方 {unit["hitl"]} 的參數表再讀一次…')
            value = self.read_back(unit['hitl'], folder / unit['hitl'])
            if str(value['autopilot_version']['uid']) != uid:
                raise Stop('兩次讀回之間飛控換了一塊：再按一次「重新核對」')
        if unit:
            self.last_uid = uid
        path = Path(value['path'])
        readback = json.loads(path.read_text())
        unit = unit or {'name': '不認得的飛控', 'role': 'unknown', 'hitl': None, 'flight': None}
        sd = {}
        for key, (path_on_card, _) in SD.items():
            listing = self.call('sd-list', '--sd-path', str(Path(path_on_card).parent), timeout=120)
            have = any(e.get('name') == Path(path_on_card).name for e in listing.get('entries', []))
            sd[key] = self.call('sd-get', '--sd-path', path_on_card, '--out', str(folder / 'sd'),
                                timeout=120).get('sha256') if have else None
        info = judge(uid, unit, path, readback, sd, folder)
        info.update(generation=(s.get('fc') or {}).get('connection_generation'), at=time.time())
        with self.state_lock:
            self.info = info
        self.log(self.check_line(info))
        return info

    def check_line(self, info):
        unit, sys_hitl = info['unit'], info['SYS_HITL']
        if unit['role'] == 'unknown':
            return f'不認得的飛控（uid {info["uid"]}）：把它加進 {self.setup["path"]}'
        here = info['checks'].get('hitl' if sys_hitl == 1 else 'flight')
        line = (f'{unit["name"]}（uid …{info["uid"][-4:]}）：{"HITL" if sys_hitl == 1 else "實飛" if sys_hitl == 0 else sys_hitl}，'
                + (f'設定核對 {here["verdict"]}{"" if here["sd_ok"] else "，記憶卡不對"}' if here else '這塊沒有這個模式的配方'))
        pair = info.get('pair')
        if pair:
            line += (f'；配方對有問題（{len(pair["problems"])} 項）' if pair['problems'] else
                     f'；HITL 和實飛配方差 {len(pair["differences"])} 個值')
        return line

    # ---- switch ----
    def make_plan(self, target):
        info = self.check()
        unit = info['unit']
        if unit['role'] == 'unknown':
            raise Stop(f'不認得這塊飛控（uid {info["uid"]}）：先把它加進 {self.setup["path"]}')
        if target == 'flight' and unit['role'] != 'aircraft':
            raise Stop('這塊只做 HITL，不能切到實飛')
        name = unit.get(target)
        if not name:
            raise Stop(f'這塊沒有{"實飛" if target == "flight" else " HITL "}配方（{self.setup["path"]}）')
        pair = info.get('pair')
        if target == 'flight' and pair and pair['problems']:  # back to HITL stays possible: its own check guards it
            raise Stop(f'{unit["hitl"]} 和 {unit["flight"]} 不能只靠參數切換，先改好配方：' + '；'.join(pair['problems']))
        c = info['checks'][target]
        if c.get('unavailable'):
            raise Stop(c['unavailable'])
        if not c['firmware_ok']:
            raise Stop(f'飛控的韌體不是 {name} 的：要先燒錄（./runbridge deploy-test --release deploy/{name} --flash，'
                       '飛控要在 HITL）')
        recipe = DEPLOY / name
        if not c['sd_ok']:
            if info['SYS_HITL'] != 1:
                raise Stop('記憶卡的開機檔或記錄清單不對，只能在 HITL 寫：先切回 HITL')
            hitl = unit['hitl']
            plan = {'target': target, 'recipe': name, 'kind': 'deploy', 'deploy_recipe': hitl,
                    'rows': [f'用部署工具寫 {hitl}：參數、開機檔、記錄清單（飛控在 HITL，會重開）'],
                    'then': '完成後再按一次「切到實飛」' if target == 'flight' else None}
        elif c['verdict'] == 'PASS':
            with self.state_lock:
                self.plan = None
            self.log(f'已經是 {name}（{"HITL" if target == "hitl" else "實飛"}），不用切換')
            return
        elif c['verdict'] == 'INCOMPLETE':
            raise Stop('設定核對不完整，列不出計畫：' + '、'.join(c['problems'][:6]) + '。再按一次「重新核對」')
        else:
            try:
                writes = flight_switch.plan(recipe, Path(info['readback']))
            except SystemExit as exc:
                raise Stop(f'列不出計畫：{exc}')
            plan = {'target': target, 'recipe': name, 'kind': 'params', 'writes': writes, 'rows': plan_rows(writes)}
        plan.update(uid=info['uid'], generation=info['generation'], made=time.time())
        with self.state_lock:
            self.plan = plan
        self.log(f'切換計畫：{len(plan["rows"])} 項，按「確定寫入」才寫')

    def do_switch(self):
        with self.state_lock:
            plan, self.plan = self.plan, None
        if not plan:
            raise Stop('沒有待確認的切換')
        s = self.settled()
        if (s.get('fc') or {}).get('connection_generation') != plan['generation'] or time.time() - plan['made'] > 600:
            raise Stop('計畫之後飛控重新連線過或已經超過 10 分鐘：請重新按切換')
        problems = not_ready(s)
        if problems:
            raise Stop('現在不能寫：' + '；'.join(problems))
        if plan['kind'] == 'deploy':
            self.log(f'部署 {plan["deploy_recipe"]}（約 1–2 分鐘，飛控會重開）…')
            code, value = qs.runbridge('deploy-test', '--release', str(DEPLOY / plan['deploy_recipe']),
                                       '--reuse', '--no-hitl', timeout=1800)
            if code or (value or {}).get('verdict') != 'PASS':
                raise Stop('部署沒有完成：' + json.dumps(value, ensure_ascii=False)[:300])
            self.settled()
        else:
            generation = (s.get('fc') or {}).get('connection_generation')
            wait = any(w.get('px4io') is not None for w in plan['writes'])
            self.log(f'寫 {len(plan["writes"])} 個值（GPS_1_CONFIG、SYS_HITL 最後寫），每個都要讀到回音'
                     + ('；PX4 自己改的值等它改完再寫回' if wait else '') + '…')
            try:
                written = flight_switch.write(plan['writes'], int(plan['uid']), AGENT_PORT)
            except SystemExit as exc:
                raise Stop(f'寫入沒有完成：{str(exc)[:300]}。SYS_HITL 最後才寫，飛控還是原本的模式；不要飛，重新按切換')
            self.log(f'已寫入 {len(written)} 個值，飛控重開中…')
            self.settled(generation=generation)
        info = self.check()
        c = info['checks'].get(plan['target'])
        if not c:
            raise Stop(f'重開後的核對沒有 {plan["recipe"]}（{self.setup["path"]} 改過？）。不要飛')
        mode_now = {1: 'HITL', 0: '實飛'}.get(info['SYS_HITL'])
        if c['verdict'] == 'PASS' and c['sd_ok']:
            self.log(f'切換完成：{mode_now}，設定核對 PASS' + ('。上飛機前照實飛前的檢查表再看一次' if plan['target'] == 'flight' else ''))
        elif plan.get('then'):
            self.log(plan['then'])
        else:
            raise Stop(f'重開後核對沒有過（{c["verdict"]}）：' + '、'.join(c['problems'][:6]) + '。不要飛')

    # ---- simulation ----
    def sim_start(self, takeoff):
        info = self.check()
        c = info['checks'].get('hitl')
        if info['SYS_HITL'] != 1 or not c or c['verdict'] != 'PASS' or not c['sd_ok']:
            raise Stop('模擬要在 HITL、設定核對 PASS 時才能開始（先按「切到 HITL」）')
        s = self.settled()
        if not s.get('ready_to_start_model'):
            raise Stop('還不能啟動模型：' + '；'.join(s.get('missing_conditions') or ['原因不明']))
        problem = qs.qgc_problem()
        if problem:
            self.log('不開 QGC：' + problem)
        elif qgc_running():
            self.log('QGC 已經開著（經 UDP 連上，地圖、姿態、警告看 QGC）')
        else:
            qs.start_qgc()
            self.log('QGC 已開（經 UDP 連上，地圖、姿態、警告看 QGC）')
        record = {'name': 'console_' + time.strftime('%Y%m%d_%H%M%S'), 'kind': 'HITL from the console, observation only',
                  'started_local': time.strftime('%Y-%m-%d %H:%M:%S'), 'unit': info['unit']['name'], 'uid': info['uid'],
                  'recipe': c['recipe'], 'build_id': s.get('build_id'), 'owner_log_dir': s.get('log_dir'),
                  'automatic_takeoff': takeoff == 'auto', 'log_before': qs.newest_log()}
        self.launch(takeoff)
        with self.state_lock:
            self.sim = {'takeoff': takeoff, 'record': record, 'started': time.time()}

    def launch(self, takeoff):
        self.log('模型放到地面…')
        self.call('model-start', timeout=60)
        if takeoff == 'auto':
            altitude = self.setup['takeoff_m']
            self.call('takeoff', '--altitude', f'{altitude:g}', '--after', 'after_takeoff_loiter',
                      '--after-stable-seconds', '1', timeout=60)
            self.log(f'自動起飛到 {altitude:g} m，平飛後交給 PX4 盤旋（Hold）；動 QGC 的搖桿就接手。'
                     '飛控接著實體遙控器時，誰優先看配方的 COM_RC_IN_MODE')
        else:
            self.log('自己起飛：模式切 Stabilized → 解鎖（QGC 的 Arm 或遙控器）→ 油門推過一半 → 空速夠了再拉桿')

    def stop_model(self):
        s = qs.status() or {}
        if (s.get('pilot') or {}).get('running'):
            qs.runbridge('stop-takeoff', timeout=60)
        self.log('停模型 → 恢復（飛控會重開）…')
        qs.runbridge('model-stop', timeout=60)
        code, value = qs.runbridge('recover', '--hil-force-disarm', timeout=180)
        s = self.settled()
        fc = s.get('fc') or {}
        if code or s.get('recovery_required') or fc.get('armed') is not False or fc.get('SYS_HITL') != 1:
            raise Stop('恢復沒有完成，先不要切換或關掉：' + json.dumps(value, ensure_ascii=False)[:300])

    def sim_restart(self):
        with self.state_lock:
            sim = self.sim
        if not sim:
            raise Stop('模擬沒有在跑')
        self.stop_model()
        self.launch(sim['takeoff'])

    def sim_end(self):
        with self.state_lock:
            sim = self.sim
        if not sim:
            raise Stop('模擬沒有在跑')
        self.stop_model()
        with self.state_lock:
            self.sim = None
        record = dict(sim['record'], ended_local=time.strftime('%Y-%m-%d %H:%M:%S'), recovery='complete')
        self.log('留下這趟的飛控記錄（下載兩次核對，約 1–2 分鐘）…')
        qs.keep_records(record)
        self.log(f'記錄在 {qs.cache() / "manual_flights" / record["name"]}')

    # ---- page state ----
    def poll(self):
        while not self.closing:
            s = qs.status()
            with self.state_lock:
                self.live = s
            time.sleep(1)

    def view(self):
        with self.state_lock:
            s, op, info, plan, sim, setup = self.live, self.op, self.info, self.plan, self.sim, self.setup
            op = op and dict(op, log=op['log'][-40:])
        fc = (s or {}).get('fc') or {}
        tele = (s or {}).get('telemetry') or {}
        height = ((tele.get('LOCAL_POSITION_NED') or {}).get('values') or {}).get('height_local_m')
        speed = ((tele.get('VFR_HUD') or {}).get('values') or {}).get('airspeed_m_s')
        return {'closing': self.closing, 'qgc_running': qgc_running(), 'owner': bool(s),
                'setup': {k: setup[k] for k in ('path', 'title', 'takeoff_m', 'problems')},
                'fc': {'state': fc.get('state'), 'armed': fc.get('armed'), 'SYS_HITL': fc.get('SYS_HITL'),
                       'mode': mode_name(fc.get('custom_mode')), 'generation': fc.get('connection_generation')},
                'model': (s or {}).get('model'), 'pilot': ((s or {}).get('pilot') or {}).get('running'),
                'height': height, 'airspeed': speed, 'misses': (s or {}).get('misses'),
                'info': info, 'op': op, 'busy': self.busy.locked(),
                'plan': plan and {k: plan[k] for k in ('target', 'recipe', 'kind', 'rows')} | {'then': plan.get('then')},
                'sim': sim and {'takeoff': sim['takeoff'], 'started': sim['started']}}


def handler(console, token, page):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, code, body, kind='application/json'):
            data = body if isinstance(body, bytes) else json.dumps(body, ensure_ascii=False).encode()
            self.send_response(code)
            self.send_header('Content-Type', kind + '; charset=utf-8')
            self.send_header('Cache-Control', 'no-store')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def local(self):
            host = self.headers.get('Host', '')
            return host.startswith('127.0.0.1:') or host.startswith('localhost:')

        def do_GET(self):
            if not self.local():
                return self.send(403, {'error': 'host'})
            if self.path == '/':
                return self.send(200, page.replace('__TOKEN__', token).encode(), 'text/html')
            if self.path == '/api/status':
                return self.send(200, console.view())
            self.send(404, {'error': 'not found'})

        def do_POST(self):
            if not self.local() or self.headers.get('X-Console-Token') != token:
                return self.send(403, {'error': 'token'})
            body = json.loads(self.rfile.read(int(self.headers.get('Content-Length') or 0)) or b'{}')
            actions = {
                '/api/check': ('重新核對', console.check),
                '/api/plan': ('切換計畫', lambda: console.make_plan(body.get('target'))),
                '/api/confirm': ('寫入並切換', console.do_switch),
                '/api/cancel': None,
                '/api/quit': None,
                '/api/sim/start': ('開始模擬', lambda: console.sim_start(body.get('takeoff', 'manual'))),
                '/api/sim/restart': ('從地面重來', console.sim_restart),
                '/api/sim/end': ('結束並存記錄', console.sim_end),
            }
            if self.path not in actions:
                return self.send(404, {'error': 'not found'})
            if self.path == '/api/quit':
                console.quit.set()
                return self.send(200, {'ok': True})
            if self.path == '/api/cancel':
                with console.state_lock:
                    console.plan = None
                return self.send(200, {'ok': True})
            if self.path == '/api/plan' and body.get('target') not in ('hitl', 'flight'):
                return self.send(400, {'error': 'target'})
            name, fn = actions[self.path]
            try:
                console.start(name, fn)
            except Stop as exc:
                return self.send(409, {'error': str(exc)})
            self.send(200, {'ok': True})
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    parser.add_argument('--units', type=Path, default=UNITS_FILE,
                        help='the units file (default deploy/units.json; format: hitl/console/units.example.json)')
    parser.add_argument('--port', type=int, default=8765)
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    if WORK_CPUS:  # the console and what it runs (readbacks, deploys) off the isolated CPUs
        os.sched_setaffinity(0, WORK_CPUS)
        print(f'CPU：控制台 {cpu_text(WORK_CPUS)}（不含隔離的核心），HITL 主程式 {OWNER_CPU}', flush=True)
    else:
        print('CPU：這台沒有隔離的核心，不綁定', flush=True)
    lock = qs.one_session()  # noqa: F841 - held until the process ends
    out = qs.cache() / 'console' / time.strftime('%Y%m%d_%H%M%S')
    out.mkdir(parents=True, exist_ok=True)
    console = Console(out, args.units.expanduser().resolve())
    for problem in console.setup['problems']:
        print('飛控清單：' + problem, flush=True)
    if console.setup['problems']:
        print(HOWTO, flush=True)
    token = secrets.token_urlsafe(16)
    page = (HERE / 'console.html').read_text().replace('__TITLE__', html.escape(console.setup['title']))
    server = ThreadingHTTPServer(('127.0.0.1', args.port), handler(console, token, page))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    threading.Thread(target=console.poll, daemon=True).start()
    url = f'http://127.0.0.1:{args.port}/'
    print(f'控制台：{url}（網頁上的「關閉控制台」、關掉這個視窗或按 Ctrl-C 都會結束：停模擬、關 QGC、打開 QGC 的'
          '自動連線、關 HITL 主程式；只關瀏覽器不會結束）', flush=True)
    console.start('開始', console.check)  # without a units file it stops at once with the how-to
    if not args.no_browser:
        subprocess.Popen(['xdg-open', url], stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL, start_new_session=True)

    def stop(signum, frame):
        console.quit.set()
    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, stop)
    while not console.quit.wait(1):  # a timeout keeps the main thread able to take signals
        pass
    for sig in (signal.SIGINT, signal.SIGTERM, signal.SIGHUP):
        signal.signal(sig, signal.SIG_IGN)  # the cleanup finishes even if the window is closed now
    console.closing = True
    print('\n結束中…', flush=True)
    console.busy.acquire(timeout=600)  # let a running operation finish
    code = 0
    try:
        if console.sim:
            console.op = {'name': '結束', 'log': [], 'done': False, 'error': None, 'started': time.time()}
            console.sim_end()
    except Exception as exc:  # noqa: BLE001
        print(f'模擬沒有正常結束：{exc}；照 hitl/README 的恢復規則處理', flush=True)
        code = 3
    if not console.qgc_restore():
        code = code or 4
    s = qs.status() or {}
    if code == 0 and s and not s.get('recovery_required') and s.get('model') != 'running':
        qs.runbridge('shutdown', timeout=60)
        print('HITL 主程式已關閉', flush=True)
    server.shutdown()
    return code


if __name__ == '__main__':
    sys.exit(main())
