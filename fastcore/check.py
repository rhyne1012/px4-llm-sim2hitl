#!/usr/bin/env python3
"""Check a generated fast core against JSBSim.

    JSBSIM_PYTHON=<unpacked jsbsim 1.3.3 wheel> <python with numpy> fastcore/check.py vehicles/testbird [--out DIR]

1. Snapshots: JSBSim flies from random states with random inputs; at a random instant its full state (including the
   actuator positions, the propeller speed and the accelerations of the previous frame) goes into the core, and every
   force, moment, aerodynamic function and propeller value is compared. JSBSim runs on a non-rotating Earth here, so
   the two must agree to rounding: this tests that the translation is exact.
2. Flights: from trimmed level flight both fly the same open-loop input sequences, JSBSim as simhost runs it (1 ms,
   Adams-Bashforth 2, rotating WGS84 Earth), the core at 1 ms and at 4 ms. The differences are what the core's
   simplifications cost (step size, flat Earth, alphadot and cl-squared timing).

Writes <out>/check.json and exits 1 if a limit is exceeded.
"""
import argparse
import json
import math
import os
import sys
import tempfile
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / 'tools'))
if os.environ.get('JSBSIM_PYTHON'):
    sys.path.insert(0, os.environ['JSBSIM_PYTHON'])
import gen  # noqa: E402
from fastcore import Core, euler_to_quat, quat_to_euler  # noqa: E402
from vehicle_check import load  # noqa: E402

FT = 0.3048
LBF = 4.4482216152605
FTLBF = LBF * FT
PSF = LBF / FT ** 2
SLUGFT3 = (LBF / FT) / FT ** 3
LAT0, LON0 = 22.91, 120.31

# Limits. Snapshots: relative to max(|JSBSim value|, the floor of the quantity). Flights: set by a person on 2026-11-27
# after the first Testbird measurement (worst 0.08 m, 0.09 deg, 0.008 m/s); see fastcore/README.md.
SNAPSHOT_LIMIT = 1e-9
FLIGHT_LIMITS = {'dt_0.004': {'pos_m': 0.3, 'att_deg': 0.3, 'airspeed_mps': 0.03}, 'horizon_s': 10.0}

NON_ROTATING = '<?xml version="1.0"?>\n<planet name="Earth"><rotation_rate unit="RAD/SEC"> 0 </rotation_rate></planet>\n'


def jsb(vehicle, dt, rotating=True):
    fdm = load(vehicle, dt)
    for k in ('rate/rotational', 'rate/translational', 'position/rotational', 'position/translational'):
        fdm[f'simulation/integrator/{k}'] = 3  # Adams-Bashforth 2, as simhost
    if not rotating:
        p = Path(tempfile.mkdtemp(prefix='fastcore_planet_')) / 'planet.xml'
        p.write_text(NON_ROTATING)
        fdm.load_planet(str(p), False)
    return fdm


def ic(fdm, h_agl_m, uvw, euler_deg, pqr, lat=LAT0, lon=LON0):
    fdm['ic/lat-geod-deg'] = lat
    fdm['ic/long-gc-deg'] = lon
    fdm['ic/terrain-elevation-ft'] = 0.0
    fdm['ic/h-agl-ft'] = h_agl_m / FT
    fdm['ic/u-fps'], fdm['ic/v-fps'], fdm['ic/w-fps'] = (c / FT for c in uvw)
    fdm['ic/phi-deg'], fdm['ic/theta-deg'], fdm['ic/psi-true-deg'] = euler_deg
    fdm['ic/p-rad_sec'], fdm['ic/q-rad_sec'], fdm['ic/r-rad_sec'] = pqr
    if not fdm.run_ic():
        raise SystemExit('JSBSim run_ic failed')
    fdm['propulsion/set-running'] = -1


def set_inputs(fdm, core, u):
    for name, i in core.U.items():
        fdm[name] = float(u[i])


