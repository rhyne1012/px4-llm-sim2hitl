#!/usr/bin/env python3
"""The model's VSP aero table (model/Skysurfer.mat, used when useAVL_VSP = 1) from OpenVSP/VSPAERO, in one command.

  "$PY" -B aircraft/vsp/run_table.py [--config aircraft/vsp/table.json] [--out NEW_DIR] [--alpha A ...] [--beta B ...]
      [--mach M ...] [--jobs N] [--merge-stab A.stab B.stab ...] [--compare-avl AVL_result.json] [--write-mat]
  "$PY" -B aircraft/vsp/run_table.py --write-mat --from-result <run>/result.json

1. Geometry: skysurfer_geometry.as (the planform of the AVL file, the four control surfaces, the tail incidence).
2. One VSPAERO stability sweep over Mach x alpha x beta: every case gives the coefficients and their derivatives with
   respect to alpha, beta, p, q, r, Mach, U and the four control groups (the .stab file), per radian.
3. result.json in the run folder, and the numbers to read first. With --compare-avl, against an AVL MCP result.json.
4. With --write-mat, model/Skysurfer.mat in the format of model/import_aerostates_vsp.m (data_out), through MATLAB,
   with the moments in wind axes as the model's VSP path reads them (wind_moments). That changes model/, so
   ./runbridge model-cycle comes next.

OpenVSP 3.55.0 is found through SIM2HITL_VSP_ROOT (the folder with opt/OpenVSP/vspscript), else ~/.local/share/OpenVSP/3.55.0.
"""
import argparse
import concurrent.futures
import datetime
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
sys.path.insert(0, str(ROOT / 'plant' / 'core'))
sys.path.insert(0, str(ROOT / 'hitl' / 'matlab'))
COEFFS = ('CFx', 'CFy', 'CFz', 'CMx', 'CMy', 'CMz', 'CL', 'CD', 'CS', 'CMl', 'CMm', 'CMn')
# Columns of the .stab table, in the order of the importer's suffixes (base, da, db, dp, dq, dr, dM, dU, then groups)
DERIVS = ('base', 'da', 'db', 'dp', 'dq', 'dr', 'dM', 'dU')


def vsp_root():
    return Path(os.environ.get('SIM2HITL_VSP_ROOT') or Path.home() / '.local/share/OpenVSP/3.55.0')


