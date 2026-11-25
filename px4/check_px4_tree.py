#!/usr/bin/env python3
"""Check that this machine's PX4 source tree matches px4/px4_lock.json.

The PX4 tree is kept outside the project. Its location is per machine and is found in this order:
  --path PATH, then $SIM2HITL_PX4_ROOT, then the local config file
  (macOS: ~/Library/Application Support/px4-llm-sim2hitl/px4_root,
   Linux: ~/.config/px4-llm-sim2hitl/px4_root,
   Windows: %LOCALAPPDATA%\\px4-llm-sim2hitl\\px4_root).
If none of them is set: use the user's tree if they have one, otherwise download the locked tag outside the
project (git clone --branch <tag> --recurse-submodules <repository>), check it with --path and --remember.
Other scripts get the location from px4_root().

  python3 px4/check_px4_tree.py                      check and print a JSON report
  python3 px4/check_px4_tree.py --path P --remember  check P and save it as this machine's location

Exit codes: 0 PASS, 1 FAIL (tree differs from the lock), 2 location unknown or not a git tree.
Read-only, except that --remember writes the local config file after a PASS.
Standard library only.
"""
import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

LOCK = Path(__file__).resolve().parent / 'px4_lock.json'


def config_file():
    if sys.platform == 'win32':
        base = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData' / 'Local'))
    elif sys.platform.startswith('linux'):
        base = Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config')
    else:
        base = Path.home() / 'Library' / 'Application Support'
    return base / 'px4-llm-sim2hitl' / 'px4_root'


def locate(explicit):
    if explicit:
        return Path(explicit).expanduser(), '--path'
    env = os.environ.get('SIM2HITL_PX4_ROOT')
    if env:
        return Path(env).expanduser(), 'SIM2HITL_PX4_ROOT'
    cfg = config_file()
    if cfg.is_file():
        text = cfg.read_text(encoding='utf-8').strip()
        if text:
            return Path(text).expanduser(), str(cfg)
    return None, None


def px4_root():
    """The PX4 tree of this machine (SIM2HITL_PX4_ROOT or the local config file)."""
    root, _ = locate(None)
    if root is None:
        raise SystemExit('PX4 tree location not set: run px4/check_px4_tree.py --path <tree> --remember')
    return root


def git(root, *args):
    result = subprocess.run(['git', '-C', str(root), *args], capture_output=True, text=True)
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def check(root, lock):
    report = {'path': str(root), 'lock_tag': lock['tag'], 'lock_commit': lock['commit'], 'problems': []}
    code, head, err = git(root, 'rev-parse', 'HEAD')
    if code:
        report['problems'].append('not a git tree: ' + err)
        return report, 2
    report['head'] = head
    if head != lock['commit']:
        report['problems'].append(f'HEAD {head} differs from lock commit {lock["commit"]}')
    _, tag, _ = git(root, 'describe', '--tags', '--exact-match', 'HEAD')
    report['head_tag'] = tag or None
    _, dirty, _ = git(root, 'status', '--porcelain')
    report['dirty_entries'] = len(dirty.splitlines()) if dirty else 0
    if dirty:
        report['problems'].append('working tree has uncommitted or untracked changes (git status --porcelain)')
    _, subs, _ = git(root, 'submodule', 'status', '--recursive')
    bad = [line for line in subs.splitlines() if line[:1] in '+-U']
    report['submodule_problems'] = bad
    if bad:
        report['problems'].append(f'{len(bad)} submodules not at the recorded commit or not initialised')
    return report, (1 if report['problems'] else 0)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--path', help='PX4 tree to check (overrides env and local config)')
    parser.add_argument('--remember', action='store_true', help='save --path as this machine\'s location after a PASS')
    args = parser.parse_args()
    lock = json.loads(LOCK.read_text(encoding='utf-8'))
    root, source = locate(args.path)
    if root is None:
        print(json.dumps({'status': 'UNKNOWN_LOCATION', 'message': 'PX4 tree location is not set on this machine. '
                          f'Ask the user where the PX4 {lock["tag"]} tree is, then run with --path PATH --remember.',
                          'config_file': str(config_file())}, indent=2, ensure_ascii=False))
        return 2
    if not root.is_dir():
        print(json.dumps({'status': 'UNKNOWN_LOCATION', 'path': str(root), 'source': source,
                          'message': 'Configured PX4 path does not exist (external disk not mounted?). Ask the user.'},
                         indent=2, ensure_ascii=False))
        return 2
    report, code = check(root.resolve(), lock)
    report['source'] = source
    report['status'] = {0: 'PASS', 1: 'FAIL', 2: 'UNKNOWN_LOCATION'}[code]
    if code == 0 and args.remember:
        if not args.path:
            parser.error('--remember needs --path')
        cfg = config_file()
        cfg.parent.mkdir(parents=True, exist_ok=True)
        cfg.write_text(str(root.resolve()) + '\n', encoding='utf-8')
        report['remembered_in'] = str(cfg)
    print(json.dumps(report, indent=2, ensure_ascii=False))
    return code


if __name__ == '__main__':
    sys.exit(main())
