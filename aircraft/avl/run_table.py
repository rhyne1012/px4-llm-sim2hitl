#!/usr/bin/env python3
"""Recompute the aero tables from the AVL geometry in one command, and say what changed.

  "$PY" -B aircraft/avl/run_table.py [--config aircraft/avl/table.json] [--lint-only] [--compare OLD_result.json] [--write-mat]

1. Lint the geometry: surfaces that touch but are not in one COMPONENT. AVL then uses its finite-core model across the
   joint, and a wing split at the centre behaves as if it had a root gap, with no warning from AVL: on SkySurfer the
   lift slope was 8 % low and the neutral point 10 % MAC too far aft (hitl/sim_to_flight.md section 6). A joint is a
   section of one surface lying on a chord of a section of another; SCALE is taken as 1, as in this geometry.
2. Run the grid in table.json through the AVL MCP server (SIM2HITL_AVL_MCP, SIM2HITL_AVL_BIN, SIM2HITL_AVL_WORK).
3. Print the numbers to read first, with sideslip slopes from grid differences. With --compare, against an older result.json.
4. With --write-mat, write the MAT files through MATLAB (aircraft/avl/build_avl_mat.m). That changes model/, so the model
   cycle comes next: ./runbridge model-cycle.
"""
import argparse
import json
import math
import os
import re
import subprocess
import sys
import time
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parents[1]
TOUCH_M = 1e-3


def data_lines(text):
    """The file without comments and blank lines; # and ! start a comment."""
    for line in text.splitlines():
        line = re.split(r'[#!]', line, maxsplit=1)[0].strip()
        if line:
            yield line


def parse_surfaces(text):
    """[{name, component, sections: [(x, y, z, chord)]}], world coordinates, a YDUPLICATE adds the mirrored sections.
    Keywords by their first four characters, as AVL reads them (SURF, SECT, COMP ...)."""
    lines = list(data_lines(text))
    surfaces = []
    current = None
    i = 0
    while i < len(lines):
        word = lines[i].split()[0].upper()[:4]
        if word == 'SURF':
            current = {'name': lines[i + 1], 'component': None, 'translate': (0.0, 0.0, 0.0), 'raw': [], 'mirror': None}
            surfaces.append(current)
            i += 2
            continue
        if word == 'BODY':
            current = None
        elif current is not None:
            if word in ('COMP', 'INDE'):
                current['component'] = int(lines[i + 1].split()[0])
            elif word == 'TRAN':
                current['translate'] = tuple(float(v) for v in lines[i + 1].split()[:3])
            elif word == 'YDUP':
                current['mirror'] = float(lines[i + 1].split()[0])
            elif word == 'SECT':
                values = lines[i + 1].split()
                current['raw'].append(tuple(float(v) for v in values[:4]))
        i += 1
    for surface in surfaces:
        dx, dy, dz = surface['translate']
        sections = [(x + dx, y + dy, z + dz, c) for x, y, z, c in surface['raw']]
        if surface['mirror'] is not None:
            sections += [(x, 2 * surface['mirror'] - y, z, c) for x, y, z, c in sections]
        surface['sections'] = sections
    return surfaces


def unjoined(surfaces):
    """Pairs of surfaces that touch without sharing a COMPONENT."""
    problems = []
    for i, a in enumerate(surfaces):
        for b in surfaces[i + 1:]:
            if a['component'] is not None and a['component'] == b['component']:
                continue
            touching = any(abs(ya - yb) < TOUCH_M and abs(za - zb) < TOUCH_M
                           and (xb - TOUCH_M <= xa <= xb + cb + TOUCH_M or xa - TOUCH_M <= xb <= xa + ca + TOUCH_M)
                           for xa, ya, za, ca in a['sections'] for xb, yb, zb, cb in b['sections'])
            if touching:
                problems.append((a['name'], b['name']))
    return problems


