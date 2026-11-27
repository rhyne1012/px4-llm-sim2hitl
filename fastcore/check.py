#!/usr/bin/env python3
"""Check a generated fast core against JSBSim.

    JSBSIM_PYTHON=<unpacked jsbsim 1.3.3 wheel> <python with numpy> fastcore/check.py vehicles/testbird [--out DIR]

1. Snapshots (translation): JSBSim flies from random states with random inputs and random parameters (point masses,
   declared properties); at a random frame its full state (actuator positions, propeller speed, the previous frame's
   accelerations) goes into the core, and every force, moment, aerodynamic function, propeller value, mass property and
   angular acceleration is compared, half of them on a non-rotating Earth (with wind in half of those) and half on the
   rotating Earth (without wind, see snapshots()). They must agree to rounding.
2. Flight-control sequences (translation): random command sequences with random actuator failures switched on and off,
   with and without the servo chain, at 1 ms. The core's actuator positions must equal JSBSim's frame by frame; JSBSim's
   commands go through an independent Python servo chain (fastcore.ServoChainRef).
3. Flights (simplifications): from trimmed level flight both fly the same open-loop input sequences, JSBSim as simhost
   runs it (1 ms, Adams-Bashforth 2, rotating WGS84 Earth), the core at 1 ms and at 4 ms; also with the vehicle's
   configuration files and with failures during flight. The differences are what the core's simplifications cost.

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
import linear  # noqa: E402  (tools/linear.py: the trims)
from fastcore import Core, ServoChainRef, euler_to_quat, load_config, quat_to_euler  # noqa: E402
from vehicle_check import load  # noqa: E402

FT = 0.3048
LBF = 4.4482216152605
FTLBF = LBF * FT
SLUG = LBF / FT
SLUGFT2 = SLUG * FT * FT
PSF = LBF / FT ** 2
SLUGFT3 = SLUG / FT ** 3
LB_PER_KG = 1.0 / 0.45359237
IN_PER_M = 3.2808399 * 12.0
LAT0, LON0 = 22.91, 120.31

# Limits. Snapshots and flight-control sequences: relative error (snapshots, against max(|JSBSim value|, a floor per
# quantity)) and absolute error in rad (sequences). Flights, the largest difference within the horizon for the 4 ms core:
# set by a person on 2026-11-27, after the first Testbird measurement (worst 0.08 m, 0.09 deg, 0.008 m/s); failure
# flights, which can end in violent motion (aileron hardover: a spiral dive at 280 deg/s roll, where JSBSim at 1 ms
# itself differs from JSBSim at 0.25 ms by 0.16 deg), have their own attitude limit, set by the same person the same day.
SNAPSHOT_LIMIT = 1e-9
SEQUENCE_LIMIT_RAD = 1e-12
FLIGHT_LIMITS = {'horizon_s': 10.0,
                 'flight': {'pos_m': 0.3, 'att_deg': 0.3, 'airspeed_mps': 0.03},
                 'failure': {'pos_m': 0.3, 'att_deg': 1.0, 'airspeed_mps': 0.03}}
EARTH_RATE = 7.292115e-5

NON_ROTATING = '<?xml version="1.0"?>\n<planet name="Earth"><rotation_rate unit="RAD/SEC"> 0 </rotation_rate></planet>\n'


def split(settings):
    """JSBSim properties, and the servo chain's settings (avionics/servo/*, not JSBSim's)."""
    js = {k: v for k, v in settings.items() if not k.startswith('avionics/')}
    sv = {k: v for k, v in settings.items() if k.startswith('avionics/')}
    return js, (sv.get('avionics/servo/pwm-period-s', 0.0), sv.get('avionics/servo/pwm-phase-s', 0.0),
                sv.get('avionics/servo/delay-s', 0.0))


def jsb(vehicle, dt, rotating=True, settings=None):
    fdm = load(vehicle, dt)
    for k in ('rate/rotational', 'rate/translational', 'position/rotational', 'position/translational'):
        fdm[f'simulation/integrator/{k}'] = 3  # Adams-Bashforth 2, as simhost
    if not rotating:
        p = Path(tempfile.mkdtemp(prefix='fastcore_planet_')) / 'planet.xml'
        p.write_text(NON_ROTATING)
        fdm.load_planet(str(p), False)
    pm = fdm.get_property_manager()
    for k, v in split(settings or {})[0].items():
        if not pm.hasNode(k):
            raise SystemExit(f'JSBSim has no property {k}: setting it would create it silently')
        fdm[k] = v
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


PRE = ('aero/bi2vel', 'aero/ci2vel', 'aero/qbar-area', 'aero/alpha-wing-rad')


def capture(fdm, core, x, prev_uvwdot, prev_pre=None):
    """JSBSim's state into a core state row; the NED origin is the current position."""
    x[:] = 0.0
    x[3:6] = [fdm[f'velocities/{c}-fps'] * FT for c in 'uvw']
    x[6:10] = euler_to_quat(fdm['attitude/phi-rad'], fdm['attitude/theta-rad'], fdm['attitude/psi-rad'])
    x[10:13] = [fdm[f'velocities/{c}-rad_sec'] for c in 'pqr']
    for e in spinning(core):
        x[core.X[f'omega_rps[{e}]']] = fdm[f'propulsion/engine[{e}]/propeller-rpm'] * 2 * math.pi / 60
    for name, i in core.X.items():
        if name.startswith('held:'):
            x[i] = fdm[name[5:]]
    x[core.X['aux:udot_mps2']:core.X['aux:udot_mps2'] + 3] = prev_uvwdot
    x[core.X['aux:cl_squared']] = fdm['aero/cl-squared']
    x[core.X['aux:fcs_initialized']] = 1.0
    for k, v in zip(('bi2vel', 'ci2vel', 'qbar_area', 'alpha_wing'), prev_pre or (0.0,) * 4):
        x[core.X[f'aux:{k}']] = v


