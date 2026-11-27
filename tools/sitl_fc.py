#!/usr/bin/env python3
r"""A vehicle repository's SITL FC: PX4 SITL on the computer, built with a recipe's modules and started like the flight
controller that runs the recipe, for simhost's SITL FC transport (--sitl-udp, --mavlink-udp). See docs/sitl_fc.md.

    PATH="<PX4 Python environment>/bin:$PATH" python3 tools/sitl_fc.py build --recipe <repo>/deploy/<recipe> \
        [--patch FILE[:REPO]]... [--committer "NAME <EMAIL>"]
    python3 tools/sitl_fc.py start --recipe <repo>/deploy/<recipe> --instance N [--fresh]
    python3 tools/sitl_fc.py stop --instance N
    python3 tools/sitl_fc.py status --instance N
    python3 tools/sitl_fc.py restart --instance N

build: the PX4 of px4/lock.toml, target px4_sitl_default (lockstep: PX4's clock follows simhost's sensor time), with the
recipe's external modules (<repo>/modules/src/<name>), the toolkit's SITL patches (px4/patches/sitl/*.patch, every vehicle
needs them with simhost), then the vehicle repository's own (--patch), each committed with git am under --committer,
which sets the commit hashes PX4 reports). The recipe's own patches are not applied: they
change board files and NuttX, which the computer build does not use. Builds run in a tree of this tool's own
(--build-tree), copied once from --copy-from without its build outputs and reset to the lock before every build.
<cache>/builds/<recipe>/build.json records the inputs and their hashes; start refuses a build whose inputs changed.

start: an instance folder (<cache>/instances/N) keeps parameters, dataman, logs and the boot file across restarts, as an
FC keeps them across reboots; --fresh starts from an empty one (a new FC). The startup script is this tool's, not PX4's
posix rcS (see startup_script). A supervisor in the background runs PX4 and starts it again whenever it exits, or when
the file <instance>/restart appears (a reboot), until stop. Ports of instance N, UDP on 127.0.0.1: simulator PX4
24740+N <-> host 4560+N, MAVLink PX4 24640+N <-> host 24540+N.

Each command prints one JSON line. Standard library only.
"""
import argparse
import datetime
import fcntl
import json
import os
import re
import shutil
import signal
import socket
import subprocess
import sys
import time
import tomllib
from contextlib import contextmanager
from pathlib import Path

TOOLKIT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLKIT / 'tools'))
from recipe import SECTIONS, Recipe, is_int32, load_firmware_params, sha256  # noqa: E402

PX4_LOCK = tomllib.loads((TOOLKIT / 'px4' / 'lock.toml').read_text())['px4']
TARGET = 'px4_sitl_default'
CACHE = Path(os.environ.get('XDG_CACHE_HOME') or Path.home() / '.cache') / 'px4-llm-sim2hitl' / 'v2' / 'sitl_fc'
BUILD_TREE = Path(os.environ.get('SIM2HITL_SITL_BUILD_TREE')
                  or Path.home() / 'px4' / f'PX4-Autopilot-{PX4_LOCK["tag"]}-build-v2sitl')
def default_copy_from():
    """The PX4 tree a new build tree is copied from: SIM2HITL_PX4_ROOT, else ~/.config/px4-llm-sim2hitl/px4_root (the
    same lookup as tools/px4build.py); the copy is then reset to the lock's commit."""
    if os.environ.get('SIM2HITL_PX4_ROOT'):
        return Path(os.environ['SIM2HITL_PX4_ROOT']).expanduser()
    cfg = Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config') / 'px4-llm-sim2hitl' / 'px4_root'
    if cfg.is_file() and cfg.read_text().strip():
        return Path(cfg.read_text().strip()).expanduser()
    return Path.home() / 'px4' / f'PX4-Autopilot-{PX4_LOCK["tag"]}'


COPY_FROM = default_copy_from()
COMMITTER = 'sim2hitl build <build@sim2hitl.invalid>'
OWNED_VALUES = 'sitl/sitl_fc_owned.json'   # in the vehicle repository

# Values that stand for the FC on the computer, unless the recipe states them: PX4's commander measures CPU load in wall
# time, which says nothing about the FC when lockstep runs faster than real time (seen 2026-11-27: "Preflight Fail: CPU
# load too high: 100.0%" refused arming); PX4's own posix rcS sets the same (ROMFS init.d-posix/rcS, v1.18.0 line 158).
SITL_DEFAULTS = {'COM_CPU_MAX': (-1, 'SITL: the computer\'s CPU load is not the FC\'s (PX4 posix rcS sets the same)')}
# The HIL outputs of a recipe (pwm_out_sim -m hil, HIL_ACT_*) on the SITL outputs (pwm_out_sim -m sim, PWM_MAIN_*).
OUTPUT_RENAME = {f'HIL_ACT_FUNC{n}': f'PWM_MAIN_FUNC{n}' for n in range(1, 17)}
OUTPUT_RENAME['HIL_ACT_REV'] = 'PWM_MAIN_REV'
# The device ids of simulator_mavlink's sensors (PX4's posix rcS sets the same on a new SITL instance).
SIM_DEVICES = {'CAL_ACC0_ID': 1310988, 'CAL_GYRO0_ID': 1310988, 'CAL_MAG0_ID': 197388, 'CAL_MAG0_PRIO': 50,
               'SENS_BOARD_X_OFF': 0.000001, 'SENS_DPRES_OFF': 0.001}
