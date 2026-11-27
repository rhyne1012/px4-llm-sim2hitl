#!/usr/bin/env python3
"""Build the firmware of a deploy recipe: a pinned PX4 commit, the recipe's committed patches, and its external
modules. The format is docs/recipes.md.

    python3 tools/px4build.py <recipe folder> [--repo <vehicle repository>] [--px4-root <PX4 tree>]

The recipe's firmware/firmware.json says what to build:

    "recipe": {"make_target": "cubepilot_cubeorangeplus_hil",
               "patches": [{"file": "px4/patches/<x>.patch", "repo": "."}],       # repo: a folder in the PX4 tree
               "modules": ["my_controller"]},                                      # folders of <repository>/modules/src
    "px4": {"tag": "v1.18.0", "commit": "<40 hex digits>"}      # must be the toolkit's px4/lock.toml commit

The user's PX4 tree (--px4-root, SIM2HITL_PX4_ROOT or ~/.config/px4-llm-sim2hitl/px4_root) is never changed. Builds
run in a build tree next to it (<tree>-build-sim2hitl, or SIM2HITL_PX4_BUILD_TREE), copied from it once and reset to
the recipe's commit, with clean submodules, before every build. Each patch is committed in its repository with
`git am`, with a fixed committer and the committer date set to the author date, so the same patches give the same
commits: the firmware then reports a PX4 (and NuttX) hash that tells it apart from the native one, and the deploy
check compares it. The committer is the vehicle repository's (sim2hitl.lock "firmware_build": {"committer": {"name",
"email"}}); changing it changes the hash of every recipe with a patch.

Writes the image (.px4) and its parameter list next to firmware.json, records in firmware.json the outputs, the
identity the FC will report (embedded), the build, and clears "flashed"; records the list's SHA-256 in params.json.
Prints one JSON line.
"""
import argparse
import base64
import datetime
import fcntl
import hashlib
import json
import lzma
import os
import shutil
import subprocess
import sys
import time
import tomllib
import zlib
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from recipe import find_repo  # noqa: E402

TOOLKIT_PX4 = tomllib.loads((Path(__file__).resolve().parents[1] / 'px4' / 'lock.toml').read_text())['px4']
DEFAULT_COMMITTER = {'name': 'sim2hitl build', 'email': 'build@sim2hitl.invalid'}
CACHE = Path(os.environ.get('XDG_CACHE_HOME') or Path.home() / '.cache') / 'px4-llm-sim2hitl' / 'v2' / 'firmware'


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def px4_root(explicit=None):
    if explicit:
        return Path(explicit).expanduser().resolve()
    if os.environ.get('SIM2HITL_PX4_ROOT'):
        return Path(os.environ['SIM2HITL_PX4_ROOT']).expanduser().resolve()
    cfg = Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config') / 'px4-llm-sim2hitl' / 'px4_root'
    if cfg.is_file() and cfg.read_text().strip():
        return Path(cfg.read_text().strip()).expanduser().resolve()
    raise SystemExit('PX4 tree unknown: --px4-root, SIM2HITL_PX4_ROOT or ~/.config/px4-llm-sim2hitl/px4_root')


def git(tree, *args, env=None):
    result = subprocess.run(['git', '-C', str(tree), *args], capture_output=True, text=True, env=env)
    if result.returncode:
        raise SystemExit(f'git {" ".join(args)} in {tree} failed: {result.stderr.strip()[-800:]}')
    return result.stdout.strip()


def portable(text, source, tree):
    """A recorded path or command without this machine's folders."""
    return (str(text).replace(str(tree), '<PX4 build tree>').replace(str(source), '<PX4 tree>')
            .replace(str(Path.home()), '~'))


def committer_of(repo):
    lock = Path(repo) / 'sim2hitl.lock'
    if lock.is_file():
        c = (json.loads(lock.read_text()).get('firmware_build') or {}).get('committer')
        if c:
            return {'name': c['name'], 'email': c['email']}
    return dict(DEFAULT_COMMITTER)