def spinning(core):
    """The engines with a propeller speed state."""
    return [i for i, k in enumerate(core.layout['engines']) if k == 'propeller']


def first_rpm(fdm, core):
    s = spinning(core)
    return fdm[f'propulsion/engine[{s[0]}]/propeller-rpm'] if s else 0.0


def env_of(fdm, core, rotating=True):
    e = core.env(1, latitude_deg=fdm['position/lat-geod-deg'], gravity=9.80665, origin_alt_msl=fdm['position/h-sl-ft'] * FT,
                 ground_alt_msl=0.0, earth_rate=EARTH_RATE if rotating else 0.0)
    e[0, 0:3] = [fdm[f'atmosphere/total-wind-{c}-fps'] * FT for c in ('north', 'east', 'down')]
    return e


def random_mass(rng, core):
    """Random point masses and declared properties, in JSBSim property units."""
    s = {}
    pms = core.layout['pointmasses']
    d = dict(zip(core.layout['p'], core.layout['p_default']))
    for i in range(len(pms)):   # around the vehicle's own: weight 0 to twice, location +-0.15 m x, +-0.3 m y, +-0.1 m z
        s[f'inertia/pointmass-weight-lbs[{i}]'] = d[f'inertia/pointmass-weight-lbs[{i}]'] * rng.uniform(0.0, 2.0)
        for c, r in (('X', 0.15), ('Y', 0.3), ('Z', 0.1)):
            k = f'inertia/pointmass-location-{c}-inches[{i}]'
            s[k] = d[k] + rng.uniform(-r, r) * IN_PER_M
    for name, d in zip(core.layout['p'], core.layout['p_default']):
        if not (name.startswith('inertia/') or name.startswith('fcs/') or name.startswith('avionics/')):
            s[name] = d * rng.uniform(0.5, 1.5) if d else rng.uniform(-1, 1)
    return s


# -- 1. snapshots -------------------------------------------------------------------------------------------------------