def script(config, vsp3):
    ref, flow, solver = config['reference'], config['flow'], config['solver']

    def span(values):
        return min(values), max(values), len(values)

    a0, a1, an = span(config['alpha_deg'])
    b0, b1, bn = span(config['beta_deg'])
    m0, m1, mn = span(config['mach'])
    groups = []
    for index, group in enumerate(config['groups']):
        names = ', '.join(f'"{s}"' for s in group['surfaces'])
        groups.append(f'''
    {{
        int g = CreateVSPAEROControlSurfaceGroup();
        array<string> @available = GetAvailableCSNameVec(g);
        array<string> wanted = {{{names}}};
        array<int> selected;
        for (uint i = 0; i < available.size(); i++) {{ if (wanted.find(available[i]) >= 0) selected.insertLast(int(i) + 1); }}
        if (int(selected.size()) != int(wanted.size())) {{ Print("GROUP_MISSING {group['name']}"); return 4; }}
        AddSelectedToCSGroup(selected, g);
        SetVSPAEROControlGroupName("{group['name']}", g);
        Print("GROUP " + g + " {group['name']}");
    }}''')
    return f'''#include "{HERE / 'skysurfer_geometry.as'}"
int CheckErrors() {{ int n = GetNumTotalErrors(); while (GetNumTotalErrors() > 0) {{ ErrorObj e = PopLastError(); Print("ERROR " + e.GetErrorString()); }} return n; }}
void SetD(string name, double v) {{ array<double> x = {{v}}; SetDoubleAnalysisInput("VSPAEROSweep", name, x); }}
void SetI(string name, int v) {{ array<int> x = {{v}}; SetIntAnalysisInput("VSPAEROSweep", name, x); }}
int main() {{
    ClearVSPModel();
    BuildSkySurfer({config['tail_incidence_deg']});
    if (CheckErrors() != 0) return 1;
{''.join(groups)}
    // A mirrored surface (Surf1, the left side) deflects the other way for the same gain: -1 makes trailing edge
    // down positive on both sides, as in the AVL file and the model (checked against AVL's aileron and elevator signs).
    string settings = FindContainer("VSPAEROSettings", 0);
    array<string> @parms = FindContainerParmIDs(settings);
    for (uint i = 0; i < parms.size(); i++) {{
        string n = GetParmName(parms[i]);
        if (n.findFirst("Surf_") == 0 && n.findFirst("_1_Gain") > 0) {{ SetParmVal(parms[i], -1.0); Print("GAIN -1 " + n); }}
    }}
    SetVSP3FileName("{vsp3}");
    WriteVSPFile("{vsp3}", SET_ALL);
    if (CheckErrors() != 0) return 2;
    SetAnalysisInputDefaults("VSPAEROComputeGeometry");
    array<int> none = {{-1}}; array<int> all = {{0}};
    SetIntAnalysisInput("VSPAEROComputeGeometry", "GeomSet", none);
    SetIntAnalysisInput("VSPAEROComputeGeometry", "ThinGeomSet", all);
    ExecAnalysis("VSPAEROComputeGeometry");
    SetAnalysisInputDefaults("VSPAEROSweep");
    SetI("GeomSet", -1); SetI("ThinGeomSet", 0); SetI("RefFlag", 0);
    SetD("Sref", {ref['sref']}); SetD("cref", {ref['cref']}); SetD("bref", {ref['bref']});
    SetD("Xcg", {ref['xcg']}); SetD("Ycg", {ref['ycg']}); SetD("Zcg", {ref['zcg']});
    SetD("AlphaStart", {a0}); SetD("AlphaEnd", {a1}); SetI("AlphaNpts", {an});
    SetD("BetaStart", {b0}); SetD("BetaEnd", {b1}); SetI("BetaNpts", {bn});
    SetD("MachStart", {m0}); SetD("MachEnd", {m1}); SetI("MachNpts", {mn});
    SetD("Vinf", {flow['vinf_m_s']}); SetD("Vref", {flow['vinf_m_s']}); SetD("Rho", {flow['rho_kg_m3']}); SetD("ReCref", {flow['re_cref']});
    SetI("WakeNumIter", {solver['wake_iterations']}); SetI("NumWakeNodes", {solver['wake_nodes']}); SetD("FarAway", {solver['far_away']});
    SetI("FixedWakeFlag", {1 if solver.get('fixed_wake') else 0});
    SetI("UnsteadyType", STABILITY_DEFAULT); SetI("NCPU", {solver['ncpu']}); SetI("Symmetry", 0);
    if (CheckErrors() != 0) return 3;
    Print("OPENVSP_VERSION " + GetVSPVersion());
    ExecAnalysis("VSPAEROSweep");
    if (CheckErrors() != 0) return 5;
    Print("SWEEP_DONE");
    return 0;
}}
'''


def parse_stab(text, groups):
    """Every case of a VSPAERO .stab file: flow condition and a table coefficient x (base, derivatives, groups)."""
    cases = []
    for block in re.split(r'\n(?=\s*\*+\s*\n\s*#\s*Name)|\n(?=#\s*Name\s+Value\s+Units)', text):
        values = {}
        for key in ('Mach_', 'AoA_', 'Beta_'):
            m = re.search(r'^\s*' + key + r'\s+(\S+)', block, re.M)
            if m:
                values[key.rstrip('_')] = float(m.group(1))
        rows = {}
        for line in block.splitlines():
            parts = line.split()
            if parts and parts[0] in COEFFS and len(parts) >= len(DERIVS) + len(groups):
                try:
                    numbers = [float(p) for p in parts[1:]]
                except ValueError:
                    continue
                rows[parts[0]] = numbers
        if len(values) == 3 and len(rows) == len(COEFFS):
            cases.append({'mach': values['Mach'], 'alpha_deg': values['AoA'], 'beta_deg': values['Beta'], 'rows': rows})
    return cases