# Lockstep: PX4's MAVLink streams count simulated seconds, so at N x real time every MAVLink user would get N times the
# messages per wall second. The link starts in mode minimal with these streams (per simulated second); HEARTBEAT,
# STATUSTEXT, commands, parameters, missions and logs are sent in every mode. --stream adds or changes one.
STREAMS = {'ATTITUDE': 10, 'VFR_HUD': 10, 'LOCAL_POSITION_NED': 10, 'ATTITUDE_TARGET': 10, 'GLOBAL_POSITION_INT': 5,
           'SYS_STATUS': 1, 'EXTENDED_SYS_STATE': 1}


def utc():
    return datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')


def ports(instance):
    return {'sim_host': 4560 + instance, 'sim_px4': 24740 + instance, 'mavlink_host': 24540 + instance,
            'mavlink_px4': 24640 + instance}


def simhost_args(instance):
    p = ports(instance)
    return ['--sitl-udp', f'{p["sim_host"]}:{p["sim_px4"]}', '--mavlink-udp', f'{p["mavlink_host"]}:{p["mavlink_px4"]}',
            '--lockstep']


def git(path, *args, env=None):
    r = subprocess.run(['git', '-C', str(path), *args], capture_output=True, text=True, env=env)
    if r.returncode:
        raise SystemExit(f'git {" ".join(args)} in {path} failed: {r.stderr.strip()[-800:]}')
    return r.stdout.strip()


def repo_state(path):
    r = subprocess.run(['git', '-C', str(path), 'rev-parse', 'HEAD'], capture_output=True, text=True)
    if r.returncode:
        return None
    dirty = subprocess.run(['git', '-C', str(path), 'status', '--porcelain'], capture_output=True, text=True).stdout
    return {'commit': r.stdout.strip(), 'dirty': bool(dirty.strip())}


# -- build -------------------------------------------------------------------------------------------------------------
def tree_problems(tree):
    problems = []
    head = git(tree, 'rev-parse', 'HEAD')
    if head != PX4_LOCK['commit']:
        problems.append(f'HEAD {head} is not the lock commit {PX4_LOCK["commit"]}')
    if git(tree, 'status', '--porcelain'):
        problems.append('uncommitted or untracked changes')
    bad = [line for line in git(tree, 'submodule', 'status', '--recursive').splitlines() if line[:1] in '+-U']
    if bad:
        problems.append(f'{len(bad)} submodules not at their recorded commit: {bad[:3]}')
    return problems


def reset_tree(tree, copy_from):
    """The build tree at the lock commit with clean submodules. Made once as a copy of copy_from (objects included, no
    network) without its build outputs; the source is only read."""
    if not tree.exists():
        if not (copy_from / '.git').exists():
            raise SystemExit(f'{copy_from} is not a PX4 git tree to copy the build tree from (--copy-from)')
        partial = tree.with_name(tree.name + '.partial')
        subprocess.run(['rsync', '-a', '--delete', '--exclude=/build/', f'{copy_from}/', f'{partial}/'], check=True)
        partial.rename(tree)
    git(tree, 'checkout', '-q', '--detach', '--force', PX4_LOCK['commit'])
    git(tree, 'submodule', 'update', '-q', '--init', '--recursive', '--force')
    git(tree, 'submodule', 'foreach', '-q', '--recursive', 'git reset -q --hard && git clean -fdq')
    git(tree, 'clean', '-fdq')
    problems = tree_problems(tree)
    if problems:
        raise SystemExit(f'build tree {tree} does not match the lock after the reset: {problems}')
    return tree


def parse_committer(text):
    m = re.fullmatch(r'\s*(.+?)\s*<([^<>\s]+)>\s*', text)
    if not m:
        raise SystemExit(f'--committer must be "NAME <EMAIL>", not {text!r}')
    return m.group(1), m.group(2)


def parse_patch(spec, repo):
    file, _, sub = spec.partition(':')
    path = Path(file) if Path(file).is_absolute() else repo / file
    if not path.is_file():
        raise SystemExit(f'patch {path} not found')
    return {'file': file, 'repo': sub or '.', 'path': path}


def apply_patches(tree, patches, committer):
    """Each patch committed in its repository inside the PX4 tree with git am: author and date from the patch, committer
    from --committer, committer date = author date. The same patches on the same commit give the same hashes."""
    name, email = parse_committer(committer)
    env = dict(os.environ, GIT_COMMITTER_NAME=name, GIT_COMMITTER_EMAIL=email)
    ident = ['-c', f'user.name={name}', '-c', f'user.email={email}']
    applied = []
    for p in patches:
        repo = tree / p['repo']
        r = subprocess.run(['git', '-C', str(repo), *ident, 'am', '-q', '--committer-date-is-author-date', str(p['path'])],
                           capture_output=True, text=True, env=env)
        if r.returncode:
            subprocess.run(['git', '-C', str(repo), 'am', '--abort'], capture_output=True, env=env)
            raise SystemExit(f'patch {p["file"]} does not apply in {p["repo"]}: {r.stderr.strip()[-800:]}')
        applied.append({'file': p['file'], 'repo': p['repo'], 'sha256': sha256(p['path']),
                        'commit': git(repo, 'rev-parse', 'HEAD')})
    return applied


def module_files(repo, name):
    """SHA-256 of every file of a module folder by its path inside it (subfolders too)."""
    base = Path(repo) / 'modules' / 'src' / name
    return {p.relative_to(base).as_posix(): sha256(p) for p in sorted(base.rglob('*'))
            if p.is_file() and '__pycache__' not in p.parts}