def snapshots(vehicle, core, n, seed):
    rng = np.random.default_rng(seed)
    floors = {'force_N': 0.01, 'moment_Nm': 0.001, 'angle_rad': 1e-6, 'rate_rps': 1e-6, 'qbar_Pa': 0.01, 'rho': 1e-6,
              # omega_dot: JSBSim's value is a difference of two rpm 1 ms apart, resolved to about 1e-10 rad/s2
              'rpm': 0.01, 'omega_dot': 1.0, 'current_A': 0.001, 'fn': 1e-4, 'mass': 1e-6, 'cg_in': 1e-6,
              'inertia': 1e-9, 'ang_acc': 1e-6}
    worst = {}
    used = []
    t0 = time.time()

    sample = {'max_rel': 0.0, 'what': ''}

    def cmp(key, kind, a, b):
        e = float(abs(a - b) / max(abs(b), floors[kind]))
        if e > worst.get(key, (-1.0,))[0]:
            worst[key] = (e, float(a), float(b))
        if e > sample['max_rel']:
            sample.update(max_rel=e, what=key)

    for s in range(n):
        sample.update(max_rel=0.0, what='')
        settings = random_mass(rng, core) if s % 4 else {}   # every fourth one with the vehicle's own values
        rotating = s % 2 == 1
        fdm = jsb(vehicle, 0.001, rotating=rotating, settings=settings)
        V = rng.uniform(8, 32)
        al, be = math.radians(rng.uniform(-25, 35)), math.radians(rng.uniform(-20, 20))
        uvw = (V * math.cos(al) * math.cos(be), V * math.sin(be), V * math.sin(al) * math.cos(be))
        ic(fdm, rng.uniform(150, 1500), uvw, (rng.uniform(-70, 70), rng.uniform(-45, 45), rng.uniform(0, 360)),
           rng.uniform(-1.5, 1.5, 3))
        u = np.zeros(core.nu)
        for name, i in core.U.items():
            if name.startswith('fcs/throttle-cmd-norm'):
                u[i] = rng.uniform(0.2, 1.0)
        set_inputs(fdm, core, u)
        for _ in range(300):        # spin the propellers up
            fdm.run()
        for name, i in core.U.items():
            u[i] = rng.uniform(0, 1) if 'throttle' in name else (rng.uniform(-1, 1) if 'trim' not in name else rng.uniform(-0.2, 0.2))
        # wind for half of the non-rotating ones. On the rotating Earth JSBSim's reported Euler angles and the
        # transformation it applies to the wind differ by about 2e-10 rad, which the core then sees as an input error;
        # the rotating ones test the Earth-rate terms without wind.
        windy = rng.uniform() < 0.5 and not rotating
        if windy:
            for c in ('north', 'east', 'down'):
                fdm[f'atmosphere/wind-{c}-fps'] = rng.uniform(-8, 8) / FT * (0.3 if c == 'down' else 1.0)
        set_inputs(fdm, core, u)
        for _ in range(int(rng.integers(5, 200))):
            fdm.run()
        prev = [fdm[f'accelerations/{c}dot-ft_sec2'] * FT for c in 'uvw']
        prev_pre = [fdm[k] for k in PRE]   # what this frame's pre-functions see (FGAerodynamics::Run)
        rpm_prev = {e: fdm[f'propulsion/engine[{e}]/propeller-rpm'] for e in spinning(core)}
        fdm.run()
        x = core.zeros(1)
        capture(fdm, core, x[0], prev, prev_pre)
        for e, r in rpm_prev.items():   # the frame computed its forces from this speed
            x[0, core.X[f'omega_rps[{e}]']] = r * 2 * math.pi / 60
        p = core.params(1, split(settings)[0])
        e = env_of(fdm, core, rotating)
        xd, y = core.eval(x, p, e, jsbsim_order=True)
        Y = {k: y[0, i] for k, i in core.Y.items()}
        ne = len(core.layout['engines'])
        for c in 'xyz':
            cmp(f'aero_f{c}', 'force_N', Y[f'aero_f{c}_N'], fdm[f'forces/fb{c}-aero-lbs'] * LBF)
            cmp(f'prop_f{c}', 'force_N', sum(Y[f'prop_f{c}_N[{e}]'] for e in range(ne)), fdm[f'forces/fb{c}-prop-lbs'] * LBF)
            cmp(f'ext_f{c}', 'force_N', Y[f'ext_f{c}_N'], fdm[f'forces/fb{c}-external-lbs'] * LBF)
            cmp(f'total_f{c}', 'force_N', Y[f'f{c}_N'], fdm[f'forces/fb{c}-total-lbs'] * LBF)
            cmp(f'cg_{c}', 'cg_in', Y[f'cg_{c}_in'], fdm[f'inertia/cg-{c}-in'])
        for c, m in zip('xyz', 'lmn'):
            cmp(f'aero_m{c}', 'moment_Nm', Y[f'aero_m{c}_Nm'], fdm[f'moments/{m}-aero-lbsft'] * FTLBF)
            cmp(f'prop_m{c}', 'moment_Nm', sum(Y[f'prop_m{c}_Nm[{e}]'] for e in range(ne)),
                fdm[f'moments/{m}-prop-lbsft'] * FTLBF)
            cmp(f'ext_m{c}', 'moment_Nm', Y[f'ext_m{c}_Nm'], fdm[f'moments/{m}-external-lbsft'] * FTLBF)
            cmp(f'total_m{c}', 'moment_Nm', Y[f'm{c}_Nm'], fdm[f'moments/{m}-total-lbsft'] * FTLBF)
        for i, c in enumerate('pqr'):
            cmp(f'{c}dot', 'ang_acc', xd[0, 10 + i], fdm[f'accelerations/{c}dot-rad_sec2'])
            cmp(f'gyro_{c}', 'rate_rps', Y[f'gyro_{"xyz"[i]}_rps'], fdm[f'velocities/{c}i-rad_sec'])
        for k in ('ixx', 'iyy', 'izz', 'ixy', 'ixz', 'iyz'):
            # the core gives the products as integrals (ixz = sum x z dm); JSBSim's inertia/ixz property alone keeps the
            # XML's negated sign (FGMassBalance::GetIxz returns mJ(1,3), GetIxy and GetIyz return -mJ)
            sign = -1.0 if k == 'ixz' else 1.0
            cmp(k, 'inertia', Y[f'{k}_kgm2'], sign * fdm[f'inertia/{k}-slugs_ft2'] * SLUGFT2)
        cmp('mass', 'mass', Y['mass_kg'], fdm['inertia/mass-slugs'] * SLUG)
        cmp('alpha', 'angle_rad', Y['alpha_rad'], fdm['aero/alpha-rad'])
        cmp('beta', 'angle_rad', Y['beta_rad'], fdm['aero/beta-rad'])
        cmp('alphadot', 'rate_rps', Y['alphadot_rps'], fdm['aero/alphadot-rad_sec'])
        cmp('qbar', 'qbar_Pa', Y['qbar_Pa'], fdm['aero/qbar-psf'] * PSF)
        cmp('rho', 'rho', Y['rho_kgm3'], fdm['atmosphere/rho-slugs_ft3'] * SLUGFT3)
        for e in range(ne):
            cmp(f'thrust[{e}]', 'force_N', Y[f'thrust_N[{e}]'], fdm[f'propulsion/engine[{e}]/thrust-lbs'] * LBF)
        for e, r in rpm_prev.items():
            cmp(f'current[{e}]', 'current_A', Y[f'current_A[{e}]'], fdm[f'propulsion/engine[{e}]/current-amperes'])
            cmp(f'rpm[{e}]', 'rpm', Y[f'rpm[{e}]'], r)
            omega_dot = (fdm[f'propulsion/engine[{e}]/propeller-rpm'] - r) / 0.001 * 2 * math.pi / 60
            cmp(f'omega_dot[{e}]', 'omega_dot', xd[0, core.X[f'omega_rps[{e}]']], omega_dot)
        for name in core.layout['y']:
            if name.startswith('fn:'):
                cmp(name, 'fn', Y[name], fdm[name[3:]])
        used.append({'V': round(V, 2), 'alpha_deg': round(math.degrees(al), 1), 'beta_deg': round(math.degrees(be), 1),
                     'rpm': round(next(iter(rpm_prev.values()), 0.0)), 'mass_kg': round(Y['mass_kg'], 3), 'cg_x_m': round(Y['cg_x_in'] / IN_PER_M, 4),
                     'index': s, 'rotating': rotating, 'wind': windy, 'max_rel': sample['max_rel'], 'worst': sample['what'],
                     'airspeed_now_mps': round(Y['airspeed_mps'], 3), 'alpha_now_deg': round(math.degrees(Y['alpha_rad']), 2),
                     'h_agl_m': round(fdm['position/h-agl-ft'] * FT, 1), 'lat_deg': round(fdm['position/lat-geod-deg'], 5)})
    worst_all = max(v[0] for v in worst.values())
    return {'n': n, 'seed': seed, 'seconds': round(time.time() - t0, 1), 'limit': SNAPSHOT_LIMIT,
            'max_relative_error': float(worst_all), 'pass': bool(worst_all <= SNAPSHOT_LIMIT),
            'worst': {k: {'rel': v[0], 'core': v[1], 'jsbsim': v[2]} for k, v in sorted(worst.items(), key=lambda kv: -kv[1][0])[:12]},
            'ranges': {k: [min(s_[k] for s_ in used), max(s_[k] for s_ in used)]
                       for k in ('V', 'alpha_deg', 'beta_deg', 'rpm', 'mass_kg', 'cg_x_m')},
            'worst_samples': sorted(used, key=lambda s_: -s_['max_rel'])[:5]}