def run(config, out):
    root = vsp_root()
    vspscript = root / 'opt/OpenVSP/vspscript'
    env = dict(os.environ, LD_LIBRARY_PATH=f"{root / 'usr/lib/x86_64-linux-gnu'}:{os.environ.get('LD_LIBRARY_PATH', '')}")
    vsp3 = out / 'skysurfer.vsp3'
    (out / 'run.vspscript').write_text(script(config, vsp3))
    start = time.monotonic()
    with (out / 'vspscript.log').open('w') as log:
        result = subprocess.run([str(vspscript), '-script', str(out / 'run.vspscript')], cwd=out, env=env, stdout=log,
                                stderr=subprocess.STDOUT, text=True, timeout=6 * 3600)
    seconds = time.monotonic() - start
    log_text = (out / 'vspscript.log').read_text(errors='replace')
    if result.returncode or 'SWEEP_DONE' not in log_text:
        raise SystemExit(f'vspscript failed ({result.returncode}): see {out / "vspscript.log"}')
    stab = sorted(out.glob('*.stab'))
    if not stab:
        raise SystemExit(f'no .stab file in {out}')
    version = re.search(r'OPENVSP_VERSION (.+)', log_text)
    return stab[0], seconds, version.group(1).strip() if version else None


def table(cases, config):
    """Cases ordered like the importer's grid: beta outer, then Mach, then alpha (data_out order)."""
    names = [g['name'] for g in config['groups']]
    suffixes = list(DERIVS) + ['d' + n for n in names]
    index = {(round(c['mach'], 4), round(c['alpha_deg'], 3), round(c['beta_deg'], 3)): c for c in cases}
    ordered = []
    for beta in config['beta_deg']:
        for mach in config['mach']:
            for alpha in config['alpha_deg']:
                key = (round(mach, 4), round(alpha, 3), round(beta, 3))
                if key not in index:
                    raise SystemExit(f'missing case Mach {mach} alpha {alpha} beta {beta}')
                ordered.append(index[key])
    data = {'mach': [c['mach'] for c in ordered], 'aoa': [c['alpha_deg'] for c in ordered],
            'beta': [c['beta_deg'] for c in ordered]}
    for coeff in COEFFS:
        data[coeff] = {s: [c['rows'][coeff][k] for c in ordered] for k, s in enumerate(suffixes)}
    return data, suffixes


def pick(data, coeff, suffix, mach, alpha, beta):
    for k in range(len(data['mach'])):
        if math.isclose(data['mach'][k], mach) and math.isclose(data['aoa'][k], alpha) and math.isclose(data['beta'][k], beta):
            return data[coeff][suffix][k]
    return None


def summary(data, config):
    """The numbers to read first, at the lowest Mach. Slopes from grid differences (not the solver's own d/dbeta)."""
    mach = min(config['mach'])
    ref = config['reference']
    rows = {}
    cl0, cl5 = pick(data, 'CL', 'base', mach, 0, 0), pick(data, 'CL', 'base', mach, 5, 0)
    cm0, cm5 = pick(data, 'CMm', 'base', mach, 0, 0), pick(data, 'CMm', 'base', mach, 5, 0)
    rad5 = math.radians(5.0)
    if None not in (cl0, cl5, cm0, cm5):
        cla, cma = (cl5 - cl0) / rad5, (cm5 - cm0) / rad5
        rows['CL_alpha_per_rad'] = cla
        rows['Cm_alpha_per_rad'] = cma
        rows['neutral_point_x_m'] = ref['xcg'] - cma / cla * ref['cref']
        rows['CL_at_0'] = cl0
        rows['Cm_at_0'] = cm0
    cy5, cl_5, cn5 = (pick(data, c, 'base', mach, 0, 5) for c in ('CS', 'CMl', 'CMn'))
    cym5, clm5, cnm5 = (pick(data, c, 'base', mach, 0, -5) for c in ('CS', 'CMl', 'CMn'))
    if None not in (cy5, cl_5, cn5, cym5, clm5, cnm5):
        rows['CY_beta_per_rad'] = (cy5 - cym5) / (2 * rad5)
        rows['Cl_beta_per_rad'] = (cl_5 - clm5) / (2 * rad5)
        rows['Cn_beta_per_rad'] = (cn5 - cnm5) / (2 * rad5)
    for coeff, suffix, name in (('CMl', 'dp', 'Clp'), ('CMm', 'dq', 'Cmq'), ('CMn', 'dr', 'Cnr'), ('CMm', 'dele', 'Cm_ele'),
                                ('CL', 'dele', 'CL_ele'), ('CMl', 'dailR', 'Cl_ailR'), ('CMl', 'dailL', 'Cl_ailL'),
                                ('CMn', 'drud', 'Cn_rud'), ('CMl', 'drud', 'Cl_rud'), ('CS', 'drud', 'CY_rud'),
                                ('CMl', 'dele', 'Cl_ele'), ('CMn', 'dailR', 'Cn_ailR')):
        value = pick(data, coeff, suffix, mach, 0, 0)
        if value is not None:
            rows[f'{name}_per_rad'] = value
    return rows


