#!/usr/bin/env python3
"""Put a deploy recipe on a flight controller: firmware, parameters, boot file and logger topics. Format: docs/recipes.md.

    <python with pymavlink> tools/deploy.py <recipe> --link /dev/serial/by-id/<the FC>             plan: nothing written
    <python with pymavlink> tools/deploy.py <recipe> --link ... --reuse      the FC runs this firmware: parameters, SD
    <python with pymavlink> tools/deploy.py <recipe> --link ... --flash      build if needed, flash, parameters, SD

The plan reads the FC (identity, every parameter, the two SD files) and says what would change. --reuse and --flash
then:

1. Flash (--flash only). The image must be the one firmware.json records (tools/px4build.py builds it when the
   patches or modules changed). An old boot file that is not the recipe's is removed first: the new firmware runs it
   on its first boot. PX4's own uploader (<PX4 tree>/Tools/px4_uploader.py) writes the image, with one retry for a
   board left in its bootloader. Then the FC must report the recipe's identity (board, PX4 hash, NuttX hash), which
   is recorded in firmware.json "flashed", and the board record (~/.cache/px4-llm-sim2hitl/v2/boards/<uid>.json)
   notes which image went onto this board.
   --reuse needs proof that the board already runs this recipe's image. The identity the FC reports is not enough:
   it names the PX4 and NuttX commits only, so two recipes with the same patches but different external modules (or
   a changed module) report the same identity. So --reuse requires the image to be current (built from the recipe's
   present patches and modules), the identity to match, and the board record of this board (its uid) to name this
   image's SHA-256. A board flashed by another tool has no such record: flash it once with --flash.
2. Parameters. Only the recipe's "set" values are written, each confirmed by the FC with the same bytes. PX4 changes
   some parameters itself after others (an output function sets its PWM limits), so after the writes everything is
   read again and what still differs is written again (at most three rounds). A parameter the recipe does not state
   must be at its firmware default; PX4 itself sometimes writes one (EKF2 writes EKF2_SENS_EN back without bit 1
   when a sensor is switched by command), which the final check reports. --reset-unmanaged writes those back to
   their default, and the recipe's airframe and boot values that another recipe changed (PX4's airframe and board
   scripts set only defaults, so a value an earlier recipe set stays): moving an FC between recipes or vehicles needs it. Both are
   listed in the plan first.
3. SD files. The boot file (/fs/microsd/etc/extras.txt) and the logger topics (/fs/microsd/etc/logging/
   logger_topics.txt) are made to hold the recipe's file, or removed when the recipe has none: written to a
   temporary file, read back, then renamed.
4. One reboot, then the proof: every parameter read again and checked (Recipe.check, verdict PASS), and both SD
   files read again.

Refuses an armed FC, and an FC whose SYS_HITL differs from the recipe's (a HITL recipe goes only onto an FC that is
already in HITL; --allow-hitl-change when a person has made the aircraft safe: propellers off). Nothing is rolled back
on a failure: the report keeps the readback from before (params_before.json), which `tools/fc.py params-restore --from`
puts back.
Report: ~/.cache/px4-llm-sim2hitl/v2/deploy/<UTC>_<recipe>/report.json; the last line printed is its summary.
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mavftp  # noqa: E402
import px4build  # noqa: E402
from fc import FC, FCError  # noqa: E402
from recipe import KINDS, Recipe, load_firmware_params  # noqa: E402

CACHE = Path(os.environ.get('XDG_CACHE_HOME') or Path.home() / '.cache') / 'px4-llm-sim2hitl' / 'v2' / 'deploy'
BOARDS = CACHE.parent / 'boards'   # <uid>.json: the image the toolkit last flashed onto that board
SD_FILES = (mavftp.BOOT_FILE, mavftp.LOGGER_TOPICS)
FUNCTION = re.compile(r'_FUNC\d+$')
SETTLE_S = 1.5     # PX4 sets an output's PWM values up to about 1 s after its function changes


def utc():
    return datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def sha(data):
    return hashlib.sha256(data).hexdigest() if data is not None else None


class Deploy:
    def __init__(self, a):
        self.a = a
        self.recipe = Recipe(a.recipe, a.repo)
        self.run = CACHE / f'{time.strftime("%Y%m%d-%H%M%S", time.gmtime())}_{self.recipe.name}'
        self.run.mkdir(parents=True, exist_ok=True)
        self.mode = 'flash' if a.flash else 'reuse' if a.reuse else 'plan'
        self.fc_log = []
        self.report = {'recipe': str(self.recipe.dir), 'mode': self.mode, 'link': a.link, 'started_utc': utc(),
                       'steps': [], 'verdict': None, 'run': str(self.run)}
        self.fc = None

    def step(self, name, verdict, **details):
        self.report['steps'].append(dict({'step': name, 'verdict': verdict, 'time_utc': utc()}, **details))
        self.save()

    def save(self):
        self.report['fc_writes_and_commands'] = self.fc_log
        (self.run / 'report.json').write_text(json.dumps(self.report, indent=1, default=str) + '\n')

    def wanted_sd(self):
        return {mavftp.BOOT_FILE: self.recipe.boot_file.read_bytes() if self.recipe.boot_file else None,
                mavftp.LOGGER_TOPICS: self.recipe.logger_topics.read_bytes() if self.recipe.logger_topics else None}

    def connect(self):
        self.fc = FC(self.a.link, self.a.baud, log=self.fc_log).connect()
        return self.fc.identity()

    def readback(self, tag):
        names = load_firmware_params(self.recipe.firmware_params_path) if self.recipe.firmware_params_path.is_file() else ()
        rb = self.fc.read_all(names)
        path = self.run / f'params_{tag}.json'
        path.write_text(json.dumps(rb, indent=1) + '\n')
        return rb, path

    def sd_state(self):
        return {path: self.fc.sd_read(path, mavftp.PUT_MAX) for path in SD_FILES}

    def identity_problems(self, version):
        e = self.recipe.firmware_info.get('embedded') or {}
        problems = []
        if version.get('board_version') != self.recipe.expected_board_version():
            problems.append(f'board {version.get("board_version")}, recipe {self.recipe.expected_board_version()}')
        if version.get('git_hash_prefix') != e.get('git_hash', '')[:10]:
            problems.append(f'PX4 hash {version.get("git_hash_prefix")}, recipe {e.get("git_hash", "")[:10]}')
        if e.get('nuttx_git_hash') and version.get('os_hash_prefix') != e['nuttx_git_hash'][:16]:
            problems.append(f'NuttX hash {version.get("os_hash_prefix")}, recipe {e["nuttx_git_hash"][:16]}')
        return problems

    def board_record(self, uid):
        path = BOARDS / f'{uid}.json'
        return json.loads(path.read_text()) if path.is_file() else None

    def reuse_problems(self, version):
        """Why the FC cannot be taken to run this recipe's image as it is (empty: it does)."""
        r = self.recipe
        problems = list(self.identity_problems(version))
        wanted, why = px4build.needs_build(r.repo, r.dir)
        if wanted:
            problems.append(f'the image is not built from the recipe as it is now ({why})')
        problems += r.local_problems()
        image = (r.firmware_info.get('outputs') or {}).get('firmware', {}).get('sha256')
        record = self.board_record(version.get('uid'))
        if record is None:
            problems.append(f'no record of what the toolkit flashed onto board {version.get("uid")}: flash it once '
                            '(--flash)')
        elif record.get('image_sha256') != image:
            problems.append(f'board {version.get("uid")} was last flashed with {record.get("recipe")} '
                            f'(image {str(record.get("image_sha256"))[:12]}), not this recipe\'s image {str(image)[:12]}')
        return problems

    def safe_to_write(self, version):
        if version.get('armed') is not False:
            raise FCError('the FC is armed (or its heartbeat says nothing): refusing to write')
        want = self.recipe.managed().get('SYS_HITL', (0,))[0]   # unstated: the firmware default, 0 (not in HITL)
        have = self.fc.get('SYS_HITL')
        if have != want and not self.a.allow_hitl_change:
            raise FCError(f'SYS_HITL is {have} on the FC and {want} in the recipe: --allow-hitl-change only when a '
                          'person has made the aircraft safe')
        return have

    # -- the steps -----------------------------------------------------------------------------------------------------
    def plan(self):
        r = self.recipe
        for path, data in self.wanted_sd().items():
            if data is not None:
                problems = mavftp.WRITABLE[path](data)
                if problems:
                    raise ValueError(f'{path} of the recipe: ' + '; '.join(problems))
        version = self.connect()
        wanted, why = px4build.needs_build(r.repo, r.dir)
        before, path = self.readback('before')
        check = r.check(before) if r.firmware_params_path.is_file() else {'verdict': 'no firmware parameter list'}
        sd = self.sd_state()
        writes = [w for w in check.get('wrong_value', []) if w['section'] == 'set']
        self.step('plan', 'PASS', fc=version, fc_runs_recipe_firmware=not self.identity_problems(version),
                  reuse_problems=self.reuse_problems(version),
                  identity_problems=self.identity_problems(version), build=('needed: ' + why) if wanted else why,
                  readback=str(path), check_verdict=check['verdict'], writes=len(writes),
                  checked_not_written=[w for w in check.get('wrong_value', []) if w['section'] != 'set'],
                  not_default=check.get('not_default', [])[:20],
                  sd={p: {'fc': sha(sd[p]), 'recipe': sha(d)} for p, d in self.wanted_sd().items()})
        return version, before, sd

    def flash(self, sd):
        r = self.recipe
        wanted, why = px4build.needs_build(r.repo, r.dir)
        if wanted:
            self.step('build', 'PASS', **px4build.build(r.dir, r.repo))
            r = self.recipe = Recipe(r.dir, r.repo)
        problems = r.local_problems()
        if problems:
            raise RuntimeError('local recipe files: ' + '; '.join(problems))
        boot = self.wanted_sd()[mavftp.BOOT_FILE]
        if sd[mavftp.BOOT_FILE] is not None and sd[mavftp.BOOT_FILE] != boot:
            self.fc.sd_replace(mavftp.BOOT_FILE, None)
            self.step('old boot file removed', 'PASS', sha256=sha(sd[mavftp.BOOT_FILE]))
        uploader = px4build.px4_root(self.a.px4_root) / 'Tools' / 'px4_uploader.py'
        if not uploader.is_file():
            raise RuntimeError(f'{uploader} not found (PX4 v1.18 or later)')
        port = os.path.realpath(self.a.link)
        self.fc.close()
        attempts = []
        for attempt in (1, 2):
            log = self.run / f'flash_{attempt}.log'
            try:
                res = subprocess.run([sys.executable, str(uploader), '--noninteractive', '--port', port, str(r.image)],
                                     capture_output=True, text=True, timeout=300)
                text, code = res.stdout + res.stderr, res.returncode
            except subprocess.TimeoutExpired as exc:
                text, code = str(exc.stdout or '') + str(exc.stderr or ''), 'timeout'
            log.write_text(text)
            ok = code == 0 and 'Uploaded in' in text
            attempts.append({'attempt': attempt, 'exit': code, 'uploaded': ok, 'log': str(log)})
            if ok:
                break
            time.sleep(2)
            if attempt == 1 and any(re.search(r'bootloader|-BL', p.name, re.I) for p in Path('/dev/serial/by-id').glob('*')):
                continue   # the first try sometimes stops in the bootloader; the board waits there
            break
        if not attempts[-1]['uploaded']:
            raise RuntimeError(f'flash failed: {attempts}; nothing retried further, the FC may need hands on it')
        time.sleep(5)
        version = self.connect()
        problems = self.identity_problems(version)
        if problems:
            raise RuntimeError('after flashing the FC does not report the recipe firmware: ' + '; '.join(problems))
        info = json.loads(r.firmware_info_path.read_text())
        info['flashed'] = {'status': 'PASS', 'at_utc': utc(), 'tool': 'px4-llm-sim2hitl tools/deploy.py',
                           'uploader': f'<PX4 tree>/Tools/px4_uploader.py --noninteractive --port {port} {r.image.name}',
                           'attempts': len(attempts),
                           'after': {k: version.get(k) for k in ('px4_version', 'git_hash_prefix', 'os_hash_prefix',
                                                                 'board_version')},
                           'uid': version.get('uid'), 'image_sha256': info['outputs']['firmware']['sha256'],
                           'evidence': str(self.run).replace(str(Path.home()), '~')}
        r.firmware_info_path.write_text(json.dumps(info, indent=2, ensure_ascii=False) + '\n')
        BOARDS.mkdir(parents=True, exist_ok=True)
        (BOARDS / f'{version.get("uid")}.json').write_text(json.dumps({
            'uid': version.get('uid'), 'board_version': version.get('board_version'), 'recipe': r.name,
            'recipe_dir': str(r.dir), 'repo': str(r.repo), 'image': r.image.name,
            'image_sha256': info['outputs']['firmware']['sha256'], 'git_hash_prefix': version.get('git_hash_prefix'),
            'os_hash_prefix': version.get('os_hash_prefix'), 'flashed_utc': utc(), 'run': str(self.run)}, indent=1) + '\n')
        self.step('flash', 'PASS', attempts=attempts, fc=version)
        return version

    def write_params(self):
        firmware = load_firmware_params(self.recipe.firmware_params_path)
        written = []
        for round_ in range(1, 4):
            rb, path = self.readback(f'round{round_}')
            check = self.recipe.check(rb)
            blocking = {k: check[k] for k in ('local_mismatch', 'identity', 'structure', 'unknown_name',
                                              'not_in_firmware', 'fc_owned_set_changed') if check[k]}
            if blocking:
                raise RuntimeError(f'readback {path.name}: ' + json.dumps(blocking, default=str)[:800])
            todo = [w for w in check['wrong_value'] if w['section'] == 'set']
            if self.a.reset_unmanaged:
                todo += [{'name': n['name'], 'fc': n['fc'], 'expected': n['default'], 'section': 'default'}
                         for n in check['not_default']]
                # an airframe or board-script value another recipe set: PX4's scripts change only defaults (or set the
                # value again at every boot), so a value stored by an earlier recipe stays
                todo += [w for w in check['wrong_value'] if w['section'] in ('airframe', 'boot')]
            if not todo:
                self.step('parameters', 'PASS', rounds=round_ - 1, written=written)
                return written
            todo.sort(key=lambda w: 0 if FUNCTION.search(w['name']) else 1)   # functions first: PX4 acts on them
            for w in todo:
                kind = KINDS[firmware[w['name']]['type']]
                self.fc.set(w['name'], kind, w['expected'])
                written.append({'round': round_, 'name': w['name'], 'from': w['fc'], 'to': w['expected'],
                                'why': w['section']})
                if FUNCTION.search(w['name']):
                    self.fc.drain(SETTLE_S)
            self.fc.drain(SETTLE_S)
        raise RuntimeError(f'parameters still differ after 3 rounds: {[w["name"] for w in todo]} (something on the '
                           'FC sets them back)')

    def write_sd(self):
        changed = []
        for path, data in self.wanted_sd().items():
            have = self.fc.sd_read(path, mavftp.PUT_MAX)
            if have == data:
                continue
            steps = self.fc.sd_replace(path, data)
            changed.append({'path': path, 'from': sha(have), 'to': sha(data), 'steps': steps})
        self.step('sd files', 'PASS', changed=changed)
        return changed

    def prove(self):
        version = self.fc.reboot()
        problems = self.identity_problems(version)
        if problems:
            raise RuntimeError('after the reboot: ' + '; '.join(problems))
        after, path = self.readback('after')
        check = self.recipe.check(after)
        (self.run / 'check.json').write_text(json.dumps(check, indent=1, default=str) + '\n')
        for p, data in self.wanted_sd().items():
            self.fc.sd_verify(p, data)
        problems = {k: check[k][:20] for k in ('wrong_value', 'not_default', 'not_read', 'structure', 'identity')
                    if check[k]}
        self.step('proof', check['verdict'], readback=str(path), check=str(self.run / 'check.json'),
                  sd_files='as the recipe', problems=problems, redundant_set_values=check['redundant'])
        if check['verdict'] != 'PASS':
            raise RuntimeError(f'final check {check["verdict"]}: see {self.run / "check.json"}')
        return version

    def go(self):
        try:
            version, before, sd = self.plan()
            if self.mode == 'plan':
                self.report['verdict'] = 'PLAN'
                return
            self.report['sys_hitl_before'] = self.safe_to_write(version)
            if self.mode == 'flash':
                self.flash(sd)
            else:
                problems = self.reuse_problems(version)
                if problems:
                    raise RuntimeError('--reuse, but it is not proven that the FC runs this recipe\'s image: '
                                       + '; '.join(problems) + ' (use --flash)')
            self.write_params()
            self.write_sd()
            self.report['fc_after'] = self.prove()
            self.report['verdict'] = 'PASS'
        except Exception as exc:  # noqa: BLE001  (every failure ends in the report)
            self.step('stopped', 'FAIL', error=f'{type(exc).__name__}: {exc}')
            self.report['verdict'] = 'FAIL'
        finally:
            if self.fc is not None:
                self.fc.close()
            self.report['finished_utc'] = utc()
            self.save()
        return self.report


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('recipe')
    p.add_argument('--link', required=True, help='the FC serial device (/dev/serial/by-id/...)')
    p.add_argument('--baud', type=int, default=2000000)
    p.add_argument('--repo', help='the vehicle repository (default: found from the recipe)')
    p.add_argument('--px4-root')
    g = p.add_mutually_exclusive_group()
    g.add_argument('--flash', action='store_true')
    g.add_argument('--reuse', action='store_true')
    p.add_argument('--allow-hitl-change', action='store_true')
    p.add_argument('--reset-unmanaged', action='store_true',
                   help='also write back every parameter the recipe does not state that differs from its default, and '
                        'the recipe\'s airframe and boot values another recipe changed (moving an FC between recipes or vehicles)')
    a = p.parse_args()
    d = Deploy(a)
    d.go()
    r = d.report
    print(json.dumps({'verdict': r['verdict'], 'mode': r['mode'], 'recipe': d.recipe.name, 'report': str(d.run / 'report.json'),
                      'steps': [(s['step'], s['verdict']) for s in r['steps']],
                      'error': next((s['error'] for s in r['steps'] if s['step'] == 'stopped'), None)}))
    sys.exit(0 if r['verdict'] in ('PASS', 'PLAN') else 1)


if __name__ == '__main__':
    main()