# -- 2. flight-control sequences ----------------------------------------------------------------------------------------

def sequences(vehicle, core, n, seed, seconds=3.0):
    rng = np.random.default_rng(seed + 100)
    servo_props = core.layout['servo_inputs']
    faults = [p for p in core.layout['p'] if '/malfunction/' in p]
    surfaces = [p for p in core.X if p.startswith('held:') and 'throttle' not in p]
    worst, cases = 0.0, []
    t0 = time.time()
    for s in range(n):
        chain = (0.0, 0.0, 0.0) if s % 2 == 0 else (0.020, 0.008, 0.040) if s % 4 == 1 else (0.010, 0.0, 0.012)
        settings = {'avionics/servo/pwm-period-s': chain[0], 'avionics/servo/pwm-phase-s': chain[1],
                    'avionics/servo/delay-s': chain[2]}
        fdm = jsb(vehicle, 0.001, rotating=False)
        u = np.zeros((1, core.nu))
        for name, i in core.U.items():
            if name.startswith('fcs/throttle-cmd-norm'):
                u[0, i] = 0.6
        set_inputs(fdm, core, u[0])
        ic(fdm, 800.0, (17.0, 0, 0.3), (0, 1.0, 0), (0, 0, 0))
        x = core.zeros(1)
        capture(fdm, core, x[0], [0.0, 0.0, 0.0])
        p = core.params(1, settings)
        e = env_of(fdm, core, rotating=False)
        core.reset(x, u, p)
        ref = ServoChainRef(len(servo_props), *chain, 0.001, [u[0, core.U[q]] for q in servo_props])
        frames = int(seconds / 0.001)
        changes = sorted(set(int(v) for v in rng.integers(0, frames, 60)))
        toggles = {int(f): faults[int(rng.integers(0, len(faults)))] for f in rng.integers(0, frames, 6)}
        err = 0.0
        for f in range(frames):
            if f in changes:
                for name, i in core.U.items():
                    if 'throttle' not in name and 'trim' not in name:
                        u[0, i] = rng.uniform(-1.2, 1.2)
            if f in toggles:
                k = toggles[f]
                p[0, core.P[k]] = 1.0 - p[0, core.P[k]]
                fdm[k] = p[0, core.P[k]]
            out = ref([u[0, core.U[q]] for q in servo_props])
            for name, i in core.U.items():
                fdm[name] = out[servo_props.index(name)] if name in servo_props else float(u[0, i])
            fdm.run()
            core.step(x, u, p, e, dt=0.001, k=1, outputs=False)
            for h in surfaces:
                err = max(err, abs(x[0, core.X[h]] - fdm[h[5:]]))
        worst = max(worst, err)
        cases.append({'servo_chain_s': chain, 'faults_toggled': sorted(set(toggles.values())), 'max_abs_rad': err})
    return {'n': n, 'seconds_each': seconds, 'limit_rad': SEQUENCE_LIMIT_RAD, 'max_abs_rad': worst,
            'pass': bool(worst <= SEQUENCE_LIMIT_RAD), 'cases': cases, 'wall_s': round(time.time() - t0, 1)}