def avl_summary(path):
    """The same numbers from an AVL MCP result.json (as aircraft/avl/run_table.py reads it), for --compare-avl."""
    sys.path.insert(0, str(ROOT / 'aircraft' / 'avl'))
    import run_table as avl  # noqa: E402
    return avl.summary(path, json.loads((ROOT / 'aircraft' / 'avl' / 'table.json').read_text()))


def comparison(data, config, avl_path, cd_fix):
    """VSP against AVL on the same grid, body axes, at beta 0 and the lowest Mach (markdown).

    AVL's CD is the induced drag only and the model adds CD_fix_AVL; VSPAERO's CD already has its own skin-friction
    estimate. cd_fix = (CD_fix_AVL, CD_fix_VSP) is added to each for the drag column."""
    mach = min(config['mach'])
    cases = json.loads(Path(avl_path).read_text())['results']

    def avl(alpha, beta):
        for c in cases:
            f = c['total']['fields']
            if abs(f['Mach'] - mach) < 1e-9 and f['Alpha'] == alpha and f['Beta'] == beta:
                return c
        return None

    deg = 180.0 / math.pi
    lines = [f'Mach {mach}, beta 0, body axes, per rad; moment reference x = {config["reference"]["xcg"]} m (AVL Xref).', '',
             '| alpha | CL VSP／AVL | Cm VSP／AVL | CD＋fix VSP／AVL | Cmq | Clp | Cnr | Cm per elevator | Cl per right aileron | Cn per rudder |',
             '|---:|---|---|---|---|---|---|---|---|---|']
    for alpha in config['alpha_deg']:
        a = avl(alpha, 0)
        if a is None:
            continue
        f, bd, bc = a['total']['fields'], a['body']['derivatives'], a['body']['control_derivatives']

        def v(coeff, suffix):
            return pick(data, coeff, suffix, mach, alpha, 0)
        lines.append(
            f"| {alpha} | {v('CL', 'base'):.3f}／{f['CLtot']:.3f} | {v('CMm', 'base'):.3f}／{f['Cmtot']:.3f} | "
            f"{v('CD', 'base') + cd_fix[1]:.4f}／{f['CDtot'] + cd_fix[0]:.4f} | {v('CMm', 'dq'):.2f}／{bd['Cmq']:.2f} | "
            f"{v('CMl', 'dp'):.3f}／{bd['Clp']:.3f} | {v('CMn', 'dr'):.4f}／{bd['Cnr']:.4f} | "
            f"{v('CMm', 'dele'):.3f}／{bc['elevator']['Cm'] * deg:.3f} | {v('CMl', 'dailR'):.4f}／{bc['aileronR']['Cl'] * deg:.4f} | "
            f"{v('CMn', 'drud'):.4f}／{bc['rudder']['Cn'] * deg:.4f} |")
    lines += ['', 'Sideslip slopes from the beta grid (beta -5 and +5; the model interpolates the table, it does not use d/dbeta):', '',
              '| alpha | CY per rad VSP／AVL | Cl per rad VSP／AVL | Cn per rad VSP／AVL |', '|---:|---|---|---|']
    step = 2 * math.radians(5.0)
    for alpha in config['alpha_deg']:
        hi, lo = avl(alpha, 5), avl(alpha, -5)
        if hi is None or lo is None or pick(data, 'CS', 'base', mach, alpha, 5) is None:
            continue
        fh, fl = hi['total']['fields'], lo['total']['fields']

        def slope(coeff):
            return (pick(data, coeff, 'base', mach, alpha, 5) - pick(data, coeff, 'base', mach, alpha, -5)) / step
        lines.append(f"| {alpha} | {slope('CS'):.3f}／{(fh['CYtot'] - fl['CYtot']) / step:.3f} | "
                     f"{slope('CMl'):.4f}／{(fh['Cltot'] - fl['Cltot']) / step:.4f} | {slope('CMn'):.4f}／{(fh['Cntot'] - fl['Cntot']) / step:.4f} |")
    return '\n'.join(lines) + '\n'