class McpServer:
    """A newline-delimited JSON-RPC client over stdio, enough for the AVL MCP tools."""

    def __init__(self, command):
        self.proc = subprocess.Popen(command, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                                     text=True, bufsize=1)
        self.next_id = 0
        self.request('initialize', {'protocolVersion': '2024-11-05', 'capabilities': {},
                                    'clientInfo': {'name': 'run_table', 'version': '1'}})
        self.proc.stdin.write(json.dumps({'jsonrpc': '2.0', 'method': 'notifications/initialized'}) + '\n')
        self.proc.stdin.flush()

    def request(self, method, params):
        self.next_id += 1
        self.proc.stdin.write(json.dumps({'jsonrpc': '2.0', 'id': self.next_id, 'method': method, 'params': params}) + '\n')
        self.proc.stdin.flush()
        for line in self.proc.stdout:
            try:
                message = json.loads(line)
            except ValueError:
                continue
            if message.get('id') == self.next_id:
                if 'error' in message:
                    raise RuntimeError(str(message['error']))
                return message['result']
        raise RuntimeError('AVL MCP server closed')

    def tool(self, name, arguments):
        result = self.request('tools/call', {'name': name, 'arguments': arguments})
        data = result.get('structuredContent')
        if data is None:
            data = json.loads('\n'.join(c.get('text', '') for c in result.get('content', [])))
        if result.get('isError'):
            raise RuntimeError(json.dumps(data)[:800])
        return data

    def close(self):
        self.proc.stdin.close()
        try:
            self.proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            self.proc.terminate()


def server_command():
    home = Path.home() / '.local/share/AVL-MCP'
    sys.path.insert(0, str(ROOT / 'plant' / 'core'))
    import toolchain
    work = os.environ.get('SIM2HITL_AVL_WORK') or str(toolchain.cache_root() / 'avl_runs')
    return [os.environ.get('SIM2HITL_AVL_MCP') or str(home / 'venv-0.5.0/bin/avl-mcp'),
            '--avl-bin', os.environ.get('SIM2HITL_AVL_BIN') or str(home / 'avl-3.52/AVL3.52rel09032025/bin/avl'),
            '--work-root', work]


def run_grid(config, geometry):
    conditions = [{'alpha_deg': a, 'beta_deg': b, 'mach': m}
                  for m in config['mach'] for a in config['alpha_deg'] for b in config['beta_deg']]
    server = McpServer(server_command())
    try:
        job = server.tool('avl.submit', {'model_path': str(geometry), 'case_name': 'aero_table', 'length_unit': 'm',
                                         'references': config['references'], 'outputs': config['outputs'],
                                         'conditions': conditions, 'timeout_seconds': 1800})
        while True:
            status = server.tool('avl.status', {'job_id': job['job_id']})
            if status['state'] not in ('queued', 'running'):
                break
            print(f"  {status['completed_count']}/{status['requested_count']} cases", flush=True)
            time.sleep(10)
    finally:
        server.close()
    if status['state'] != 'completed' or status['failed_count']:
        raise RuntimeError(f"AVL job {job['job_id']} ended {status['state']}, {status['failed_count']} failed: {status.get('error')}")
    return Path(status['result_json']), job['job_id']