# -- 3. flights ---------------------------------------------------------------------------------------------------------

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


def trim(vehicle, core, settings, speed, height=100.0):
    """Steady level flight from tools/linear.py (Newton on the equilibrium, the engines at their steady speed), then the
    airframe held there while the actuators and engines settle on the trim commands, in JSBSim as simhost runs it
    (1 ms, Adams-Bashforth 2, rotating WGS84 Earth, the vehicle's start position). Also returns the sign of the
    elevator command that pitches the nose up (for a pull that is a pull on any vehicle)."""
    m = linear.Model(vehicle, settings=settings)
    t = linear.trim(m, 'level', speed, height)
    if not t['converged']:
        raise SystemExit(f'no level trim at {speed} m/s, {height} m (residual {t["residual_max"]:.2e})')
    y0 = np.array([t['state'][s] for s in linear.STATES])
    u0 = np.array([t['commands'][n] for n in m.inputs])
    d = np.zeros(len(u0))
    d[m.inputs.index('elevator')] = 0.01
    nose_up = 1.0 if m.f(y0, u0 + d)[4] > m.f(y0, u0 - d)[4] else -1.0
    m.hold(y0, u0, trim=False, seconds=3.0, settle=False)
    trim_u = {n_: 0.0 for n_ in core.U}
    for i, (_, prop) in enumerate(m.props):
        key = prop if prop in core.U else f'{prop}[0]'
        if key not in core.U:
            raise SystemExit(f'vehicle.toml property {prop} is not an input of the core')
        trim_u[key] = float(u0[i])
    return m.fdm, trim_u, nose_up