def capture(fdm, core, x, prev_uvwdot):
    """JSBSim's state into a core state row; the NED origin is the current position."""
    x[:] = 0.0
    x[core.X['u_mps']:core.X['u_mps'] + 3] = [fdm[f'velocities/{c}-fps'] * FT for c in 'uvw']
    x[6:10] = euler_to_quat(fdm['attitude/phi-rad'], fdm['attitude/theta-rad'], fdm['attitude/psi-rad'])
    x[10:13] = [fdm[f'velocities/{c}-rad_sec'] for c in 'pqr']
    x[core.X['omega_rps[0]']] = fdm['propulsion/engine/propeller-rpm'] * 2 * math.pi / 60
    for name, i in core.X.items():
        if name.startswith('held:'):
            x[i] = fdm[name[5:]]
    x[core.X['aux:udot_mps2']:core.X['aux:udot_mps2'] + 3] = prev_uvwdot
    x[core.X['aux:cl_squared']] = fdm['aero/cl-squared']
    x[core.X['aux:fcs_initialized']] = 1.0


def env_of(fdm, core):
    e = core.env(1, gravity=9.80665, origin_alt_msl=fdm['position/h-sl-ft'] * FT, ground_alt_msl=0.0)
    e[0, 0:3] = [fdm[f'atmosphere/total-wind-{c}-fps'] * FT for c in ('north', 'east', 'down')]
    return e


# -- 1. snapshots -------------------------------------------------------------------------------------------------------

