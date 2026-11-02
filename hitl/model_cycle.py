#!/usr/bin/env python3
"""Everything to run after a change in model/, in order, stopping at the first failure (AGENTS section 5).

  ./runbridge model-cycle [--cache DIR] [--skip-generate] [--airspeed 13 16 20 25] [--no-sitl-build] [--out NEW_DIR]

1. Code generation through MATLAB (--cache: a build_core() folder made by hand; --skip-generate: only plant C changed).
2. What the generation changed: the generated C without comments and the Simulink reference runs, byte by byte.
3. Model release: compile, the four checks, publish.
4. Trim at several airspeeds, drop test, and the linear model at the middle one (sitl/trim.py).
5. The recorded reference data re-recorded and compared. Identical data plus identical C means nothing numeric changed.
6. The reduced SITL rebuilt against the new release (its executable links the plant library by absolute path).
   SIM2HITL_PX4_VENV, when set, is put first on PATH for the build (a venv for PX4's Python kept outside the PX4 tree).

The report says what ran, and what did not. A change that was meant to change the aircraft reports `numeric_change: true`,
which is then expected, not a failure. No FC is touched: SITL scenarios and HITL come after, as AGENTS section 5 says.
"""
import argparse
import datetime
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

import numpy as np

HITL = Path(__file__).resolve().parent
ROOT = HITL.parent
sys.path.insert(0, str(ROOT / 'plant' / 'core'))
import toolchain  # noqa: E402

GENERATED = ROOT / 'model' / 'generated'
REFERENCE = ROOT / 'plant' / 'reference' / 'data' / 'reference.npz'
COMMENT_BLOCK = re.compile(r'/\*.*?\*/', re.S)


class Failed(RuntimeError):
    pass


def code_without_comments(path):
    return COMMENT_BLOCK.sub('', Path(path).read_text(errors='replace'))


def generated_difference(before, after):
    """What differs between two model/generated folders: code without comments, and other files (results) by bytes."""
    before, after = Path(before), Path(after)
    names = {p.relative_to(before) for p in before.rglob('*') if p.is_file()} | \
            {p.relative_to(after) for p in after.rglob('*') if p.is_file()}
    code, results, comments_only = [], [], 0
    for name in sorted(names):
        if name.name == 'manifest.json' or name.suffix == '.mk':
            continue  # identity and paths, which change on every generation
        a, b = before / name, after / name
        if not a.is_file() or not b.is_file():
            (code if name.suffix in ('.c', '.h') else results).append(str(name))
        elif name.suffix in ('.c', '.h'):
            if code_without_comments(a) != code_without_comments(b):
                code.append(str(name))
            elif a.read_bytes() != b.read_bytes():
                comments_only += 1
        elif a.read_bytes() != b.read_bytes():
            results.append(str(name))
    return {'code_changed': code, 'results_changed': results, 'code_files_with_only_comment_changes': comments_only}


def arrays_difference(before, after):
    """Names of the arrays that differ between two .npz files, compared byte by byte."""
    a, b = np.load(before, allow_pickle=True), np.load(after, allow_pickle=True)
    changed = [k for k in sorted(set(a.files) | set(b.files))
               if k not in a.files or k not in b.files or a[k].shape != b[k].shape or a[k].tobytes() != b[k].tobytes()]
    return {'arrays': len(set(a.files) | set(b.files)), 'changed': changed}


class Cycle:
    def __init__(self, out):
        self.out = out
        self.report = {'created_utc': datetime.datetime.now(datetime.timezone.utc).isoformat(timespec='seconds'), 'steps': []}

    def run(self, name, command, env=None, timeout=3600):
        """One step: full output in the report folder, a short result here."""
        log = self.out / (re.sub(r'\W+', '_', name) + '.log')
        print(f'--- {name}', flush=True)
        with log.open('w') as handle:
            result = subprocess.run([str(c) for c in command], cwd=ROOT, stdout=handle, stderr=subprocess.STDOUT, text=True,
                                    timeout=timeout, env=dict(os.environ, **(env or {})))
        entry = {'step': name, 'exit': result.returncode, 'log': str(log)}
        self.report['steps'].append(entry)
        if result.returncode:
            raise Failed(f'{name} exited {result.returncode}: see {log}')
        return log.read_text()

    def write(self):
        (self.out / 'report.json').write_text(json.dumps(self.report, indent=1, ensure_ascii=False))