def hold_tree_lock(source):
    """One build at a time in the build tree (a reset or a build of another run would trample this one): the lock is
    held until the returned file is closed, or the process ends."""
    tree = Path(os.environ.get('SIM2HITL_PX4_BUILD_TREE') or str(source) + '-build-sim2hitl')
    f = open(str(tree) + '.lock', 'w')
    try:
        fcntl.flock(f, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        print(json.dumps({'status': 'WAITING', 'why': f'another build runs in {tree}'}), file=sys.stderr, flush=True)
        fcntl.flock(f, fcntl.LOCK_EX)
    return f


def build_tree(source, commit):
    """The build tree, reset to commit with clean submodules (the user's tree is only the source of the copy)."""
    tree = Path(os.environ.get('SIM2HITL_PX4_BUILD_TREE') or str(source) + '-build-sim2hitl')
    if not tree.exists():
        subprocess.run(['rsync', '-a', '--exclude=/build/', f'{source}/', f'{tree}/'], check=True)
    git(tree, 'checkout', '-q', '--detach', '--force', commit)
    git(tree, 'submodule', 'update', '-q', '--init', '--recursive', '--force')
    git(tree, 'submodule', 'foreach', '-q', '--recursive', 'git reset -q --hard && git clean -fdq')
    git(tree, 'clean', '-fdq', '-e', '/build/')
    if git(tree, 'rev-parse', 'HEAD') != commit:
        raise SystemExit(f'build tree is not at {commit} after the reset')
    dirty = git(tree, 'status', '--porcelain', '--ignore-submodules=none', '--untracked-files=no')
    if dirty:
        raise SystemExit('build tree not clean after the reset: ' + dirty[:400])
    return tree


def apply_patches(repo, tree, patches, committer):
    who = ['-c', f'user.name={committer["name"]}', '-c', f'user.email={committer["email"]}']
    env = dict(os.environ, GIT_COMMITTER_NAME=committer['name'], GIT_COMMITTER_EMAIL=committer['email'])
    applied = []
    for patch in patches:
        target, file = tree / patch['repo'], Path(repo) / patch['file']
        result = subprocess.run(['git', '-C', str(target), *who, 'am', '-q', '--committer-date-is-author-date',
                                 str(file)], capture_output=True, text=True, env=env)
        if result.returncode:
            subprocess.run(['git', '-C', str(target), *who, 'am', '--abort'], capture_output=True, env=env)
            raise SystemExit(f'patch {patch["file"]} does not apply in {patch["repo"]}: {result.stderr.strip()[-800:]}')
        applied.append({'file': patch['file'], 'sha256': sha256(file), 'repo': patch['repo'],
                        'commit': git(target, 'rev-parse', 'HEAD')})
    return applied


def module_files(repo, name):
    """SHA-256 of every file of a module folder (subfolders too), by its path inside it."""
    base = Path(repo) / 'modules' / 'src' / name
    return {p.relative_to(base).as_posix(): sha256(p) for p in sorted(base.rglob('*'))
            if p.is_file() and '__pycache__' not in p.parts}


def external_modules(repo, work, modules):
    """An EXTERNAL_MODULES_LOCATION holding only this recipe's modules (links into <repository>/modules/src)."""
    ext = work / 'ext'
    if ext.exists():
        shutil.rmtree(ext)
    (ext / 'src').mkdir(parents=True)
    for name in modules:
        source = Path(repo) / 'modules' / 'src' / name
        if not (source / 'CMakeLists.txt').is_file():
            raise SystemExit(f'module {name}: no {source}/CMakeLists.txt')
        (ext / 'src' / name).symlink_to(source)
    listing = '\n'.join('\t' + name for name in modules)
    (ext / 'src' / 'CMakeLists.txt').write_text(f'set(config_module_list_external\n{listing}\n\tPARENT_SCOPE\n)\n')
    return ext


def needs_build(repo, recipe_dir):
    """(build needed, why): no image matching firmware.json, or the patches or modules changed since the build."""
    info = json.loads((Path(recipe_dir) / 'firmware' / 'firmware.json').read_text())
    recipe = info.get('recipe')
    if not recipe:
        return False, 'prebuilt firmware'
    out = (info.get('outputs') or {}).get('firmware') or {}
    image = Path(recipe_dir) / 'firmware' / (out.get('file') or 'missing')
    if not image.is_file() or sha256(image) != out.get('sha256'):
        return True, 'no built image matching firmware.json'
    build = info.get('build') or {}
    recorded = {p['file']: p['sha256'] for p in build.get('patches', [])}
    if recorded != {p['file']: sha256(Path(repo) / p['file']) for p in recipe.get('patches', [])}:
        return True, 'patches changed'
    if {n: module_files(repo, n) for n in recipe.get('modules', [])} != build.get('modules', {}):
        return True, 'modules changed'
    return False, 'built image is current'


def build(recipe_dir, repo=None, px4=None):
    recipe_dir = Path(recipe_dir).resolve()
    repo = Path(repo).resolve() if repo else find_repo(recipe_dir)
    info_path = recipe_dir / 'firmware' / 'firmware.json'
    info = json.loads(info_path.read_text())
    recipe = info.get('recipe')
    if not recipe:
        raise SystemExit(f'{info_path} has no "recipe": a prebuilt firmware is not built here')
    commit = (info.get('px4') or {}).get('commit')
    if not commit or len(commit) != 40:
        raise SystemExit(f'{info_path}: "px4": {{"commit": <40 hex digits>}} is required')
    if commit != TOOLKIT_PX4['commit']:
        raise SystemExit(f'{info_path}: PX4 {commit[:10]}, but this toolkit is tested with {TOOLKIT_PX4["tag"]} '
                         f'({TOOLKIT_PX4["commit"][:10]}, px4/lock.toml)')
    source = px4_root(px4)
    committer = committer_of(repo)
    work = CACHE / repo.name / recipe_dir.name
    work.mkdir(parents=True, exist_ok=True)
    lock = hold_tree_lock(source)
    tree = build_tree(source, commit)
    applied = apply_patches(repo, tree, recipe.get('patches', []), committer)
    modules = recipe.get('modules', [])
    target, suffix = recipe['make_target'], '_' + recipe_dir.name
    cmd = ['make', target, f'BUILD_DIR_SUFFIX={suffix}']
    if modules:
        cmd.append(f'EXTERNAL_MODULES_LOCATION={external_modules(repo, work, modules)}')
    log = work / f'build_{time.strftime("%Y%m%d_%H%M%S")}.log'
    started = time.monotonic()
    # PX4's switch to leave submodules as they are (Tools/check_submodules.sh): the build tree was reset above and the
    # patches are committed in their submodules on purpose. CI=true would reset them.
    env = dict(os.environ, GIT_SUBMODULES_ARE_EVIL='1')
    env.pop('CI', None)
    with open(log, 'w') as out:
        code = subprocess.run(cmd, cwd=tree, stdout=out, stderr=subprocess.STDOUT, env=env).returncode
    seconds = round(time.monotonic() - started, 1)
    if code:
        print(json.dumps({'status': 'FAIL', 'recipe': str(recipe_dir), 'exit': code, 'log': str(log)}))
        raise SystemExit(code)
    outdir = tree / 'build' / (target + suffix)
    image, params = outdir / f'{target}.px4', outdir / 'parameters.json.xz'
    shutil.copy2(image, recipe_dir / 'firmware' / image.name)
    shutil.copy2(params, recipe_dir / 'firmware' / params.name)
    px4_image = json.loads(image.read_text())
    listing = json.loads(lzma.decompress(params.read_bytes()))['parameters']
    nuttx = tree / 'platforms' / 'nuttx' / 'NuttX' / 'nuttx'
    # AUTOPILOT_VERSION.board_version: PX4's px4_board_version() returns the USB product id (CONFIG_CDCACM_PRODUCTID),
    # not the image's board id. Pixhawk 6C: both 56; Cube Orange+: 0x1058 (4184) against 1063.
    config = outdir / 'NuttX' / 'nuttx' / '.config'
    product = None
    if config.is_file():
        product = next((line.split('=', 1)[1] for line in config.read_text().splitlines()
                        if line.startswith('CONFIG_CDCACM_PRODUCTID=')), None)
    if product is None:
        raise SystemExit(f'CONFIG_CDCACM_PRODUCTID not in {config}: the board version the FC reports is unknown')
    info['outputs'] = {
        'firmware': {'file': image.name, 'sha256': sha256(image), 'size': image.stat().st_size},
        'image_bin': {'file': 'not kept (inside the .px4 image field)',
                      'sha256': hashlib.sha256(zlib.decompress(base64.b64decode(px4_image['image']))).hexdigest(),
                      'size': px4_image['image_size']},
        'parameters': {'file': params.name, 'sha256': sha256(params), 'count': len(listing),
                       'origin': 'PX4 build output, unmodified'},
    }
    info['embedded'] = {
        'board_id': px4_image['board_id'], 'board_version': int(product, 0),
        'git_identity': px4_image.get('git_identity'), 'git_hash': git(tree, 'rev-parse', 'HEAD'),
        'nuttx_git_hash': git(nuttx, 'rev-parse', 'HEAD'), 'image_size': px4_image['image_size'],
        'image_maxsize': px4_image['image_maxsize'],
        'flash_used_percent': round(100 * px4_image['image_size'] / px4_image['image_maxsize'], 2),
    }
    gcc = subprocess.run(['arm-none-eabi-gcc', '--version'], capture_output=True, text=True).stdout.splitlines()
    info['build'] = {
        'tool': 'px4-llm-sim2hitl tools/px4build.py', 'command': portable(' '.join(cmd), source, tree),
        'build_tree': '<PX4 build tree>', 'output_dir': portable(outdir, source, tree), 'committer': committer,
        'patches': applied, 'modules': {n: module_files(repo, n) for n in modules},
        'toolchain': gcc[0] if gcc else None,
        'built_at_utc': datetime.datetime.now(datetime.timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ'),
        'seconds': seconds, 'log': portable(log, source, tree),
    }
    info['flashed'] = None
    info_path.write_text(json.dumps(info, indent=2, ensure_ascii=False) + '\n')
    lock.close()
    params_path = recipe_dir / 'params.json'
    if params_path.is_file():
        p = json.loads(params_path.read_text())
        p['firmware_params'] = {'file': 'firmware/' + params.name, 'sha256': sha256(params)}
        params_path.write_text(json.dumps(p, indent=2, ensure_ascii=False) + '\n')
    return {'status': 'PASS', 'recipe': str(recipe_dir), 'firmware_sha256': info['outputs']['firmware']['sha256'],
            'image_bin_sha256': info['outputs']['image_bin']['sha256'], 'git_hash': info['embedded']['git_hash'],
            'nuttx_git_hash': info['embedded']['nuttx_git_hash'],
            'flash_used_percent': info['embedded']['flash_used_percent'], 'seconds': seconds, 'log': str(log)}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('recipe')
    p.add_argument('--repo', help='the vehicle repository (default: the nearest folder above with sim2hitl.lock)')
    p.add_argument('--px4-root')
    p.add_argument('--if-needed', action='store_true', help='build only when no current image exists')
    a = p.parse_args()
    if a.if_needed:
        repo = Path(a.repo).resolve() if a.repo else find_repo(a.recipe)
        wanted, why = needs_build(repo, a.recipe)
        if not wanted:
            print(json.dumps({'status': 'PASS', 'recipe': str(Path(a.recipe).resolve()), 'built': False, 'why': why}))
            return
    print(json.dumps(build(a.recipe, a.repo, a.px4_root)))


if __name__ == '__main__':
    main()