def external_modules(work, repo, modules):
    """An EXTERNAL_MODULES_LOCATION with only this recipe's modules (links into the vehicle repository)."""
    ext = work / 'ext'
    if ext.exists():
        shutil.rmtree(ext)
    (ext / 'src').mkdir(parents=True)
    for name in modules:
        source = Path(repo) / 'modules' / 'src' / name
        if not (source / 'CMakeLists.txt').is_file():
            raise SystemExit(f'module {name} not found in {source.parent}')
        (ext / 'src' / name).symlink_to(source)
    listing = '\n'.join('\t' + name for name in modules)
    (ext / 'src' / 'CMakeLists.txt').write_text(f'set(config_module_list_external\n{listing}\n\tPARENT_SCOPE\n)\n')
    return ext


@contextmanager
def build_lock():
    CACHE.mkdir(parents=True, exist_ok=True)
    with open(CACHE / 'build.lock', 'w') as f:
        try:
            fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            print(json.dumps({'status': 'WAITING', 'why': 'another build runs in the build tree'}), flush=True)
            fcntl.flock(f, fcntl.LOCK_EX)
        yield


def build_dir(recipe):
    """A recipe's SITL FC build, per vehicle repository: two repositories may have recipes of the same name."""
    return CACHE / 'builds' / recipe.repo.name / recipe.name


def cmd_build(a):
    recipe = Recipe(a.recipe, a.repo)
    build_recipe = recipe.build_recipe or {}
    modules = build_recipe.get('modules', [])
    lock = json.loads((recipe.repo / 'sim2hitl.lock').read_text()) if (recipe.repo / 'sim2hitl.lock').is_file() else {}
    if a.committer is None:   # the vehicle repository's, as tools/px4build.py takes it
        c = (lock.get('firmware_build') or {}).get('committer')
        a.committer = f'{c["name"]} <{c["email"]}>' if c else COMMITTER
    patches = sitl_patches(recipe, lock, a.patch)
    parse_committer(a.committer)
    probe = subprocess.run(['python3', '-c', 'import em, jinja2, yaml'], capture_output=True)
    if probe.returncode:
        raise SystemExit('python3 in PATH lacks the PX4 build modules (empy, jinja2, pyyaml): put the PX4 Python '
                         'environment first in PATH')
    out = build_dir(recipe)
    out.mkdir(parents=True, exist_ok=True)
    previous = json.loads((out / 'build.json').read_text()) if (out / 'build.json').is_file() else None
    with build_lock():
        tree = reset_tree(Path(a.build_tree).expanduser().resolve(), Path(a.copy_from).expanduser().resolve())
        applied = apply_patches(tree, patches, a.committer)
        module_hashes = {name: module_files(recipe.repo, name) for name in modules}   # before the build: what it compiles
        suffix = f'_{recipe.repo.name}_{recipe.name}'   # per repository: two may have recipes of the same name
        cmd = ['make', TARGET, f'BUILD_DIR_SUFFIX={suffix}']
        if modules:
            cmd.append(f'EXTERNAL_MODULES_LOCATION={external_modules(out, recipe.repo, modules)}')
        (out / 'logs').mkdir(exist_ok=True)
        log = out / 'logs' / f'build_{time.strftime("%Y%m%d_%H%M%S")}.log'
        # PX4's switch to leave the submodules as they are (Tools/check_submodules.sh): the tree was reset above and the
        # patches are committed on purpose. CI=true would reset them.
        env = dict(os.environ, GIT_SUBMODULES_ARE_EVIL='1')
        env.pop('CI', None)
        started = time.monotonic()
        with open(log, 'w') as f:
            code = subprocess.run(cmd, cwd=tree, stdout=f, stderr=subprocess.STDOUT, env=env).returncode
        seconds = round(time.monotonic() - started, 1)
        if code:
            print(json.dumps({'status': 'FAIL', 'recipe': str(recipe.dir), 'exit': code, 'log': str(log)}))
            raise SystemExit(code)
        outdir = tree / 'build' / (TARGET + suffix)
        listing = outdir / 'parameters.json.xz'
        shutil.copy2(listing, out / listing.name)
        px4 = outdir / 'bin' / 'px4'
        info = {
            'schema_version': 1, 'recipe': recipe.name, 'recipe_dir': str(recipe.dir), 'vehicle_repo': str(recipe.repo),
            'vehicle_repo_state': repo_state(recipe.repo), 'target': TARGET, 'lockstep': True,
            'px4': {'tag': PX4_LOCK['tag'], 'lock_commit': PX4_LOCK['commit'], 'build_tree': str(tree),
                    'git_hash': git(tree, 'rev-parse', 'HEAD'), 'git_describe': git(tree, 'describe', '--always', '--tags')},
            'committer': a.committer, 'patches': applied, 'explicit_patches': bool(a.patch),
            'recipe_patches_not_applied': build_recipe.get('patches', []),
            'modules': module_hashes,
            'build_dir': str(outdir), 'binary': {'path': str(px4), 'sha256': sha256(px4)},
            'parameters': {'file': listing.name, 'sha256': sha256(out / listing.name),
                           'count': len(load_firmware_params(out / listing.name))},
            'command': ' '.join(cmd), 'built_at_utc': utc(), 'seconds': seconds, 'log': str(log),
            'toolkit': repo_state(TOOLKIT),
        }
    (out / 'build.json').write_text(json.dumps(info, indent=2) + '\n')
    replaced = previous['recipe_dir'] if previous and previous.get('recipe_dir') != info['recipe_dir'] else None
    print(json.dumps({'status': 'PASS', 'recipe': str(recipe.dir), 'build': str(out / 'build.json'), 'px4': str(px4),
                      'git_hash': info['px4']['git_hash'], 'parameters': info['parameters']['count'], 'seconds': seconds,
                      'log': str(log), **({'replaced_build_of': replaced} if replaced else {})}))