def px4_path_env():
    venv = os.environ.get('SIM2HITL_PX4_VENV')
    return {'PATH': f"{venv}/bin:{os.environ['PATH']}"} if venv else {}


def last_json(text):
    for line in reversed(text.strip().splitlines()):
        try:
            value = json.loads(line)
        except ValueError:
            continue
        if isinstance(value, dict):
            return value
    return {}


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--cache', type=Path, help='a folder build_core() returned in MATLAB')
    parser.add_argument('--skip-generate', action='store_true', help='model/generated is current (plant C changed)')
    parser.add_argument('--airspeed', type=float, nargs='+', default=[13.0, 16.0, 20.0, 25.0])
    parser.add_argument('--no-sitl-build', action='store_true')
    parser.add_argument('--out', type=Path)
    args = parser.parse_args()
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d_%H%M%SZ')
    out = args.out or toolchain.cache_root() / 'model_cycles' / f'cycle_{stamp}'
    if out.exists():
        parser.error(f'{out} exists')
    out.mkdir(parents=True)
    cycle = Cycle(out)
    report = cycle.report
    python = sys.executable
    before = out / 'before'
    before.mkdir()
    shutil.copy2(REFERENCE, before / 'reference.npz')
    shutil.copytree(GENERATED, before / 'generated')
    try:
        if not args.skip_generate:
            cycle.run('generate', [python, '-B', HITL / 'update.py', '--generate'] + (['--cache', args.cache] if args.cache else []))
            report['generated'] = generated_difference(before / 'generated', GENERATED)
            print('    ' + json.dumps(report['generated']), flush=True)
        else:
            report['generated'] = 'skipped'
        release = last_json(cycle.run('release', [python, '-B', HITL / 'update.py']))
        report['build_id'] = release.get('build_id')
        print(f"    {release.get('build_id')}{' (unchanged)' if release.get('unchanged') else ''}", flush=True)
        middle = sorted(args.airspeed)[len(args.airspeed) // 2 - 1]
        cycle.run('trim', [python, '-B', ROOT / 'sitl/trim.py', '--airspeed', *args.airspeed, '--drop', 20, '--out', out / 'trim.json'])
        report['trim'] = [{'airspeed_m_s': r['airspeed_m_s'], 'elevator': r['elevator'], 'throttle': r['throttle'],
                           'pitch_deg': r['pitch_deg'], 'converged': r['converged']}
                          for r in json.loads((out / 'trim.json').read_text())['trims']]
        for row in report['trim']:
            print(f"    {row['airspeed_m_s']:5.1f} m/s elevator {row['elevator']:.4f} throttle {row['throttle']:.4f} pitch {row['pitch_deg']:.2f}", flush=True)
        cycle.run('linear model', [python, '-B', ROOT / 'sitl/trim.py', '--airspeed', middle, '--drop', 0, '--linearize', '--out', out / 'linear.json'])
        linear = json.loads((out / 'linear.json').read_text())['trims'][0]['linear']
        report['linear_modes'] = linear['modes']
        report['linear_check'] = linear['check_against_full_model']
        cycle.run('reference data', [python, '-B', ROOT / 'plant/reference/record_reference.py'])
        report['reference'] = arrays_difference(before / 'reference.npz', REFERENCE)
        generated = report['generated']
        code_changed = generated != 'skipped' and bool(generated['code_changed'] or generated['results_changed'])
        report['numeric_change'] = bool(report['reference']['changed']) or code_changed
        print(f"    reference: {len(report['reference']['changed'])} of {report['reference']['arrays']} arrays changed; "
              f"numeric_change {report['numeric_change']}", flush=True)
        if not args.no_sitl_build:
            cycle.run('reduced SITL build', [python, '-B', ROOT / 'sitl/build_sitl.py'], env=px4_path_env())
        else:
            report['reduced_sitl'] = 'not rebuilt: run sitl/build_sitl.py before the next reduced SITL'
        report['verdict'] = 'PASS'
    except (Failed, subprocess.TimeoutExpired) as error:
        report['verdict'] = 'FAIL'
        report['failure'] = str(error)
        print(f'FAIL: {error}', flush=True)
    cycle.write()
    print(json.dumps({'verdict': report['verdict'], 'build_id': report.get('build_id'), 'numeric_change': report.get('numeric_change'),
                      'report': str(out / 'report.json')}), flush=True)
    return 0 if report['verdict'] == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