def wind_moments(data, ref):
    """CMl, CMm, CMn rotated from body to wind axes, case by case, for the model's VSP path.

    VSPAERO's CMl/CMm/CMn are body axes (CMl = -CMx at every alpha), but the model feeds CD, CS, CL, CMl, CMm, CMn to an
    Aerodynamic Forces and Moments block with input axes 'Wind' (the AVL path uses 'Stability' with Cl', Cn'). The
    rotation is constant within a case, so the rate and control derivatives rotate the same way; da and db would also
    need the rotation's own derivative, but the model does not use them.

    CMl and CMn are per bref, CMm per cref, so the moments are rotated times their reference lengths and divided back.
    The first version (2026-11-02) rotated the coefficients as they were: in sideslip it put sin(beta) * CMm straight
    into CMl (Clb about -0.215 instead of about -0.05 at alpha 5)."""
    out = json.loads(json.dumps(data))
    lengths = (ref['bref'], ref['cref'], ref['bref'])
    for k, (alpha, beta) in enumerate(zip(data['aoa'], data['beta'])):
        a, b = math.radians(alpha), math.radians(beta)
        rotation = ((math.cos(a) * math.cos(b), math.sin(b), math.sin(a) * math.cos(b)),
                    (-math.cos(a) * math.sin(b), math.cos(b), -math.sin(a) * math.sin(b)),
                    (-math.sin(a), 0.0, math.cos(a)))
        for suffix in data['CMl']:
            body = [data[c][suffix][k] * n for c, n in zip(('CMl', 'CMm', 'CMn'), lengths)]
            for row, coeff, n in zip(rotation, ('CMl', 'CMm', 'CMn'), lengths):
                out[coeff][suffix][k] = sum(r * m for r, m in zip(row, body)) / n
    return out