def sitl_patches(recipe, lock, explicit=None):
    """The patches a SITL FC build gets, in order: the toolkit's own (px4/patches/sitl/, fixes every vehicle needs with
    simhost), then the vehicle repository's (--patch, else sim2hitl.lock sitl_build)."""
    specs = explicit or (lock.get('sitl_build') or {}).get('patches', [])
    patches = [parse_patch(str(f), TOOLKIT) | {'file': f'toolkit:{f.relative_to(TOOLKIT)}'}
               for f in sorted((TOOLKIT / 'px4' / 'patches' / 'sitl').glob('*.patch'))]
    patches += [parse_patch(s, recipe.repo) for s in specs]
    names = [p['path'].name for p in patches]
    if len(set(names)) != len(names):
        raise SystemExit(f'a SITL patch is given twice (the toolkit applies px4/patches/sitl/ itself): {names}')
    return patches


def build_problems(recipe, build):
    """Why a build no longer matches the recipe: empty when it is current."""
    problems = []
    lock = json.loads((recipe.repo / 'sim2hitl.lock').read_text()) if (recipe.repo / 'sim2hitl.lock').is_file() else {}
    if not build.get('explicit_patches'):   # built with the default list: it must still be the default list
        want = [(p['file'], p['repo']) for p in sitl_patches(recipe, lock)]
        have = [(p['file'], p.get('repo', '.')) for p in build['patches']]
        if want != have:
            problems.append(f'the SITL patches are now {[w[0] for w in want]}, the build has {[h[0] for h in have]}')
    if build.get('recipe_dir') != str(recipe.dir) or build.get('vehicle_repo') != str(recipe.repo):
        problems.append(f'built from {build.get("recipe_dir")} of {build.get("vehicle_repo")}')
    if build['px4']['lock_commit'] != PX4_LOCK['commit']:
        problems.append(f'built at PX4 {build["px4"]["lock_commit"]}, the lock is {PX4_LOCK["commit"]}')
    modules = (recipe.build_recipe or {}).get('modules', [])
    if sorted(build['modules']) != sorted(modules):
        problems.append(f'modules {sorted(build["modules"])} built, the recipe has {sorted(modules)}')
    for name in modules:
        if name in build['modules'] and module_files(recipe.repo, name) != build['modules'][name]:
            problems.append(f'module {name} changed')
    for p in build['patches']:
        if p['file'].startswith('toolkit:'):   # the toolkit's own SITL patches (px4/patches/sitl/)
            path = TOOLKIT / p['file'][len('toolkit:'):]
        else:
            path = Path(p['file']) if Path(p['file']).is_absolute() else recipe.repo / p['file']
        if not path.is_file() or sha256(path) != p['sha256']:
            problems.append(f'patch {p["file"]} changed or missing')
    px4 = Path(build['binary']['path'])
    if not px4.is_file() or sha256(px4) != build['binary']['sha256']:
        problems.append(f'{px4} missing or built again since build.json')
    listing = build_dir(recipe) / build['parameters']['file']
    if not listing.is_file() or sha256(listing) != build['parameters']['sha256']:
        problems.append(f'{listing} missing or changed')
    return problems


def load_build(recipe):
    path = build_dir(recipe) / 'build.json'
    if not path.is_file():
        raise SystemExit(f'no SITL FC build of {recipe.name}: run tools/sitl_fc.py build --recipe {recipe.dir}')
    return json.loads(path.read_text())


# -- start -------------------------------------------------------------------------------------------------------------
def instance_dir(instance):
    return CACHE / 'instances' / str(instance)


def value_text(name, value, firmware):
    kind = firmware[name]['type']
    if kind == 'Int32':
        if not is_int32(value):
            raise SystemExit(f'{name} is Int32 in the SITL build, the value {value!r} is not')
        return str(int(value))
    return repr(float(value))


