#!/usr/bin/env python3
"""Sanity checks for a JSBSim vehicle folder: mass properties, rest on the ground, static thrust, level trim.

    python3 tools/vehicle_check.py vehicles/testbird [--speeds 12 15 18 22] [--height 100]

The vehicle folder is a JSBSim aircraft directory (<name>/<name>.xml, Engines/, Systems/). The checks print what JSBSim
computes; they do not judge the vehicle against fixed limits. Use them to catch generated values that are off by orders of
magnitude (for example ground springs sized for a full-size aircraft) before the vehicle is used anywhere else.

Needs the JSBSim Python module (1.3.3), e.g. `pip install jsbsim==1.3.3`, or JSBSIM_PYTHON pointing to an unpacked wheel.
"""
import argparse
import json
import math
import os
import sys
import tempfile
from pathlib import Path

if os.environ.get('JSBSIM_PYTHON'):
    sys.path.insert(0, os.environ['JSBSIM_PYTHON'])
import jsbsim  # noqa: E402

FT = 0.3048
LBF = 4.4482216152605
SLUG_FT2 = 1.35581795


def load(folder, dt):
    folder = Path(folder).resolve()
    name = folder.name
    root = Path(tempfile.mkdtemp(prefix='vehicle_check_'))
    (root / 'aircraft').mkdir()
    (root / 'aircraft' / name).symlink_to(folder)
    fdm = jsbsim.FGFDMExec(str(root), None)
    fdm.set_debug_level(0)
    fdm.set_engine_path(str(Path('aircraft') / name / 'Engines'))
    fdm.set_systems_path(str(Path('aircraft') / name / 'Systems'))
    fdm.set_dt(dt)  # before load_model: components keep the dt they are loaded with
    if not fdm.load_model(name):
        raise SystemExit(f'JSBSim could not load {folder}')
    return fdm


def start(fdm, height_m, speed_m_s, theta_deg=0.0):
    fdm['ic/lat-geod-deg'] = 22.91
    fdm['ic/long-gc-deg'] = 120.31
    fdm['ic/psi-true-deg'] = 0.0
    fdm['ic/h-agl-ft'] = height_m / FT
    fdm['ic/u-fps'] = speed_m_s / FT
    fdm['ic/v-fps'] = 0.0
    fdm['ic/w-fps'] = 0.0
    fdm['ic/theta-deg'] = theta_deg
    fdm['ic/phi-deg'] = 0.0
    if not fdm.run_ic():
        raise SystemExit('run_ic failed')
    fdm['propulsion/set-running'] = -1


def controls(fdm, throttle=0.0, elevator=0.0, brake=0.0):
    fdm['fcs/throttle-cmd-norm'] = throttle
    fdm['fcs/elevator-cmd-norm'] = elevator
    fdm['fcs/aileron-cmd-norm'] = 0.0
    fdm['fcs/rudder-cmd-norm'] = 0.0
    fdm['fcs/left-brake-cmd-norm'] = brake
    fdm['fcs/right-brake-cmd-norm'] = brake


def run(fdm, seconds):
    for _ in range(int(round(seconds / fdm.get_delta_t()))):
        if not fdm.run():
            return False
    return True


def gear(fdm):
    # Bogeys (wheels) only: structure contacts have no WOW/compression properties.
    out = []
    pm = fdm.get_property_manager()
    for i in range(fdm.get_ground_reactions().get_num_gear_units()):
        if pm.hasNode(f'gear/unit[{i}]/WOW'):
            out.append({'unit': i, 'wow': bool(fdm[f'gear/unit[{i}]/WOW']),
                        'compression_m': round(fdm[f'gear/unit[{i}]/compression-ft'] * FT, 4)})
    return out