def actuator_fault(core, command, kinds):
    """The first actuator the command drives that has one of these failures (in the order given)."""
    for act, deps in core.layout['actuators'].items():
        if command in deps:
            for k in kinds:
                if f'{act}/malfunction/{k}' in core.P:
                    return f'{act}/malfunction/{k}', k
    raise SystemExit(f'no actuator driven by {command} has a failure of {kinds}')


def cases(rng, core, nose_up):
    def doublet(name, amp, t0=1.0, width=1.0):
        return lambda t: {name: amp if t0 <= t < t0 + width else (-amp if t0 + width <= t < t0 + 2 * width else 0.0)}
    ph = rng.uniform(0, 2 * math.pi, (4, 3))
    fr = np.array([0.2, 0.55, 1.3])

    def multisine(t):
        s = [float(sum(0.05 * math.sin(2 * math.pi * f * t + p) for f, p in zip(fr, ph[i]))) for i in range(4)]
        return {'fcs/elevator-cmd-norm': s[0], 'fcs/aileron-cmd-norm': s[1], 'fcs/rudder-cmd-norm': s[2],
                'fcs/throttle-cmd-norm[0]': 2 * s[3]}
    none = lambda t: {}  # noqa: E731
    base = {
        'hold': (none, None, {}),
        'elevator_doublet': (doublet('fcs/elevator-cmd-norm', 0.15), None, {}),
        'aileron_doublet': (doublet('fcs/aileron-cmd-norm', 0.2), None, {}),
        'rudder_doublet': (doublet('fcs/rudder-cmd-norm', 0.3), None, {}),
        'throttle_steps': (lambda t: {'fcs/throttle-cmd-norm[0]': 0.3 if 1 <= t < 5 else (-0.4 if 5 <= t < 9 else 0.0)}, None, {}),
        'multisine': (multisine, None, {}),
        'crosswind_aileron': (doublet('fcs/aileron-cmd-norm', 0.2), (0.0, 5.0, 0.0), {}),
        'pull_to_stall': (lambda t: {'fcs/elevator-cmd-norm': 0.8 * nose_up if 1 <= t < 4 else 0.0,
                                     'fcs/throttle-cmd-norm[0]': -0.6 if 1 <= t < 4 else 0.0}, None, {}),
    }
    # failures switched on during the flight, flown at 1500 m so no case reaches the ground in 20 s; the actuator is the
    # first one the command drives (core layout "actuators"), the aileron one hardover where it can be
    stuck, _ = actuator_fault(core, 'fcs/elevator-cmd-norm', ['fail_stuck'])
    zero, _ = actuator_fault(core, 'fcs/rudder-cmd-norm', ['fail_zero'])
    ail, kind = actuator_fault(core, 'fcs/aileron-cmd-norm', ['fail_hardover', 'fail_stuck'])
    faults = {
        'elevator_stuck_in_doublet': (doublet('fcs/elevator-cmd-norm', 0.15), None, {1.5: {stuck: 1}}),
        'rudder_fail_zero': (doublet('fcs/rudder-cmd-norm', 0.3), None, {1.5: {zero: 1}}),
        f'aileron_{kind[5:]}': ((none if kind == 'fail_hardover' else doublet('fcs/aileron-cmd-norm', 0.2)), None,
                                {2.0 if kind == 'fail_hardover' else 1.5: {ail: 1}}),
    }
    return base, faults