def snapshots(vehicle, core, n, seed):
    rng = np.random.default_rng(seed)
    floors = {'force_N': 0.01, 'moment_Nm': 0.001, 'angle_rad': 1e-6, 'rate_rps': 1e-6, 'qbar_Pa': 0.01, 'rho': 1e-6,
              'rpm': 0.01, 'omega_dot': 0.01, 'current_A': 0.001, 'fn': 1e-4}
    worst = {}
    used = []
    t0 = time.time()

    def cmp(key, kind, a, b):
        e = float(abs(a - b) / max(abs(b), floors[kind]))
        if e > worst.get(key, (0.0,))[0]:
            worst[key] = (e, float(a), float(b))

    for s in range(n):
        fdm = jsb(vehicle, 0.001, rotating=False)
        V = rng.uniform(8, 32)
        al, be = math.radians(rng.uniform(-25, 35)), math.radians(rng.uniform(-20, 20))
        uvw = (V * math.cos(al) * math.cos(be), V * math.sin(be), V * math.sin(al) * math.cos(be))
        eul = (rng.uniform(-70, 70), rng.uniform(-45, 45), rng.uniform(0, 360))
        pqr = rng.uniform(-1.5, 1.5, 3)
        ic(fdm, rng.uniform(150, 1500), uvw, eul, pqr)
        u = np.zeros(core.nu)
        u[core.U['fcs/throttle-cmd-norm[0]']] = rng.uniform(0.2, 1.0)
        set_inputs(fdm, core, u)
        for _ in range(300):        # spin the propeller up
            fdm.run()
        for name, i in core.U.items():
            u[i] = rng.uniform(0, 1) if 'throttle' in name else (rng.uniform(-1, 1) if 'trim' not in name else rng.uniform(-0.2, 0.2))
        if rng.uniform() < 0.5:     # wind for half of them
            for c in ('north', 'east', 'down'):
                fdm[f'atmosphere/wind-{c}-fps'] = rng.uniform(-8, 8) / FT * (0.3 if c == 'down' else 1.0)
        set_inputs(fdm, core, u)
        for _ in range(int(rng.integers(5, 200))):
            fdm.run()
        prev = [fdm[f'accelerations/{c}dot-ft_sec2'] * FT for c in 'uvw']
        rpm_prev = fdm['propulsion/engine/propeller-rpm']
        fdm.run()
        x = core.zeros(1)
        capture(fdm, core, x[0], prev)
        x[0, core.X['omega_rps[0]']] = rpm_prev * 2 * math.pi / 60   # the frame computed its forces from this speed
        e = env_of(fdm, core)
        xd, y = core.eval(x, e, jsbsim_order=True)
        Y = {k: y[0, i] for k, i in core.Y.items()}
        for i, c in enumerate('xyz'):
            cmp(f'aero_f{c}', 'force_N', Y[f'aero_f{c}_N'], fdm[f'forces/fb{c}-aero-lbs'] * LBF)
            cmp(f'prop_f{c}', 'force_N', Y[f'prop_f{c}_N[0]'], fdm[f'forces/fb{c}-prop-lbs'] * LBF)
            cmp(f'total_f{c}', 'force_N', Y[f'f{c}_N'], fdm[f'forces/fb{c}-total-lbs'] * LBF)
        for c, m in zip('xyz', 'lmn'):
            cmp(f'aero_m{c}', 'moment_Nm', Y[f'aero_m{c}_Nm'], fdm[f'moments/{m}-aero-lbsft'] * FTLBF)
            cmp(f'prop_m{c}', 'moment_Nm', Y[f'prop_m{c}_Nm[0]'], fdm[f'moments/{m}-prop-lbsft'] * FTLBF)
            cmp(f'total_m{c}', 'moment_Nm', Y[f'm{c}_Nm'], fdm[f'moments/{m}-total-lbsft'] * FTLBF)
        cmp('alpha', 'angle_rad', Y['alpha_rad'], fdm['aero/alpha-rad'])
        cmp('beta', 'angle_rad', Y['beta_rad'], fdm['aero/beta-rad'])
        cmp('alphadot', 'rate_rps', Y['alphadot_rps'], fdm['aero/alphadot-rad_sec'])
        cmp('qbar', 'qbar_Pa', Y['qbar_Pa'], fdm['aero/qbar-psf'] * PSF)
        cmp('rho', 'rho', Y['rho_kgm3'], fdm['atmosphere/rho-slugs_ft3'] * SLUGFT3)
        cmp('thrust', 'force_N', Y['thrust_N[0]'], fdm['propulsion/engine/thrust-lbs'] * LBF)
        cmp('current', 'current_A', Y['current_A[0]'], fdm['propulsion/engine/current-amperes'])
        cmp('rpm', 'rpm', Y['rpm[0]'], rpm_prev)
        omega_dot = (fdm['propulsion/engine/propeller-rpm'] - rpm_prev) / 0.001 * 2 * math.pi / 60
        cmp('omega_dot', 'omega_dot', xd[0, core.X['omega_rps[0]']], omega_dot)
        for name in core.layout['y']:
            if name.startswith('fn:'):
                cmp(name, 'fn', Y[name], fdm[name[3:]])
        used.append({'V': round(V, 2), 'alpha_deg': round(math.degrees(al), 1), 'beta_deg': round(math.degrees(be), 1),
                     'rpm': round(rpm_prev), 'elev_pos_rad': round(fdm['fcs/elevator-pos-rad'], 4)})
    worst_all = max(v[0] for v in worst.values())
    return {'n': n, 'seed': seed, 'seconds': round(time.time() - t0, 1), 'limit': SNAPSHOT_LIMIT,
            'max_relative_error': float(worst_all), 'pass': bool(worst_all <= SNAPSHOT_LIMIT),
            'worst': {k: {'rel': v[0], 'core': v[1], 'jsbsim': v[2]} for k, v in sorted(worst.items(), key=lambda kv: -kv[1][0])[:12]},
            'ranges': {k: [min(s[k] for s in used), max(s[k] for s in used)] for k in used[0]}}


# -- 2. flights ---------------------------------------------------------------------------------------------------------

def ecef(lat, lon, h):
    a, f = 6378137.0, 1 / 298.257223563
    e2 = f * (2 - f)
    la, lo = math.radians(lat), math.radians(lon)
    N = a / math.sqrt(1 - e2 * math.sin(la) ** 2)
    return np.array([(N + h) * math.cos(la) * math.cos(lo), (N + h) * math.cos(la) * math.sin(lo), (N * (1 - e2) + h) * math.sin(la)])


