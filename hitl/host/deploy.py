"""Stage 3 in one command: firmware -> FC -> parameters -> boot file -> hitl-run.

  ./runbridge deploy-test --release deploy/<name>            plan only: what the FC has now, what would happen
  ./runbridge deploy-test --release deploy/<name> --flash    build if needed, flash, deploy, test
  ./runbridge deploy-test --release deploy/<name> --reuse    the FC already runs this firmware: deploy, test
  ./runbridge flash --release deploy/<name>                  only the flash step, with its checks
  --no-hitl stops after the boot file.
The report's "scope" says what its PASS covers: deployment and flight (hitl-run), deployment only (--no-hitl: not
flown), flash only (no parameters, boot file or flight), or the plan (nothing written).

Without --flash or --reuse nothing is changed: the plan says what the FC runs now and what would happen, so the
person decides (refresh or reuse). A failed step stops the later steps; restoring and the report still happen
(parameter deploy and boot-file changes restore themselves on failure). Flashing runs PX4's own
Tools/px_uploader.py of the checked PX4 tree with the owner shut down (the uploader needs the serial port): the
board must be the same FC, unarmed, HITL on and with no recovery pending; the old boot file is removed first
when it is not this recipe's (the new firmware runs it on its first boot); a board left in its bootloader is
retried once; anything else stops. The owner is restarted afterwards and the FC's identity (board, PX4 and NuttX
hash) is compared with the recipe before anything else is written. Report: <cache>/deploy_runs/<run>/report.json.
"""

import datetime
import hashlib
import json
import subprocess
import sys
import time
import uuid
from pathlib import Path

from .ipc import cache_root, request

BOOT = '/fs/microsd/etc/extras.txt'
# The logger topic list (host/sd_files.py LOGGER_TOPICS): a recipe's sd/etc/logging/logger_topics.txt is put on the
# card; a recipe without one gets the card's removed (the logger then follows SDLOG_PROFILE). Added 2026-11-21.
LOGGER_TOPICS = '/fs/microsd/etc/logging/logger_topics.txt'


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def utc():
    return datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