def summary(result_path, config):
    """The numbers to read first, at the highest Mach of the grid; sideslip slopes by grid difference."""
    cases = json.loads(Path(result_path).read_text())['results']
    mach = max(config['mach'])

    def case(alpha, beta):
        for c in cases:
            f = c['total']['fields']
            if abs(f['Mach'] - mach) < 1e-9 and f['Alpha'] == alpha and f['Beta'] == beta:
                return c
        return None

    # The numbers need alpha 0 and 5 and beta 0 and 5 in the grid, and read the control derivatives by the names in
    # this geometry (elevator, rudder, aileron*); another grid or other names leave those rows out, nothing stops.
    rows = {}
    low, high, side = case(0, 0), case(5, 0), case(5, 5)
    if low and high:
        fl, fh = low['total']['fields'], high['total']['fields']
        mac = config['geometric_mac']
        neutral = (low['stability']['diagnostics']['neutral_point_x'] + high['stability']['diagnostics']['neutral_point_x']) / 2
        d, c = high['stability']['derivatives'], high['stability']['control_derivatives']
        rows.update({'CL at alpha 0': fl['CLtot'], 'lift slope, /rad': (fh['CLtot'] - fl['CLtot']) / math.radians(5.0),
                     'neutral point, % geometric MAC': 100 * (neutral - mac['leading_edge_x_m']) / mac['length_m'],
                     'static margin at the CG, % MAC': 100 * (neutral - config['cg_x_m']) / mac['length_m'],
                     'span efficiency e, alpha 5': fh['e'], 'Cmq': d['Cmq'], 'Clp': d['Clp'], 'Cnr': d['Cnr'],
                     'false side force at beta 0, largest of CY Cl Cn': max(abs(fh['CYtot']), abs(fh["Cl'tot"]), abs(fh["Cn'tot"]))})
        if 'elevator' in c:
            rows['Cm per elevator deg'] = c['elevator']['Cm']
        ailerons = [abs(v['Cl']) for k, v in c.items() if k.lower().startswith('aileron')]
        if ailerons:
            rows['Cl per aileron deg, both'] = sum(ailerons)
        if 'rudder' in c:
            rows['Cn per rudder deg'] = c['rudder']['Cn']
        if side:
            fs = side['total']['fields']
            rows.update({'Cn per beta deg (grid)': (fs["Cn'tot"] - fh["Cn'tot"]) / 5.0,
                         'Cl per beta deg (grid)': (fs["Cl'tot"] - fh["Cl'tot"]) / 5.0,
                         'CY per beta deg (grid)': (fs['CYtot'] - fh['CYtot']) / 5.0})
    return rows


def write_mat(result_path, config):
    sys.path.insert(0, str(ROOT / 'hitl' / 'matlab'))
    from mcp_build import evaluate
    path = str(result_path).replace("'", "''")
    calls = ''.join(f"build_avl_mat('{path}', '{t['mat']}', '{t['mat']}', '{t['tag']}'); " for t in config['tables'])
    evaluate(ROOT, f"addpath('aircraft/avl'); {calls}disp('MAT files written');")


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--config', type=Path, default=HERE / 'table.json')
    parser.add_argument('--lint-only', action='store_true')
    parser.add_argument('--compare', type=Path, help='an older result.json')
    parser.add_argument('--write-mat', action='store_true')
    parser.add_argument('--ignore-lint', action='store_true', help='solve (and write) although the lint found a joint')
    args = parser.parse_args()
    config = json.loads(args.config.read_text())
    geometry = (args.config.parent / config['geometry']).resolve()
    problems = unjoined(parse_surfaces(geometry.read_text()))
    for a, b in problems:
        print(f'LINT: "{a}" and "{b}" touch but are not in one COMPONENT: AVL treats the joint with a finite core')
    if not problems:
        print(f'lint: {geometry.name}: every touching pair of surfaces shares a COMPONENT')
    if args.lint_only or (problems and not args.ignore_lint):
        if problems and not args.lint_only:
            print('Nothing solved or written: join the surfaces (COMPONENT), or --ignore-lint if the gap is real.')
        return 1 if problems else 0
    result, job = run_grid(config, geometry)
    print(f'AVL job {job}: {result}')
    numbers = summary(result, config)
    old = summary(args.compare, config) if args.compare else None
    for name, value in numbers.items():
        print(f'  {name:48s} {value:12.5f}' + (f'   was {old[name]:12.5f}' if old and name in old else ''))
    if args.write_mat:
        write_mat(result, config)
        print('MAT files written: model/ changed, next ./runbridge model-cycle')
    else:
        print('Nothing written. --write-mat puts this into model/.')
    return 1 if problems else 0


if __name__ == '__main__':
    sys.exit(main())