def ned_of(lat0, lon0, h0):
    la, lo = math.radians(lat0), math.radians(lon0)
    R = np.array([[-math.sin(la) * math.cos(lo), -math.sin(la) * math.sin(lo), math.cos(la)],
                  [-math.sin(lo), math.cos(lo), 0.0],
                  [-math.cos(la) * math.cos(lo), -math.cos(la) * math.sin(lo), -math.sin(la)]])
    o = ecef(lat0, lon0, h0)
    return lambda lat, lon, h: R @ (ecef(lat, lon, h) - o)


def trim(vehicle, speed=17.0, height=100.0, seconds=30.0):
    """Fly JSBSim to steady level flight (the controller of tools/vehicle_check.py), then hold the last commands."""
    fdm = jsb(vehicle, 0.001)
    ic(fdm, height, (speed, 0, 0), (0, 1.0, 0), (0, 0, 0))
    theta_i, thr_i = math.radians(1.0), 0.7
    dt = 0.001
    for _ in range(int(seconds / dt)):
        vt = fdm['velocities/vt-fps'] * FT
        hdot = fdm['velocities/h-dot-fps'] * FT
        h = fdm['position/h-agl-ft'] * FT
        theta_i = min(0.26, max(-0.26, theta_i - 0.01 * (speed - vt) * dt))
        theta_c = min(0.26, max(-0.26, theta_i - 0.02 * (speed - vt)))
        elev = min(1.0, max(-1.0, 1.0 * (fdm['attitude/theta-rad'] - theta_c) + 0.2 * fdm['velocities/q-rad_sec']))
        e_h = -hdot + 0.1 * (height - h)
        thr_i = min(1.0, max(0.0, thr_i + 0.05 * e_h * dt))
        thr = min(1.0, max(0.0, thr_i + 0.1 * e_h))
        ail = min(1.0, max(-1.0, -1.0 * fdm['attitude/phi-rad'] - 0.1 * fdm['velocities/p-rad_sec']))
        rud = min(1.0, max(-1.0, -0.5 * fdm['velocities/r-rad_sec']))
        fdm['fcs/throttle-cmd-norm'], fdm['fcs/elevator-cmd-norm'] = thr, elev
        fdm['fcs/aileron-cmd-norm'], fdm['fcs/rudder-cmd-norm'] = ail, rud
        fdm.run()
    for _ in range(int(1.0 / dt)):   # hold the last commands so the actuators settle on them
        fdm.run()
    return fdm


def cases(rng):
    def doublet(name, amp, t0=1.0, width=1.0):
        return lambda t: {name: amp if t0 <= t < t0 + width else (-amp if t0 + width <= t < t0 + 2 * width else 0.0)}
    ph = rng.uniform(0, 2 * math.pi, (4, 3))
    fr = np.array([0.2, 0.55, 1.3])

    def multisine(t):
        s = [float(sum(0.05 * math.sin(2 * math.pi * f * t + p) for f, p in zip(fr, ph[i]))) for i in range(4)]
        return {'fcs/elevator-cmd-norm': s[0], 'fcs/aileron-cmd-norm': s[1], 'fcs/rudder-cmd-norm': s[2],
                'fcs/throttle-cmd-norm[0]': 2 * s[3]}
    return {
        'hold': (lambda t: {}, None),
        'elevator_doublet': (doublet('fcs/elevator-cmd-norm', 0.15), None),
        'aileron_doublet': (doublet('fcs/aileron-cmd-norm', 0.2), None),
        'rudder_doublet': (doublet('fcs/rudder-cmd-norm', 0.3), None),
        'throttle_steps': (lambda t: {'fcs/throttle-cmd-norm[0]': 0.3 if 1 <= t < 5 else (-0.4 if 5 <= t < 9 else 0.0)}, None),
        'multisine': (multisine, None),
        'crosswind_aileron': (doublet('fcs/aileron-cmd-norm', 0.2), (0.0, 5.0, 0.0)),
        'pull_to_stall': (lambda t: {'fcs/elevator-cmd-norm': -0.8 if 1 <= t < 4 else 0.0,
                                     'fcs/throttle-cmd-norm[0]': -0.6 if 1 <= t < 4 else 0.0}, None),
    }