def derive(recipe, build, out):
    """The recipe as the SITL FC runs it, in the instance folder (tools/recipe.py reads it like any recipe): the HIL
    output functions on the SITL outputs, the parameters the computer build does not have left out (listed in its
    params.json "sitl"), the SITL build's parameter list and identity (AUTOPILOT_VERSION on posix: board version 1, no
    NuttX). Returns (Recipe of it, the SITL build's parameter list)."""
    if out.exists():
        shutil.rmtree(out)
    (out / 'firmware').mkdir(parents=True)
    listing = build_dir(recipe) / build['parameters']['file']
    shutil.copy2(listing, out / 'firmware' / listing.name)
    firmware = load_firmware_params(out / 'firmware' / listing.name)
    params = json.loads(recipe.params_path.read_text())
    left_out = []
    for section in SECTIONS:
        kept = {}
        # Own names first, renamed HIL outputs after: they win over the recipe's PWM_MAIN_* (a recipe may set those for
        # the FC's real outputs; on the computer they are the simulated ones).
        for name, entry in sorted(params.get(section, {}).items(), key=lambda item: item[0] in OUTPUT_RENAME):
            target = OUTPUT_RENAME.get(name, name)
            if target != name:
                entry = dict(entry, why=f'SITL: {name} of the recipe on the SITL outputs ({entry.get("why", "")})')
            if target not in firmware:
                left_out.append({'name': name, 'section': section})
                continue
            kept[target] = entry
        params[section] = kept
    for name in OUTPUT_RENAME.values():   # a renamed output is in set: drop it from the other sections
        if name in params['set']:
            for section in ('airframe', 'boot', 'verify_only'):
                params[section].pop(name, None)
    stated = {n for section in SECTIONS for n in params.get(section, {})}
    for name, (value, why) in SITL_DEFAULTS.items():
        if name in firmware and name not in stated:
            params['boot'][name] = {'value': value, 'why': why}
    rule = re.compile('|'.join(params['fc_owned']['patterns']))
    params['fc_owned']['resolved_names'] = sorted(n for n in firmware if rule.search(n))
    params['fc_owned']['resolved_count'] = len(params['fc_owned']['resolved_names'])
    params['firmware'] = 'firmware/firmware.json'
    params['firmware_params'] = {'file': 'firmware/' + listing.name, 'sha256': build['parameters']['sha256']}
    params['sitl'] = {'recipe': str(recipe.dir), 'vehicle_repo': str(recipe.repo), 'target': build['target'],
                      'lockstep': True, 'left_out': left_out, 'renamed': OUTPUT_RENAME}
    (out / 'params.json').write_text(json.dumps(params, indent=2, ensure_ascii=False) + '\n')
    px4 = Path(build['binary']['path'])
    try:   # for the identity check only: PX4 runs from its build folder (its commands are links next to it)
        os.link(px4, out / 'firmware' / 'px4')
    except OSError:
        shutil.copy2(px4, out / 'firmware' / 'px4')
    info = {'schema_version': 1, 'sitl': True,
            'outputs': {'firmware': {'file': 'px4', 'sha256': sha256(out / 'firmware' / 'px4')},
                        'parameters': {'file': listing.name, 'sha256': build['parameters']['sha256']}},
            'embedded': {'board_id': 0, 'board_version': 1, 'git_hash': build['px4']['git_hash'], 'nuttx_git_hash': None},
            'build': {k: build[k] for k in ('target', 'built_at_utc', 'modules', 'patches', 'committer')}}
    (out / 'firmware' / 'firmware.json').write_text(json.dumps(info, indent=2) + '\n')
    if (recipe.dir / 'hitl.json').is_file():
        shutil.copy2(recipe.dir / 'hitl.json', out / 'hitl.json')
    if (recipe.dir / 'sd').is_dir():
        shutil.copytree(recipe.dir / 'sd', out / 'sd')
    return Recipe(out, recipe.repo), firmware


def vehicle_type(etc, params):
    """VEHICLE_TYPE of the recipe's airframe (SYS_AUTOSTART), as its rc.<type>_defaults sets it, or None."""
    entry = next((params.get(s, {}).get('SYS_AUTOSTART') for s in SECTIONS if 'SYS_AUTOSTART' in params.get(s, {})), None)
    if entry is None:
        return None
    files = sorted((etc / 'init.d' / 'airframes').glob(f'{int(entry["value"])}_*'))
    m = re.search(r'rc\.(\w+)_defaults', files[0].read_text()) if files else None
    defaults = etc / 'init.d' / f'rc.{m.group(1)}_defaults' if m else None
    m = re.search(r'^\s*set\s+VEHICLE_TYPE\s+(\w+)', defaults.read_text(), re.M) if defaults and defaults.is_file() else None
    return m.group(1) if m else None


def load_owned_values(recipe, option, firmware):
    """The physical FC's own values (fc_owned: RC calibration and mapping, ...) that the SITL FC stands in for, from a
    file of the vehicle repository ({"values": {NAME: VALUE}}). Only fc_owned names; names the build lacks are left
    out. Returns (values, record)."""
    path = Path(option or OWNED_VALUES)
    path = path if path.is_absolute() else recipe.repo / path
    if not path.is_file():
        if option:
            raise SystemExit(f'{path} not found (--fc-owned-values)')
        return {}, {'file': None, 'why': f'no {OWNED_VALUES} in the vehicle repository'}
    values = json.loads(path.read_text())['values']
    rule = re.compile('|'.join(recipe.params['fc_owned']['patterns']))
    managed = [n for n in values if not rule.search(n)]
    if managed:
        raise SystemExit(f'{path}: {managed} are not fc_owned in {recipe.dir}: the recipe states them')
    left_out = sorted(n for n in values if n not in firmware)
    return ({n: v for n, v in values.items() if n in firmware},
            {'file': str(path), 'sha256': sha256(path), 'count': len(values) - len(left_out), 'left_out': left_out})