def write_mat(data, suffixes, out, ref):
    from mcp_build import evaluate
    source = out / 'data_out.json'
    source.write_text(json.dumps(wind_moments(data, ref)))
    target = ROOT / 'model' / 'Skysurfer.mat'
    code = f'''d = jsondecode(fileread('{source}'));
data_out = struct('aoa', d.aoa(:).', 'beta', d.beta(:).', 'mach', d.mach(:).');
names = {{{', '.join(repr(c) for c in COEFFS)}}};
suffixes = {{{', '.join(repr(s) for s in suffixes)}}};
for i = 1:numel(names)
    s = struct();
    for j = 1:numel(suffixes), s.(suffixes{{j}}) = d.(names{{i}}).(suffixes{{j}})(:).'; end
    data_out.(names{{i}}) = s;
end
save('{target}', 'data_out');
disp('MAT_WRITTEN');'''
    text = evaluate(ROOT, code)
    if 'MAT_WRITTEN' not in text:
        raise SystemExit('MATLAB did not write the MAT file:\n' + text[-2000:])
    return target


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--config', type=Path, default=HERE / 'table.json')
    parser.add_argument('--out', type=Path)
    parser.add_argument('--alpha', type=float, nargs='+', help='override the alpha grid (deg), for a quick look')
    parser.add_argument('--beta', type=float, nargs='+')
    parser.add_argument('--mach', type=float, nargs='+')
    parser.add_argument('--compare-avl', type=Path, help='an AVL MCP result.json of the same grid')
    parser.add_argument('--jobs', type=int, default=1, help='VSPAERO processes at once, each with ncpu/jobs threads')
    parser.add_argument('--write-mat', action='store_true', help='write model/Skysurfer.mat (needs MATLAB)')
    parser.add_argument('--merge-stab', type=Path, nargs='+', help='no solve: the result from these .stab files')
    parser.add_argument('--vsp-version', default='OpenVSP 3.55.0', help='with --merge-stab: recorded in result.json')
    parser.add_argument('--from-result', type=Path, help='the result.json of an earlier run: compare or write, no solve')
    parser.add_argument('--cd-fix', type=float, nargs=2, default=(0.030, 0.0), metavar=('AVL', 'VSP'),
                        help='CD_fix_AVL and CD_fix_VSP added in the drag column of the comparison')
    args = parser.parse_args()
    if args.from_result:
        report = json.loads(args.from_result.read_text())
        if args.compare_avl:
            text = comparison(report['data_out'], report['config'], args.compare_avl, args.cd_fix)
            (args.from_result.parent / 'comparison.md').write_text(text)
            print(text)
        if args.write_mat:
            suffixes = list(DERIVS) + ['d' + g['name'] for g in report['config']['groups']]
            print(f"MAT written: {write_mat(report['data_out'], suffixes, args.from_result.parent, report['config']['reference'])}; model/ changed, next ./runbridge model-cycle")
        return 0
    config = json.loads(args.config.read_text())
    for key, value in (('alpha_deg', args.alpha), ('beta_deg', args.beta), ('mach', args.mach)):
        if value:
            config[key] = value
    if args.write_mat and (args.alpha or args.beta or args.mach):
        parser.error('--write-mat needs the full grid of the config')
    import toolchain
    stamp = datetime.datetime.now(datetime.timezone.utc).strftime('%Y%m%d_%H%M%SZ')
    out = (args.out or toolchain.cache_root() / 'vsp_runs' / f'table_{stamp}').resolve()
    out.mkdir(parents=True, exist_ok=False)
    # One VSPAERO process per beta value, one after the other (--jobs N runs N at once). A single sweep of all 60 cases
    # grew to 22 GB and the kernel's OOM killer stopped it at case 57 on the 30 GB laptop (2026-11-02); 12 cases per
    # process stay small. Five at once were slower than one (41 s per solve each against about 9 s).
    # --merge-stab: build the result from .stab files of earlier runs instead, e.g. a run that stopped and its missing cases.
    groups = [g['name'] for g in config['groups']]
    if args.merge_stab:
        cases, seen = [], set()
        for path in args.merge_stab:
            for c in parse_stab(path.read_text(errors='replace'), groups):
                key = (round(c['mach'], 4), c['alpha_deg'], c['beta_deg'])
                if key not in seen:
                    seen.add(key)
                    cases.append(c)
        stab, seconds, version, jobs = [str(p) for p in args.merge_stab], 0.0, args.vsp_version, 0
    else:
        jobs = max(1, min(args.jobs, len(config['beta_deg'])))
        parts = []
        for beta in config['beta_deg']:
            part = dict(config, beta_deg=[beta], solver=dict(config['solver'], ncpu=max(1, config['solver']['ncpu'] // jobs)))
            folder = out / f'beta_{beta:+g}'
            folder.mkdir()
            parts.append((part, folder))
        with concurrent.futures.ThreadPoolExecutor(jobs) as pool:
            finished = list(pool.map(lambda pf: run(*pf), parts))
        cases = [c for stab, _, _ in finished for c in parse_stab(stab.read_text(errors='replace'), groups)]
        stab = [str(f[0]) for f in finished]
        seconds = sum(f[1] for f in finished) if jobs == 1 else max(f[1] for f in finished)
        version = finished[0][2]
    data, suffixes = table(cases, config)
    report = {'openvsp': version, 'seconds': round(seconds, 1), 'jobs': jobs, 'stab': stab, 'cases': len(cases),
              'config': config, 'summary': summary(data, config), 'data_out': data}
    if args.compare_avl:
        report['avl_summary'] = avl_summary(args.compare_avl)
    (out / 'result.json').write_text(json.dumps(report, indent=1))
    print(json.dumps({k: report[k] for k in ('openvsp', 'seconds', 'cases', 'summary')}, indent=1))
    if args.compare_avl:
        print(json.dumps({'avl': report['avl_summary']}, indent=1))
    if args.write_mat:
        print(f'MAT written: {write_mat(data, suffixes, out, config["reference"])}; model/ changed, next ./runbridge model-cycle')
    print(json.dumps({'out': str(out)}))
    return 0


if __name__ == '__main__':
    sys.exit(main())