def fly_case(vehicle, core, settings, fn, wind, events, gravity, T, speed, height=100.0, dts=(0.001, 0.004)):
    fdm, trim_u, _ = trim(vehicle, core, settings, speed, height=height)
    if wind is not None:
        for c, w in zip(('north', 'east', 'down'), wind):
            fdm[f'atmosphere/wind-{c}-fps'] = w / FT
    ned = ned_of(fdm['position/lat-geod-deg'], fdm['position/long-gc-deg'], fdm['position/h-sl-ft'] * FT)
    x0 = core.zeros(1)
    capture(fdm, core, x0[0], [fdm[f'accelerations/{c}dot-ft_sec2'] * FT for c in 'uvw'])
    e = env_of(fdm, core)
    e[0, 3] = gravity
    if wind is not None:        # JSBSim's total-wind properties update only in its next frame
        e[0, 0:3] = wind
    uarr0 = np.array([[trim_u[n_] for n_ in core.layout['u']]])
    servo = core.layout['servo_inputs']
    clamp = lambda n_, v: min(1.0, max(0.0 if 'throttle' in n_ else -1.0, v))  # noqa: E731
    res = {}
    for dt in dts:
        x = x0.copy()
        p = core.params(1, settings)
        core.reset(x, uarr0, p)    # actuator filters and servo chain at rest on the trim commands, as JSBSim's after the hold
        x[0, core.X['aux:udot_mps2']:core.X['aux:udot_mps2'] + 3] = x0[0, core.X['aux:udot_mps2']:core.X['aux:udot_mps2'] + 3]
        u = uarr0.copy()
        traj = []
        for i in range(int(round(T / dt))):
            t = i * dt
            for te, ev in events.items():
                if abs(t - te) < dt / 2:
                    for k, v in ev.items():
                        p[0, core.P[k]] = v
            d = fn(t)
            for n_ in core.U:
                u[0, core.U[n_]] = clamp(n_, trim_u[n_] + d.get(n_, 0.0))
            y = core.step(x, u, p, e, dt=dt, k=1)
            tt = (i + 1) * dt
            if abs(tt / 0.1 - round(tt / 0.1)) < 1e-6:
                traj.append((round(tt, 3), x[0, 0:3].copy(), x[0, 6:10].copy(), y[0, core.Y['airspeed_mps']], x[0, 10:13].copy(),
                             y[0, core.Y[f'rpm[{spinning(core)[0]}]']] if spinning(core) else 0.0))
        res[dt] = traj
    ref = ServoChainRef(len(servo), *split(settings)[1], 0.001, [trim_u[q] for q in servo])
    traj_j = []
    for i in range(int(round(T / 0.001))):
        t = i * 0.001
        for te, ev in events.items():
            if abs(t - te) < 0.0005:
                for k, v in ev.items():
                    fdm[k] = v
        d = fn(t)
        cmd = {n_: clamp(n_, trim_u[n_] + d.get(n_, 0.0)) for n_ in core.U}
        out = ref([cmd[q] for q in servo])
        for n_, v in cmd.items():
            fdm[n_] = out[servo.index(n_)] if n_ in servo else v
        fdm.run()
        tt = (i + 1) * 0.001
        if abs(tt / 0.1 - round(tt / 0.1)) < 1e-6:
            q = euler_to_quat(fdm['attitude/phi-rad'], fdm['attitude/theta-rad'], fdm['attitude/psi-rad'])
            traj_j.append((round(tt, 3), ned(fdm['position/lat-geod-deg'], fdm['position/long-gc-deg'], fdm['position/h-sl-ft'] * FT),
                           q, fdm['velocities/vt-fps'] * FT, np.array([fdm[f'velocities/{c}-rad_sec'] for c in 'pqr']),
                           first_rpm(fdm, core)))
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
    case['trim'] = {k: round(v, 4) for k, v in trim_u.items() if v != 0.0}
    case['speed_mps'] = speed
    case['start_agl_m'] = height
    case['jsbsim_min_agl_m'] = round(height - max(float(r[1][2]) for r in traj_j), 1)
    case['jsbsim_end'] = {'pos_from_start_m': [round(float(c), 1) for c in end[1]], 'airspeed_mps': round(end[3], 2),
                          'euler_deg': [round(math.degrees(float(a)), 1) for a in quat_to_euler(end[2])]}
    return case