def startup_script(derived, firmware, instance, vtype, owned, owned_file, streams):
    """The instance's rcS: the flight controller's HITL apps (rcS, rc.vehicle_setup, rc.logging), not PX4's posix rcS,
    which sets SITL defaults the FC does not have. Parameters: the recipe's airframe, boot and verify_only values as
    defaults (the FC's airframe and board scripts set them so), its set values written (as the toolkit writes them to an
    FC), the simulated devices and the physical FC's own values as defaults. SYS_HITL stays 1 and commander runs with
    -h, as on the FC in HITL. The differences to the FC: simulator_mavlink (UDP) instead of the HIL messages on the FC's
    MAVLink link, outputs on PWM_MAIN_* (pwm_out_sim -m sim), the MAVLink link on UDP, system_power_simulator for the
    board's power reading, the boot file at <instance>/fs/microsd/etc/extras.txt."""
    p = ports(instance)
    params = derived.params
    lines = [
        '#!/bin/sh',
        f'# SITL FC instance {instance} of {params["sitl"]["recipe"]}',
        '# Written by tools/sitl_fc.py of px4-llm-sim2hitl (docs/sitl_fc.md): the FC\'s HITL apps, not PX4\'s posix rcS.',
        'set +e',
        '. px4-alias.sh',
        f'set VEHICLE_TYPE {vtype}',
        'set LOGGER_ARGS ""',
        'set LOGGER_BUF 1000',
        'param select parameters.bson',
        'if [ -f parameters.bson ]; then param import; fi',
        'param select-backup parameters_backup.bson',
        '# The recipe\'s airframe, boot and verify_only values: defaults, as the FC\'s airframe and board scripts set them',
    ]
    for section in ('airframe', 'boot', 'verify_only'):
        for name, entry in sorted(params.get(section, {}).items()):
            lines.append(f'param set-default {name} {value_text(name, entry["value"], firmware)}  # {section}')
    lines.append('# The simulated sensors of simulator_mavlink')
    for name, value in SIM_DEVICES.items():
        lines.append(f'param set-default {name} {value_text(name, value, firmware)}')
    if owned:
        lines.append(f'# The physical FC\'s own values (fc_owned): {owned_file}')
        for name, value in sorted(owned.items()):
            lines.append(f'param set-default {name} {value_text(name, value, firmware)}')
    lines += ['param set-default SYS_HITL 1',
              '# The recipe\'s set values, written as the toolkit writes them to an FC']
    for name, entry in sorted(params.get('set', {}).items()):
        lines.append(f'param set {name} {value_text(name, entry["value"], firmware)}')
    mav = f'-u {p["mavlink_px4"]}'
    lines += [
        'param set MAV_SYS_ID 1',
        'dataman start',
        f'simulator_mavlink start -u {p["sim_px4"]}',
        'load_mon start',
        'system_power_simulator start',
        'rc_update start',
        'manual_control start',
        'sensors start',
        'commander start -h',
        'if param compare -s EKF2_EN 1',
        'then',
        '\tekf2 start &',
        'fi',
        'pwm_out_sim start -m sim',
        '. ${R}etc/init.d/rc.vehicle_setup',
        'navigator start',
        f'mavlink start -x {mav} -o {p["mavlink_host"]} -t 127.0.0.1 -r 4000000 -m minimal',
        *[f'mavlink stream {mav} -s {name} -r {rate}' for name, rate in streams.items()],
        '# The recipe\'s boot file, at the FC\'s path, then the logger, as in the FC\'s rcS',
        'if [ -f fs/microsd/etc/extras.txt ]; then . fs/microsd/etc/extras.txt; fi',
        'if param compare -s EKF2_EN 1',
        'then',
        '\tset LOGGER_ARGS "-p ekf2_timestamps"',
        'else',
        '\tset LOGGER_ARGS "-p vehicle_attitude"',
        'fi',
        '. ${R}etc/init.d/rc.logging',
        'mavlink boot_complete',
    ]
    return '\n'.join(lines) + '\n'


def prepare_etc(work, build_etc, topics):
    """<instance>/etc: PX4 links the working directory's etc to the build's ROMFS at every start, unless it is a real
    folder. A real folder of links to the build's entries, with a logging/ of the instance's own: the recipe's logger
    topics land where the logger reads them (PX4_STORAGEDIR/etc/logging/logger_topics.txt), and the build stays as it
    was built."""
    etc = work / 'etc'
    if etc.is_symlink():
        etc.unlink()
    etc.mkdir(exist_ok=True)
    for entry in etc.iterdir():
        if entry.is_symlink():
            entry.unlink()
        elif entry.name == 'logging' and entry.is_dir():
            shutil.rmtree(entry)
        else:
            raise SystemExit(f'{entry}: not made by this tool, move it away first')
    for source in build_etc.iterdir():
        if not (topics and source.name == 'logging'):
            (etc / source.name).symlink_to(source)
    if topics:
        (etc / 'logging').mkdir()
        shutil.copy2(topics, etc / 'logging' / 'logger_topics.txt')


def pid_of(path, *words):
    """The pid in path when that process runs and its command line has every word, else None (a stale pid file)."""
    try:
        pid = int(Path(path).read_text())
        cmdline = Path(f'/proc/{pid}/cmdline').read_bytes().split(b'\0')
    except (OSError, ValueError):
        return None
    args = [c.decode(errors='replace') for c in cmdline]
    return pid if all(any(w in arg for arg in args) for w in words) else None


def supervisor_pid(work, instance):
    return pid_of(work / 'supervisor.pid', 'sitl_fc.py', 'supervise', str(instance))


def px4_pid(work):
    return pid_of(work / 'px4.pid', str(work))