def flights(vehicle, core, seed, T=20.0):
    rng = np.random.default_rng(seed)
    base = trim(vehicle)
    names = ['fcs/throttle-cmd-norm[0]', 'fcs/elevator-cmd-norm', 'fcs/aileron-cmd-norm', 'fcs/rudder-cmd-norm']
    trim_u = {n: base[n] for n in names}
    for n in core.U:
        trim_u.setdefault(n, 0.0)
    out = {'trim': {k: round(v, 4) for k, v in trim_u.items() if k in names}}
    out['trim']['airspeed_mps'] = round(base['velocities/vt-fps'] * FT, 3)
    out['trim']['alpha_deg'] = round(base['aero/alpha-deg'], 3)
    # gravity the core should use here: JSBSim's own at this place, from an instance at rest in the air
    g0 = jsb(vehicle, 0.001)
    ic(g0, 100.0, (0, 0, 0), (0, 0, 0), (0, 0, 0))
    gravity = g0['accelerations/wdot-ft_sec2'] * FT
    out['gravity_mps2'] = gravity
    for name, (fn, wind) in cases(rng).items():
        fdm = trim(vehicle)
        if wind is not None:
            for c, w in zip(('north', 'east', 'down'), wind):
                fdm[f'atmosphere/wind-{c}-fps'] = w / FT
        lat0, lon0, h0 = fdm['position/lat-geod-deg'], fdm['position/long-gc-deg'], fdm['position/h-sl-ft'] * FT
        ned = ned_of(lat0, lon0, h0)
        x0 = core.zeros(1)
        capture(fdm, core, x0[0], [fdm[f'accelerations/{c}dot-ft_sec2'] * FT for c in 'uvw'])
        e = env_of(fdm, core)
        e[0, 3] = gravity
        if wind is not None:        # JSBSim's total-wind properties update only in its next frame
            e[0, 0:3] = wind
        res = {}
        uarr0 = np.array([[trim_u[n_] for n_ in core.layout['u']]])
        for dt in (0.001, 0.004):
            x = x0.copy()
            core.reset(x, uarr0)    # actuator filters at rest on the trim commands, as JSBSim's after the hold
            x[0, core.X['aux:udot_mps2']:core.X['aux:udot_mps2'] + 3] = x0[0, core.X['aux:udot_mps2']:core.X['aux:udot_mps2'] + 3]
            uarr = uarr0.copy()
            traj_c = []
            for i in range(int(round(T / dt))):
                t = i * dt
                d = fn(t)
                for n_ in core.U:
                    uarr[0, core.U[n_]] = min(1.0, max(0.0 if 'throttle' in n_ else -1.0, trim_u[n_] + d.get(n_, 0.0)))
                y = core.step(x, uarr, e, dt=dt, k=1)
                tt = (i + 1) * dt
                if abs(tt / 0.1 - round(tt / 0.1)) < 1e-6:
                    traj_c.append((round(tt, 3), x[0, 0:3].copy(), x[0, 6:10].copy(), y[0, core.Y['airspeed_mps']], x[0, 10:13].copy(), y[0, core.Y['rpm[0]']]))
            res[dt] = traj_c
        # JSBSim
        traj_j = []
        for i in range(int(round(T / 0.001))):
            t = i * 0.001
            d = fn(t)
            for n_ in core.U:
                fdm[n_] = min(1.0, max(0.0 if 'throttle' in n_ else -1.0, trim_u[n_] + d.get(n_, 0.0)))
            fdm.run()
            tt = (i + 1) * 0.001
            if abs(tt / 0.1 - round(tt / 0.1)) < 1e-6:
                q = euler_to_quat(fdm['attitude/phi-rad'], fdm['attitude/theta-rad'], fdm['attitude/psi-rad'])
                traj_j.append((round(tt, 3), ned(fdm['position/lat-geod-deg'], fdm['position/long-gc-deg'], fdm['position/h-sl-ft'] * FT),
                               q, fdm['velocities/vt-fps'] * FT, np.array([fdm[f'velocities/{c}-rad_sec'] for c in 'pqr']),
                               fdm['propulsion/engine/propeller-rpm']))
        case = {}
        for dt, tc in res.items():
            rows = []
            for (t, pc, qc, vc, wc, rc), (_, pj, qj, vj, wj, rj) in zip(tc, traj_j):
                dq = abs(float(np.dot(qc, qj)))
                rows.append((t, float(np.linalg.norm(pc - pj)), math.degrees(2 * math.acos(min(1.0, dq))), abs(vc - vj),
                             math.degrees(float(np.max(np.abs(wc - wj)))), abs(rc - rj)))
            def mx(h, col):
                return max(r[col] for r in rows if r[0] <= h + 1e-9)
            case[f'dt_{dt}'] = {f'{h:g}s': {'pos_m': round(mx(h, 1), 3), 'att_deg': round(mx(h, 2), 3),
                                            'airspeed_mps': round(mx(h, 3), 4), 'rate_dps': round(mx(h, 4), 3),
                                            'rpm': round(mx(h, 5), 1)} for h in (5.0, 10.0, 20.0)}
        end = traj_j[-1]
        case['jsbsim_end'] = {'pos_from_start_m': [round(float(c), 1) for c in end[1]], 'airspeed_mps': round(end[3], 2),
                              'euler_deg': [round(math.degrees(float(a)), 1) for a in quat_to_euler(end[2])]}
        out[name] = case
    lim = FLIGHT_LIMITS
    h = f'{lim["horizon_s"]:g}s'
    worst = {k: max(out[c]['dt_0.004'][h][k] for c in out if isinstance(out[c], dict) and 'dt_0.004' in out[c]) for k in lim['dt_0.004']}
    out['limits'] = lim
    out['worst_dt_0.004_' + h] = worst
    out['pass'] = bool(all(worst[k] <= lim['dt_0.004'][k] for k in worst))
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('vehicle')
    p.add_argument('--out', help='default build/fastcore/<vehicle>')
    p.add_argument('--snapshots', type=int, default=300)
    p.add_argument('--seed', type=int, default=1)
    p.add_argument('--skip-flights', action='store_true')
    a = p.parse_args()
    name = Path(a.vehicle).resolve().name
    out = Path(a.out) if a.out else Path('build/fastcore') / name
    gen.generate(a.vehicle, out)
    gen.build(out, name)
    core = Core(out)
    import jsbsim
    rep = {'vehicle': name, 'jsbsim': jsbsim.__version__, 'core': core.layout['sources_sha256'],
           'generator_sha256': core.layout['generator_sha256']}
    rep['snapshots'] = snapshots(a.vehicle, core, a.snapshots, a.seed)
    print(json.dumps({'snapshots': {k: rep['snapshots'][k] for k in ('n', 'max_relative_error', 'pass')}}), flush=True)
    if not a.skip_flights:
        rep['flights'] = flights(a.vehicle, core, a.seed)
        print(json.dumps({'flights_worst': rep['flights']['worst_dt_0.004_10s'], 'pass': rep['flights']['pass']}), flush=True)
    rep['pass'] = rep['snapshots']['pass'] and rep.get('flights', {'pass': True})['pass']
    (out / 'check.json').write_text(json.dumps(rep, indent=1) + '\n')
    print(json.dumps({'check': str(out / 'check.json'), 'pass': rep['pass']}))
    sys.exit(0 if rep['pass'] else 1)


if __name__ == '__main__':
    main()