def flights(vehicle, core, seed, configs, speed, T=20.0):
    rng = np.random.default_rng(seed)
    g0 = jsb(vehicle, 0.001)   # gravity the core should use: JSBSim's own here, from an instance at rest in the air
    ic(g0, 100.0, (0, 0, 0), (0, 0, 0), (0, 0, 0))
    gravity = g0['accelerations/wdot-ft_sec2'] * FT
    out = {'gravity_mps2': gravity, 'configs': {str(c): load_config(c) for c in configs}, 'cases': {}}
    nose_up = trim(vehicle, core, {}, speed)[2]
    base, faults = cases(rng, core, nose_up)
    runs = [(name, {}, c) for name, c in base.items()]
    if configs:
        both = load_config(*configs)
        label = '+'.join(Path(c).stem for c in configs)
        runs += [(f'{label}:{name}', both, base[name]) for name in ('hold', 'elevator_doublet', 'aileron_doublet', 'multisine')]
    runs += [(name, {}, c) for name, c in faults.items()]
    for name, settings, (fn, wind, events) in runs:
        height = 1500.0 if name in faults else 100.0
        out['cases'][name] = fly_case(vehicle, core, settings, fn, wind, events, gravity, T, speed, height)
        print(json.dumps({name: out['cases'][name]['dt_0.004']['10s']}), flush=True)
    lim = FLIGHT_LIMITS
    h = f'{lim["horizon_s"]:g}s'
    out['limits'] = lim
    out['pass'] = True
    for group in ('flight', 'failure'):
        names = [n_ for n_ in out['cases'] if (n_ in faults) == (group == 'failure')]
        worst = {k: max(out['cases'][n_]['dt_0.004'][h][k] for n_ in names) for k in lim[group]}
        out[f'worst_{group}_dt_0.004_{h}'] = worst
        out['pass'] = bool(out['pass'] and all(worst[k] <= lim[group][k] for k in worst))
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('vehicle')
    p.add_argument('--out', help='default build/fastcore/<vehicle>')
    p.add_argument('--snapshots', type=int, default=300)
    p.add_argument('--sequences', type=int, default=8)
    p.add_argument('--seed', type=int, default=1)
    p.add_argument('--config', action='append', default=None,
                   help='configuration file(s) flown together in the flights (default: every file in <vehicle>/configs)')
    p.add_argument('--skip-flights', action='store_true')
    p.add_argument('--speed', type=float, default=17.0, help='airspeed of the trimmed flights (m/s)')
    a = p.parse_args()
    name = Path(a.vehicle).resolve().name
    out = Path(a.out) if a.out else Path('build/fastcore') / name
    gen.generate(a.vehicle, out)
    gen.build(out, name)
    core = Core(out, name)
    import jsbsim
    configs = a.config if a.config is not None else sorted(str(c) for c in (Path(a.vehicle) / 'configs').glob('*.toml'))
    rep = {'vehicle': name, 'jsbsim': jsbsim.__version__, 'core': core.layout['sources_sha256'],
           'generator_sha256': core.layout['generator_sha256']}
    rep['snapshots'] = snapshots(a.vehicle, core, a.snapshots, a.seed)
    print(json.dumps({'snapshots': {k: rep['snapshots'][k] for k in ('n', 'max_relative_error', 'pass')}}), flush=True)
    rep['sequences'] = sequences(a.vehicle, core, a.sequences, a.seed)
    print(json.dumps({'sequences': {k: rep['sequences'][k] for k in ('n', 'max_abs_rad', 'pass')}}), flush=True)
    if not a.skip_flights:
        rep['flights'] = flights(a.vehicle, core, a.seed, configs, a.speed)
        print(json.dumps({'flights_worst': rep['flights']['worst_flight_dt_0.004_10s'],
                          'failures_worst': rep['flights']['worst_failure_dt_0.004_10s'], 'pass': rep['flights']['pass']}), flush=True)
    rep['pass'] = rep['snapshots']['pass'] and rep['sequences']['pass'] and rep.get('flights', {'pass': True})['pass']
    (out / 'check.json').write_text(json.dumps(rep, indent=1) + '\n')
    print(json.dumps({'check': str(out / 'check.json'), 'pass': rep['pass']}))
    sys.exit(0 if rep['pass'] else 1)


if __name__ == '__main__':
    main()