def px4_instance_running(instance):
    """PX4 holds a POSIX lock on /tmp/px4_lock-<instance> while it runs (platforms/posix main.cpp)."""
    path = Path(f'/tmp/px4_lock-{instance}')
    if not path.exists():
        return False
    fd = os.open(path, os.O_RDWR)
    try:
        fcntl.lockf(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        fcntl.lockf(fd, fcntl.LOCK_UN)
        return False
    except OSError:
        return True
    finally:
        os.close(fd)


def udp_free(port):
    with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as s:
        try:
            s.bind(('127.0.0.1', port))
            return True
        except OSError:
            return False


def cmd_start(a):
    recipe = Recipe(a.recipe, a.repo)
    build = load_build(recipe)
    problems = build_problems(recipe, build)
    if problems:
        raise SystemExit(f'the SITL FC build of {recipe.name} is stale ({"; ".join(problems)}): build it again')
    n = a.instance
    work = instance_dir(n)
    if supervisor_pid(work, n):
        raise SystemExit(f'SITL FC instance {n} is running (supervisor {supervisor_pid(work, n)}): stop it first')
    if px4_instance_running(n):
        raise SystemExit(f'a PX4 with instance number {n} runs on this computer (/tmp/px4_lock-{n}), not this tool\'s')
    busy = [port for port in (ports(n)['sim_px4'], ports(n)['mavlink_px4']) if not udp_free(port)]
    if busy:
        raise SystemExit(f'UDP ports {busy} of instance {n} are in use')
    previous = json.loads((work / 'sitl_fc.json').read_text()) if (work / 'sitl_fc.json').is_file() else None
    if a.fresh and work.exists():
        shutil.rmtree(work)
    work.mkdir(parents=True, exist_ok=True)
    derived, firmware = derive(recipe, build, work / 'recipe')
    build_etc = Path(build['build_dir']) / 'etc'
    vtype = a.vehicle_type or vehicle_type(build_etc, derived.params)
    if not vtype:
        raise SystemExit('the recipe\'s airframe (SYS_AUTOSTART) gives no VEHICLE_TYPE in the build: give --vehicle-type')
    owned, owned_record = load_owned_values(recipe, a.fc_owned_values, firmware)
    streams = dict(STREAMS)
    for spec in a.stream:
        name, _, rate = spec.partition('=')
        streams[name] = float(rate)
    (work / 'rcS').write_text(startup_script(derived, firmware, n, vtype, owned, owned_record['file'], streams))
    boot = work / 'fs' / 'microsd' / 'etc' / 'extras.txt'
    boot.parent.mkdir(parents=True, exist_ok=True)
    if derived.boot_file:   # put or removed, as a deploy does on the FC's SD card
        shutil.copy2(derived.boot_file, boot)
    else:
        boot.unlink(missing_ok=True)
    prepare_etc(work, build_etc, derived.logger_topics)
    info = {'schema_version': 1, 'instance': n, 'recipe': recipe.name, 'recipe_dir': str(recipe.dir),
            'vehicle_repo': str(recipe.repo), 'vehicle_repo_state': repo_state(recipe.repo),
            'derived_recipe': str(derived.dir), 'build': str(build_dir(recipe) / 'build.json'),
            'px4': build['binary']['path'], 'px4_sha256': build['binary']['sha256'], 'git_hash': build['px4']['git_hash'],
            'build_etc': str(build_etc), 'ports': ports(n), 'simhost_args': simhost_args(n), 'lockstep': True,
            'vehicle_type': vtype, 'fc_owned_values': owned_record, 'streams': streams,
            'boot_file': str(boot) if derived.boot_file else None,
            'logger_topics': str(work / 'etc' / 'logging' / 'logger_topics.txt') if derived.logger_topics else None,
            'left_out': derived.params['sitl']['left_out'], 'started_utc': utc(), 'toolkit': repo_state(TOOLKIT)}
    (work / 'sitl_fc.json').write_text(json.dumps(info, indent=1) + '\n')
    with open(work / 'supervisor.err', 'a') as err:
        proc = subprocess.Popen([sys.executable, '-B', str(Path(__file__).resolve()), 'supervise', '--instance', str(n)],
                                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=err, start_new_session=True)
    (work / 'supervisor.pid').write_text(str(proc.pid))
    pid = None
    for _ in range(100):
        pid = px4_pid(work)
        if pid or proc.poll() is not None:
            break
        time.sleep(0.1)
    time.sleep(1.0)
    if not px4_pid(work):
        raise SystemExit(f'PX4 did not stay up: see {work / "px4.log"} and {work / "supervisor.log"}')
    out = {'status': 'STARTED', 'instance': n, 'folder': str(work), 'recipe': str(recipe.dir), 'fresh': a.fresh,
           'supervisor_pid': proc.pid, 'px4_pid': pid, 'ports': ports(n), 'simhost_args': simhost_args(n),
           'left_out': [x['name'] for x in info['left_out']]}
    if previous and previous.get('recipe_dir') != str(recipe.dir) and not a.fresh:
        out['previous_recipe'] = previous.get('recipe_dir')   # its stored parameters are still in the instance
    print(json.dumps(out))


def stop_px4(proc, log, why):
    log.write(f'{utc()} {why}: SIGINT to PX4 pid {proc.pid}\n')
    log.flush()
    proc.send_signal(signal.SIGINT)
    try:
        proc.wait(10)
    except subprocess.TimeoutExpired:
        proc.kill()
        proc.wait()


def supervise(n):
    """Run PX4 until the file stop appears: a PX4 that exits is started again after 1 s. PX4 on the computer denies
    MAVLink's reboot and shutdown commands (Commander builds them only with CONFIG_BOARDCTL_RESET and
    BOARD_HAS_POWER_CONTROL), so a reboot comes from outside: the file restart stops PX4 first (400 ms later, as a
    flight controller resets 400 ms after it answers). A build changed since start is not started again."""
    work = instance_dir(n)
    info = json.loads((work / 'sitl_fc.json').read_text())
    px4, stop, restart = Path(info['px4']), work / 'stop', work / 'restart'
    stop.unlink(missing_ok=True)
    restart.unlink(missing_ok=True)
    signal.signal(signal.SIGTERM, lambda *_: stop.touch())
    with open(work / 'supervisor.log', 'a') as log:
        log.write(f'{utc()} supervisor {os.getpid()} for {info["recipe_dir"]}\n')
        while not stop.exists():
            if not px4.is_file() or sha256(px4) != info['px4_sha256']:
                log.write(f'{utc()} {px4} changed since start: not started again (start the instance again)\n')
                break
            with open(work / 'px4.log', 'a') as out:
                proc = subprocess.Popen([str(px4), '-d', '-i', str(n), '-w', str(work), '-s', str(work / 'rcS'),
                                         info['build_etc']], cwd=work, stdout=out, stderr=subprocess.STDOUT,
                                        stdin=subprocess.DEVNULL)
                (work / 'px4.pid').write_text(str(proc.pid))
                log.write(f'{utc()} PX4 pid {proc.pid} started\n')
                log.flush()
                while proc.poll() is None:
                    if restart.exists():
                        time.sleep(0.4)
                        restart.unlink(missing_ok=True)
                        stop_px4(proc, log, 'restart requested')
                    elif stop.exists():
                        stop_px4(proc, log, 'stop requested')
                    time.sleep(0.2)
            (work / 'px4.pid').unlink(missing_ok=True)
            log.write(f'{utc()} PX4 pid {proc.pid} exited {proc.returncode}\n')
            log.flush()
            if not stop.exists():
                time.sleep(1)
        log.write(f'{utc()} supervisor {os.getpid()} ends\n')
    (work / 'px4.pid').unlink(missing_ok=True)
    (work / 'supervisor.pid').unlink(missing_ok=True)


def wait_for(condition, seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if condition():
            return True
        time.sleep(0.1)
    return condition()


def cmd_stop(a):
    n, work = a.instance, instance_dir(a.instance)
    sup = supervisor_pid(work, n)
    killed = []
    if sup:
        (work / 'stop').touch()
        if not wait_for(lambda: not supervisor_pid(work, n), 25):
            os.kill(sup, signal.SIGKILL)
            killed.append(sup)
    left = px4_pid(work)   # a PX4 without its supervisor (it was killed)
    if left:
        os.kill(left, signal.SIGKILL)
        killed.append(left)
    stopped = not supervisor_pid(work, n) and not px4_pid(work)
    print(json.dumps({'status': 'STOPPED' if stopped else 'STILL RUNNING', 'instance': n, 'was_running': bool(sup),
                      **({'killed': killed} if killed else {})}))


def cmd_restart(a):
    n, work = a.instance, instance_dir(a.instance)
    if not supervisor_pid(work, n):
        raise SystemExit(f'SITL FC instance {n} is not running')
    old = px4_pid(work)
    (work / 'restart').touch()
    ok = wait_for(lambda: px4_pid(work) not in (None, old), 30)
    print(json.dumps({'status': 'RESTARTED' if ok else 'NOT RESTARTED', 'instance': n, 'old_px4_pid': old,
                      'px4_pid': px4_pid(work)}))


def cmd_status(a):
    n, work = a.instance, instance_dir(a.instance)
    info = json.loads((work / 'sitl_fc.json').read_text()) if (work / 'sitl_fc.json').is_file() else {}
    out = {'instance': n, 'folder': str(work), 'running': bool(supervisor_pid(work, n)),
           'supervisor_pid': supervisor_pid(work, n), 'px4_pid': px4_pid(work)}
    if info:
        try:
            recipe = Recipe(info['recipe_dir'], info['vehicle_repo'])
            out['build_problems'] = build_problems(recipe, load_build(recipe))
        except (OSError, ValueError, KeyError, SystemExit) as e:
            out['build_problems'] = [f'cannot check: {e}']
        out.update({k: info.get(k) for k in ('recipe_dir', 'started_utc', 'ports', 'simhost_args', 'git_hash',
                                              'vehicle_type', 'boot_file', 'logger_topics')})
    log = work / 'supervisor.log'
    out['supervisor_log'] = log.read_text().splitlines()[-4:] if log.is_file() else []
    print(json.dumps(out))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = p.add_subparsers(dest='action', required=True)
    b = sub.add_parser('build', help='build the recipe\'s SITL FC')
    b.add_argument('--recipe', required=True, help='recipe folder in a vehicle repository')
    b.add_argument('--repo', help='the vehicle repository (default: the folder above the recipe with sim2hitl.lock)')
    b.add_argument('--patch', action='append', default=[], metavar='FILE[:REPO]',
                   help='a SITL patch of the vehicle repository (path relative to it), applied in REPO of the PX4 tree '
                        '(default .); repeatable, in order (default: sim2hitl.lock "sitl_build": {"patches": [...]})')
    b.add_argument('--committer', help='git committer of the patch commits, "NAME <EMAIL>" (default: sim2hitl.lock '
                                       f'"firmware_build": {{"committer"}}, else "{COMMITTER}")')
    b.add_argument('--build-tree', default=str(BUILD_TREE), help=f'this tool\'s PX4 build tree (default {BUILD_TREE})')
    b.add_argument('--copy-from', default=str(COPY_FROM),
                   help=f'the PX4 tree the build tree is copied from once, only read (default {COPY_FROM})')
    s = sub.add_parser('start', help='start an instance of the recipe\'s SITL FC')
    s.add_argument('--recipe', required=True)
    s.add_argument('--repo')
    s.add_argument('--instance', type=int, required=True)
    s.add_argument('--fresh', action='store_true', help='start from an empty instance folder (a new FC)')
    s.add_argument('--fc-owned-values', help=f'file of the physical FC\'s own values, relative to the vehicle repository '
                                             f'(default {OWNED_VALUES}, if it exists)')
    s.add_argument('--vehicle-type', help='VEHICLE_TYPE for rc.vehicle_setup (default: from the airframe)')
    s.add_argument('--stream', action='append', default=[], metavar='NAME=RATE',
                   help='a MAVLink stream and its rate per simulated second, added to the defaults; repeatable')
    for name, text in (('stop', 'stop an instance'), ('status', 'state of an instance'),
                       ('restart', 'restart PX4 of an instance (a reboot)'), ('supervise', 'internal: the supervisor')):
        x = sub.add_parser(name, help=text)
        x.add_argument('--instance', type=int, required=True)
    a = p.parse_args()
    if a.action == 'build':
        cmd_build(a)
    elif a.action == 'start':
        cmd_start(a)
    elif a.action == 'stop':
        cmd_stop(a)
    elif a.action == 'restart':
        cmd_restart(a)
    elif a.action == 'status':
        cmd_status(a)
    else:
        supervise(a.instance)


if __name__ == '__main__':
    main()