def fly_level(folder, speed, height, dt, seconds=60.0, average=5.0):
    """Steady level flight by flying it: the elevator holds the airspeed through pitch attitude, the throttle holds the
    height, the ailerons hold the wings level. Returns the averages over the last `average` seconds."""
    fdm = load(folder, dt)
    start(fdm, height, speed, theta_deg=1.0)
    theta_i, thr_i = math.radians(1.0), 0.7
    sums, n = {}, 0
    steps = int(round(seconds / dt))
    for k in range(steps):
        vt = fdm['velocities/vt-fps'] * FT
        hdot = fdm['velocities/h-dot-fps'] * FT
        h = fdm['position/h-agl-ft'] * FT
        theta_i = min(0.26, max(-0.26, theta_i - 0.01 * (speed - vt) * dt))
        theta_c = min(0.26, max(-0.26, theta_i - 0.02 * (speed - vt)))
        elev = min(1.0, max(-1.0, 1.0 * (fdm['attitude/theta-rad'] - theta_c) + 0.2 * fdm['velocities/q-rad_sec']))  # + nose down
        e_h = -hdot + 0.1 * (height - h)
        thr_i = min(1.0, max(0.0, thr_i + 0.05 * e_h * dt))
        thr = min(1.0, max(0.0, thr_i + 0.1 * e_h))
        ail = min(1.0, max(-1.0, -1.0 * fdm['attitude/phi-rad'] - 0.1 * fdm['velocities/p-rad_sec']))  # + rolls right
        controls(fdm, throttle=thr, elevator=elev)
        fdm['fcs/aileron-cmd-norm'] = ail
        if not fdm.run():
            return {'ok': False, 'error': f'stopped at {k * dt:.1f} s'}
        if k >= steps - int(round(average / dt)):
            vals = {'speed_m_s': vt, 'climb_m_s': hdot, 'alpha_deg': fdm['aero/alpha-deg'], 'theta_deg': fdm['attitude/theta-deg'],
                    'phi_deg': fdm['attitude/phi-deg'], 'elevator_norm': elev, 'aileron_norm': ail, 'throttle_norm': thr,
                    'thrust_N': fdm['propulsion/engine/thrust-lbs'] * LBF, 'rpm': fdm['propulsion/engine/propeller-rpm'],
                    'power_W': fdm['propulsion/engine/power-hp'] * 745.7}
            for key, val in vals.items():
                sums[key] = sums.get(key, 0.0) + val
            n += 1
    out = {key: round(val / n, 4) for key, val in sums.items()}
    out['ok'] = abs(out['climb_m_s']) < 0.05 and abs(out['speed_m_s'] - speed) < 0.1
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('folder')
    p.add_argument('--speeds', type=float, nargs='+', default=[12.0, 15.0, 18.0, 22.0], help='trim airspeeds, m/s')
    p.add_argument('--height', type=float, default=100.0, help='trim height above ground, m')
    p.add_argument('--dt', type=float, default=0.002)
    a = p.parse_args()
    report = {'jsbsim': jsbsim.__version__, 'vehicle': str(a.folder)}

    fdm = load(a.folder, a.dt)
    start(fdm, 1.0, 0.0)
    mass_kg = fdm['inertia/mass-slugs'] * 14.5939029
    report['mass'] = {'mass_kg': round(mass_kg, 3), 'weight_N': round(mass_kg * 9.80665, 2),
                      'cg_m': [round(fdm[f'inertia/cg-{c}-in'] * 0.0254, 3) for c in 'xyz'],
                      'inertia_kg_m2': {k: round(fdm[f'inertia/{k}-slugs_ft2'] * SLUG_FT2, 4) for k in ['ixx', 'iyy', 'izz', 'ixz']},
                      'wing_area_m2': round(fdm['metrics/Sw-sqft'] * FT * FT, 3), 'span_m': round(fdm['metrics/bw-ft'] * FT, 3),
                      'chord_m': round(fdm['metrics/cbarw-ft'] * FT, 3)}

    # Rest: dropped from 1 m with the engine idle and the brakes on, 10 s to settle.
    controls(fdm, brake=1.0)
    ok = run(fdm, 10.0)
    report['ground_rest'] = {'ran': ok, 'h_agl_m': round(fdm['position/h-agl-ft'] * FT, 4),
                             'h_dot_m_s': round(fdm['velocities/h-dot-fps'] * FT, 4), 'theta_deg': round(fdm['attitude/theta-deg'], 2),
                             'gear': gear(fdm)}

    # Static thrust: full throttle with the brakes on, 3 s.
    controls(fdm, throttle=1.0, brake=1.0)
    run(fdm, 3.0)
    thrust_N = fdm['propulsion/engine/thrust-lbs'] * LBF
    report['static_thrust'] = {'thrust_N': round(thrust_N, 2), 'thrust_to_weight': round(thrust_N / (mass_kg * 9.80665), 3),
                               'rpm': round(fdm['propulsion/engine/propeller-rpm'], 0),
                               'power_W': round(fdm['propulsion/engine/power-hp'] * 745.7, 1) if fdm.get_property_manager().hasNode('propulsion/engine/power-hp') else None}

    # Level flight at each speed. JSBSim's FGTrim is tried first; it fails for electric motors whose time constant is
    # shorter than about 0.25 s, because FGPropulsion::GetSteadyState marches the propeller in fixed 0.5 s steps.
    # The steady state is then found by flying: PI loops hold the airspeed (throttle) and zero climb rate (elevator)
    # for 40 s, and the last 5 s are averaged.
    trims = []
    for v in a.speeds:
        row = {'speed_m_s': v}
        fdm = load(a.folder, a.dt)
        start(fdm, a.height, v)
        controls(fdm, throttle=0.5)
        try:
            fdm['simulation/do_simple_trim'] = 1
            row['fgtrim'] = {'ok': True, 'alpha_deg': round(fdm['aero/alpha-deg'], 3), 'elevator_norm': round(fdm['fcs/elevator-cmd-norm'], 4),
                             'throttle_norm': round(fdm['fcs/throttle-cmd-norm'], 4)}
        except Exception as exc:  # noqa: BLE001  (JSBSim raises its own TrimFailureError)
            row['fgtrim'] = {'ok': False, 'error': str(exc).splitlines()[0][:120]}
        row['flown'] = fly_level(a.folder, v, a.height, a.dt)
        trims.append(row)
    report['level_trim'] = trims
    print(json.dumps(report, indent=1, default=lambda x: None if isinstance(x, float) and math.isnan(x) else x))


if __name__ == '__main__':
    main()