class Owner:
    """The runtime owner seen from this client: calls, start (detached) and shutdown."""

    def __init__(self, runtime, log):
        self.runtime, self.log = Path(runtime), log

    def call(self, action, arguments=None, timeout_s=45):
        response = request(self.runtime, action, arguments, timeout_s=timeout_s)
        with self.log.open('a') as stream:
            stream.write(json.dumps({'time': utc(), 'action': action, 'arguments': arguments, 'response': response},
                                    default=str) + '\n')
        if response.get('status') != 'complete':
            raise RuntimeError(f'{action} failed: {response.get("error") or response.get("operation", {}).get("error")}')
        return response.get('result') if 'result' in response else response.get('operation', {}).get('result')

    def status(self):
        return self.call('status')

    def running(self):
        try:
            self.status()
            return True
        except (OSError, RuntimeError, ValueError):
            return False

    def start(self, out):
        project = self.runtime.parent
        stream = open(out / 'owner.log', 'a')
        subprocess.Popen([str(project / 'runbridge'), 'bridge'], cwd=project, stdout=stream, stderr=subprocess.STDOUT,
                         stdin=subprocess.DEVNULL, start_new_session=True)
        return self.wait_verified(90)

    def wait_verified(self, seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            try:
                s = self.status()
                if (s.get('fc') or {}).get('state') == 'verified':
                    return s
            except (OSError, RuntimeError, ValueError):
                pass
            time.sleep(1)
        raise RuntimeError(f'owner not ready with a verified FC within {seconds} s')

    def shutdown(self):
        self.call('shutdown', {'force': False}, timeout_s=60)
        end = time.monotonic() + 30
        while time.monotonic() < end and self.running():
            time.sleep(0.5)
        if self.running():
            raise RuntimeError('owner did not exit after shutdown')


def ready_to_write(status):
    """The conditions of every FC write: a verified, unarmed FC with HITL on, model stopped, nothing pending."""
    fc = status.get('fc') or {}
    problems = []
    if fc.get('state') != 'verified':
        problems.append('FC not verified')
    if fc.get('armed') is not False:
        problems.append(f'FC armed state {fc.get("armed")}')
    if fc.get('SYS_HITL') != 1:
        problems.append(f'SYS_HITL {fc.get("SYS_HITL")} (HITL must be on)')
    if status.get('model') == 'running':
        problems.append('model running')
    if status.get('recovery_required'):
        problems.append('recovery pending')
    if status.get('param_deploy_pending'):
        problems.append('parameter deploy pending')
    return problems


def recipe_matches(project, version):
    """Deploy recipes whose recorded firmware identity matches what the FC reports. The board counts too: the
    native firmware of two boards has the same PX4 and NuttX hashes (board_version: deploy/check_params.py)."""
    sys.path.insert(0, str(Path(project) / 'deploy'))
    from check_params import expected_board_version

    names = []
    for path in sorted((Path(project) / 'deploy').glob('*/firmware/firmware.json')):
        embedded = json.loads(path.read_text()).get('embedded') or {}
        if not embedded or version.get('git_hash_prefix') != (embedded.get('git_hash') or '')[:10]:
            continue
        if version.get('board_version') != expected_board_version(embedded):
            continue
        if embedded.get('nuttx_git_hash') and version.get('os_hash_prefix') != embedded['nuttx_git_hash'][:16]:
            continue
        names.append(path.parents[1].name)
    return names


def needs_build(project, release):
    info = json.loads((release / 'firmware' / 'firmware.json').read_text())
    recipe = info.get('recipe')
    if not recipe:
        return False, 'prebuilt firmware'
    outputs = info.get('outputs') or {}
    image = release / 'firmware' / ((outputs.get('firmware') or {}).get('file') or 'missing')
    if not image.is_file() or sha256(image) != outputs['firmware']['sha256']:
        return True, 'no built image matching firmware.json'
    build = info.get('build') or {}
    recorded = {p['file']: p['sha256'] for p in build.get('patches', [])}
    if recorded != {p['file']: sha256(Path(project) / p['file']) for p in recipe.get('patches', [])}:
        return True, 'patches changed'
    modules = {name: {p.name: sha256(p) for p in sorted((Path(project) / 'modules' / 'src' / name).glob('*')) if p.is_file()}
               for name in recipe.get('modules', [])}
    if modules != build.get('modules', {}):
        return True, 'modules changed'
    return False, 'built image is current'


def checker(project):
    sys.path.insert(0, str(Path(project) / 'deploy'))
    import check_params

    return check_params


def fc_state(owner, project, release, out):
    """What the FC runs now: readback identity (with this recipe's parameter list), its SD boot file and logger
    topic list."""
    readback = owner.call('param-readback', {'out': str(out), 'release': str(release)}, timeout_s=600)
    version = json.loads(Path(readback['path']).read_text()).get('autopilot_version') or {}
    listing = owner.call('sd-list', {'sd_path': '/fs/microsd/etc'}, timeout_s=120)
    boot = None
    if any(e.get('name') == 'extras.txt' for e in listing.get('entries', [])):
        got = owner.call('sd-get', {'sd_path': BOOT, 'out': str(out / 'sd')}, timeout_s=120)
        boot = got.get('sha256')
    topics = None
    listing = owner.call('sd-list', {'sd_path': '/fs/microsd/etc/logging'}, timeout_s=120)
    if any(e.get('name') == 'logger_topics.txt' for e in listing.get('entries', [])):
        got = owner.call('sd-get', {'sd_path': LOGGER_TOPICS, 'out': str(out / 'sd')}, timeout_s=120)
        topics = got.get('sha256')
    return {'readback': readback['path'], 'autopilot_version': version, 'matches': recipe_matches(project, version),
            'boot_file_sha256': boot, 'logger_topics_sha256': topics}


def bootloader_present():
    from serial.tools import list_ports
    from .serial_helpers import BOOTLOADER_LABEL

    return [p.device for p in list_ports.comports()
            if BOOTLOADER_LABEL.search(f'{p.description or ""} {p.product or ""}')]


def flash_firmware(owner, project, release, out, report):
    """Shut the owner down, run px_uploader (one retry for a board left in its bootloader), restart the owner and
    compare the FC's identity with the recipe. Returns the flash record."""
    sys.path.insert(0, str(Path(project) / 'px4'))
    from check_px4_tree import px4_root
    from . import serial_helpers

    out.mkdir(parents=True, exist_ok=True)
    info_path = release / 'firmware' / 'firmware.json'
    info = json.loads(info_path.read_text())
    image = release / 'firmware' / info['outputs']['firmware']['file']
    if sha256(image) != info['outputs']['firmware']['sha256']:
        raise RuntimeError(f'{image} differs from firmware.json')
    uploader = px4_root() / 'Tools' / 'px_uploader.py'
    devices = serial_helpers.devices()
    port = next((d.path for d in devices if d.priority == 0), devices[0].path if devices else None)
    if not port:
        raise RuntimeError('no FC serial device found')
    owner.shutdown()
    attempts = []
    for attempt in (1, 2):
        log = out / f'flash_{attempt}.log'
        try:
            result = subprocess.run([sys.executable, str(uploader), '--port', port, str(image)], capture_output=True,
                                    text=True, timeout=300)
            text, code = result.stdout + result.stderr, result.returncode
        except subprocess.TimeoutExpired as exc:
            text, code = (exc.stdout or '') + (exc.stderr or '') if isinstance(exc.stdout, str) else '', 'timeout'
        log.write_text(text)
        ok = code == 0 and 'Verify' in text and 'Rebooting' in text
        attempts.append({'attempt': attempt, 'exit': code, 'verified_and_rebooting': ok, 'log': str(log)})
        if ok:
            break
        time.sleep(2)
        if attempt == 1 and bootloader_present():
            continue  # known: the first try sometimes fails at the bootloader; the board waits there
        break
    report['flash_attempts'] = attempts
    if not attempts[-1]['verified_and_rebooting']:
        raise RuntimeError(f'flash failed (attempts: {attempts}); the FC may need hands on it, nothing retried further')
    time.sleep(5)
    owner.start(out)
    state = fc_state(owner, project, release, out / 'after_flash')
    check = checker(project).check(release, state['readback'])
    identity = [p for p in check['identity'] if p.get('kind') in ('fail', 'incomplete')]
    if identity:
        raise RuntimeError(f'after flashing the FC does not report this firmware: {identity}')
    record = {'status': 'PASS', 'at_utc': utc(), 'port': port, 'tool': f'<PX4 tree>/Tools/px_uploader.py --port {port} {image.name}',
              'attempts': len(attempts), 'after': {k: state['autopilot_version'].get(k) for k in
                                                   ['flight_sw_version', 'git_hash_prefix', 'os_hash_prefix', 'board_version']},
              'evidence': str(out).replace(str(Path.home()), '~')}
    info['flashed'] = record
    info_path.write_text(json.dumps(info, indent=2, ensure_ascii=False) + '\n')
    return record


def run_deploy(runtime, args):
    runtime = Path(runtime).resolve()
    project = runtime.parent
    release = Path(args.release).resolve() if args.release else None
    if not release or not (release / 'params.json').is_file():
        raise ValueError('--release deploy/<name> (a folder with params.json) is required')
    run = cache_root() / 'deploy_runs' / f'run_{time.strftime("%Y%m%d_%H%M%SZ", time.gmtime())}_{uuid.uuid4().hex[:8]}'
    run.mkdir(parents=True)
    owner = Owner(runtime, run / 'operations.jsonl')
    mode = 'flash' if args.flash else 'reuse' if args.reuse else 'plan'
    if args.action == 'flash':
        mode = 'flash-only'
    # What a PASS of this run covers: a deployment PASS is not a flight PASS.
    scope = ('plan: nothing written' if mode == 'plan' else 'flash only: no parameters, boot file or flight'
             if mode == 'flash-only' else 'deployment only (--no-hitl): not flown' if args.no_hitl
             else 'deployment and flight (hitl-run)')
    report = {'schema_version': 1, 'release': str(release), 'mode': mode, 'scope': scope, 'created_utc': utc(),
              'steps': [], 'verdict': None}
    path = run / 'report.json'

    def step(name, verdict, **details):
        report['steps'].append(dict({'step': name, 'verdict': verdict}, **details))
        path.write_text(json.dumps(report, indent=2, default=str))

    boot_local = release / 'sd' / 'etc' / 'extras.txt'
    topics_local = release / 'sd' / 'etc' / 'logging' / 'logger_topics.txt'
    try:
        if not owner.running():
            owner.start(run)
        status = owner.status()
        before = fc_state(owner, project, release, run / 'before')
        wanted, why = needs_build(project, release)
        step('plan', 'PASS', fc_runs=before['matches'] or ['unknown firmware'], fc_version=before['autopilot_version'],
             fc_boot_file_sha256=before['boot_file_sha256'], recipe=release.name,
             recipe_boot_file_sha256=sha256(boot_local) if boot_local.is_file() else None,
             fc_logger_topics_sha256=before['logger_topics_sha256'],
             recipe_logger_topics_sha256=sha256(topics_local) if topics_local.is_file() else None,
             build=('needed: ' + why) if wanted else why, owner_conditions=ready_to_write(status) or 'ready')
        if mode == 'plan':
            report['verdict'] = 'PLAN'
            return report, path
        problems = ready_to_write(status)
        if problems:
            raise RuntimeError('not ready for FC writes: ' + '; '.join(problems))
        if mode == 'reuse' and release.name not in before['matches']:
            raise RuntimeError(f'--reuse, but the FC reports {before["matches"] or "unknown firmware"}, not {release.name}')
        if mode in ('flash', 'flash-only'):
            if wanted:
                result = subprocess.run([sys.executable, str(project / 'px4' / 'build_firmware.py'), '--release',
                                         str(release)], capture_output=True, text=True)
                (run / 'build.out').write_text(result.stdout + result.stderr)
                if result.returncode:
                    raise RuntimeError('firmware build failed: ' + (result.stdout + result.stderr).strip()[-600:])
                step('build', 'PASS', output=json.loads(result.stdout.strip().splitlines()[-1]))
            # The new firmware runs the SD boot file on its first boot: an old one that is not this recipe's goes first.
            local = sha256(boot_local) if boot_local.is_file() else None
            if before['boot_file_sha256'] and before['boot_file_sha256'] != local:
                removed = owner.call('sd-rm', {'sd_path': BOOT, 'out': str(run / 'sd')}, timeout_s=1800)
                if removed.get('verdict') != 'PASS':
                    raise RuntimeError(f'removing the old boot file: {removed.get("verdict")}')
                step('old_boot_file_removed', 'PASS', result=removed)
            step('flash', 'PASS', **flash_firmware(owner, project, release, run / 'flash', report))
            if mode == 'flash-only':
                report['verdict'] = 'PASS'
                return report, path
        deployed = owner.call('param-deploy', {'out': str(run / 'params'), 'release': str(release)}, timeout_s=1800)
        if deployed.get('verdict') != 'PASS':
            raise RuntimeError(f'parameter deploy {deployed.get("verdict")}')
        step('params', 'PASS', writes=len(deployed.get('writes') or []), transaction=deployed.get('transaction'))
        if boot_local.is_file():
            put = owner.call('sd-put', {'sd_path': BOOT, 'file': str(boot_local), 'out': str(run / 'sd')}, timeout_s=1800)
            if put.get('verdict') != 'PASS':
                raise RuntimeError(f'boot file {put.get("verdict")}')
            step('boot_file', 'PASS', result=put)
        elif before['boot_file_sha256'] and mode == 'reuse':
            removed = owner.call('sd-rm', {'sd_path': BOOT, 'out': str(run / 'sd')}, timeout_s=1800)
            if removed.get('verdict') != 'PASS':
                raise RuntimeError(f'removing the boot file {removed.get("verdict")}')
            step('boot_file_removed', 'PASS', result=removed)
        if topics_local.is_file():
            put = owner.call('sd-put', {'sd_path': LOGGER_TOPICS, 'file': str(topics_local), 'out': str(run / 'sd')},
                             timeout_s=1800)
            if put.get('verdict') != 'PASS':
                raise RuntimeError(f'logger topic list {put.get("verdict")}')
            step('logger_topics', 'PASS', result=put)
        elif before['logger_topics_sha256']:
            removed = owner.call('sd-rm', {'sd_path': LOGGER_TOPICS, 'out': str(run / 'sd')}, timeout_s=1800)
            if removed.get('verdict') != 'PASS':
                raise RuntimeError(f'removing the logger topic list {removed.get("verdict")}')
            step('logger_topics_removed', 'PASS', result=removed)
        if args.no_hitl:
            report['verdict'] = 'PASS'
            return report, path
        # The recipe's own flight action and judgement of its module (deploy/<name>/hitl.json), if it has them.
        hitl = json.loads((release / 'hitl.json').read_text()) if (release / 'hitl.json').is_file() else {}
        extra = [x for key in ('after', 'check') if hitl.get(key) for x in (f'--{key}', hitl[key])]
        result = subprocess.run([str(project / 'runbridge'), 'hitl-run', '--release', str(release), *extra], cwd=project,
                                capture_output=True, text=True)
        (run / 'hitl_run.out').write_text(result.stdout + result.stderr)
        line = next((x for x in reversed(result.stdout.strip().splitlines()) if x.startswith('{')), '{}')
        hitl = json.loads(line)
        step('hitl_run', hitl.get('verdict') or 'FAIL', manifest=hitl.get('manifest'), reasons=hitl.get('reasons'))
        report['verdict'] = hitl.get('verdict') or 'FAIL'
    except Exception as exc:  # noqa: BLE001 - every failure ends in the report
        step('stopped', 'FAIL', error=f'{type(exc).__name__}: {exc}')
        report['verdict'] = 'FAIL'
        if not owner.running():
            try:
                owner.start(run)
                step('owner_restarted', 'PASS')
            except Exception as again:  # noqa: BLE001
                step('owner_restarted', 'FAIL', error=str(again))
    finally:
        try:
            report['fc_after'] = owner.status() if owner.running() else None
        except Exception:  # noqa: BLE001
            report['fc_after'] = None
        report['finished_utc'] = utc()
        path.write_text(json.dumps(report, indent=2, default=str))
    return report, path
