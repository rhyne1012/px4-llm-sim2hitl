#!/usr/bin/env python3
"""Trims, linear models and transfer functions of a fixed-wing JSBSim vehicle folder, checked against the nonlinear model.

    python3 tools/linear.py <vehicle folder> [--config <config.toml> ...] --out <answers.json>
        [--level 14 17 20] [--turn 17:30 17:-30] [--sideslip 17:5] [--linear 14 17 20] [--height 100] [--no-check]
    python3 tools/linear.py --compare <reference.json> <new.json> [--out <comparison.json>]

The model is the vehicle as simhost flies it: the same JSBSim file, 1 ms steps, Adams-Bashforth 2, the configuration's
JSBSim property settings, the start position of vehicle.toml (simhost's default otherwise), no wind.

Trim (--level, --turn SPEED:BANK, --sideslip SPEED:BETA; m/s, degrees). Damped Newton on the equilibrium: angle of
attack, sideslip (or bank for a sideslip trim), pitch and the four commands solve the six body accelerations and the
climb rate = 0 at the given airspeed, height and bank (a turn has the turn rate g tan(bank) / V). Each evaluation holds the
airframe at the candidate state and lets the engines reach their steady speed for the candidate commands (JSBSim's
FGTrim cannot do that for fast electric motors, docs/architecture.md); the actuators pass their input through, as in
FGTrim. JSBSim's FGTrim is tried next to every level trim and reported as a check, never used.

Linear model (--linear SPEEDS, wings level). Central differences of the same evaluation around the trim:
  airframe: 8 states u v w (m/s, body) p q r (rad/s) phi theta (rad); inputs: the JSBSim command properties of
    vehicle.toml (throttle, aileron, elevator, rudder, and any other property it maps outputs to), at the surfaces
    (actuators passed through) and with the thrust at the engines' steady speed (quasi-steady).
  modes: of the longitudinal (u w q theta) and lateral (v p r phi) blocks.
  servo: per input, the first-order pole of its actuator or engine, measured from a small step of the command with the
    airframe held at the trim (the step response of the largest acceleration it changes, normalised), and the
    servo chain's transport delay for inputs driven by servo outputs (vehicle.toml kind = "servo"): delay + half the PWM
    period (avionics/servo/*, the configuration). The delay is not in the polynomials: transfer functions carry it as
    delay_s.
  transfer functions: q theta u airspeed alpha per elevator and throttle (longitudinal block), p r phi beta per aileron
    and rudder (lateral block); airframe, and with the servo pole (with_servo, plus delay_s).
Small-signal models of one trim: no saturation, rate limit or PWM quantisation.

Check (default; --no-check skips it): the nonlinear model from the trim, actuators and engines at rest, a sine on one
command (2, 5, 10, 20 rad/s), against with_servo without delay_s (the servo chain is simhost's, not JSBSim's):
q/elevator, p/aileron, r/rudder, airspeed/throttle. A check outside 1 dB or 10 degrees is reported, not hidden. An
open-loop unstable trim (an eigenvalue with real part above 0.05 1/s) is not checked: the model diverges from it. Also
reported: the split blocks against the coupled 8-state model, per pair (a large value means coupled motions).

Compare (--compare): every trim, mode, servo pole and checked frequency response of two answer files, with the limits
in COMPARE_LIMITS. Exit 1 when an item is outside.

Commands are JSBSim's normalised command properties in the vehicle's own sign convention; vehicle.toml says which PX4
output drives which property with which gain (listed in the output as "outputs"). Needs the JSBSim Python module (1.3.3;
JSBSIM_PYTHON as tools/vehicle_check.py) and numpy.
"""
import argparse
import hashlib
import json
import math
import sys
import tomllib
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'fastcore'))
import vehicle_check as VC  # noqa: E402  (loads the JSBSim Python module)
from fastcore import load_config  # noqa: E402

jsbsim = VC.jsbsim
FT = 0.3048
DT = 0.001
AB2 = 3
START = (22.9100, 120.3110)  # simhost's default start (simhost/src/main.cpp)
STATES = ('u', 'v', 'w', 'p', 'q', 'r', 'phi', 'theta')
LON, LAT = [0, 2, 4, 7], [1, 3, 5, 6]  # u w q theta; v p r phi
STANDARD = {'throttle': 'fcs/throttle-cmd-norm', 'aileron': 'fcs/aileron-cmd-norm', 'elevator': 'fcs/elevator-cmd-norm',
            'rudder': 'fcs/rudder-cmd-norm'}
LIMITS = {'throttle': (0.0, 1.0), 'aileron': (-1.0, 1.0), 'elevator': (-1.0, 1.0), 'rudder': (-1.0, 1.0)}
CHECK_RAD_S = (2.0, 5.0, 10.0, 20.0)
CHECK_PAIRS = (('q', 'elevator'), ('p', 'aileron'), ('r', 'rudder'), ('airspeed', 'throttle'))
CHECK_DB, CHECK_DEG = 1.0, 10.0
UNSTABLE_REAL = 0.05  # 1/s: a faster open-loop divergence skips the sine check
AMPLITUDE = {'throttle': 0.02}  # sine and servo-step amplitude per input; others 0.01
# --compare limits: absolute for trims, relative for modes and servo poles, dB and degrees for frequency responses
COMPARE_LIMITS = {'angle_deg': 0.1, 'command': 0.005, 'throttle': 0.01, 'mode_relative': 0.05, 'slow_mode_relative': 0.2,
                  'servo_relative': 0.05, 'delay_s': 0.001, 'gain_db': 1.0, 'phase_deg': 10.0}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def name_of(prop):
    """'fcs/elevator-cmd-norm' -> 'elevator'; other properties keep their own name."""
    base = prop.split('[')[0]
    for name, std in STANDARD.items():
        if base == std:
            return name
    return prop


class Model:
    """The vehicle in JSBSim, with the airframe held at a state while everything else runs."""

    def __init__(self, folder, configs=()):
        self.folder = Path(folder).resolve()
        self.toml = tomllib.loads((self.folder / 'vehicle.toml').read_text())
        self.settings = load_config(*configs)
        self.fdm = f = VC.load(self.folder, DT)
        for k in ('rate/rotational', 'rate/translational', 'position/rotational', 'position/translational'):
            f[f'simulation/integrator/{k}'] = AB2
        for k, v in self.settings.items():
            if not k.startswith('avionics/'):
                f[k] = v
        start = self.toml.get('start', {})
        self.lat0 = math.radians(start.get('lat_deg', START[0]))
        self.lon0 = math.radians(start.get('lon_deg', START[1]))
        self.psi0 = math.radians(start.get('heading_deg', 0.0))
        # inputs: every command property vehicle.toml drives, in first-use order
        self.props, self.outputs = [], {}
        for m in self.toml['actuators']:
            name = name_of(m['property'])
            if name not in self.outputs:
                self.props.append((name, m['property']))
                self.outputs[name] = []
            self.outputs[name].append({'channel': m['channel'], 'gain': m['gain'], 'offset': m.get('offset', 0.0),
                                       'kind': m.get('kind', '')})
        self.inputs = [n for n, _ in self.props]
        missing = [n for n in STANDARD if n not in self.inputs]
        if missing:
            raise SystemExit(f'{self.folder}: vehicle.toml drives no {", ".join(missing)} command; linear.py needs all four')
        self.prop = dict(self.props)
        self.thrust = [f'propulsion/engine[{i}]/thrust-lbs' for i in range(f.get_propulsion().get_num_engines())]
        self.height = None
        f['ic/terrain-elevation-ft'] = 0.0
        f['ic/lat-geod-rad'], f['ic/long-gc-rad'] = self.lat0, self.lon0
        f['ic/h-agl-ft'] = 100.0 / FT
        f['ic/u-fps'] = 15.0 / FT
        if not f.run_ic():
            raise SystemExit('JSBSim RunIC failed')
        f['propulsion/set-running'] = -1

    def gravity(self):
        return self.fdm['accelerations/gravity-ft_sec2'] * FT

    def put(self, y, u):
        """The airframe at state y (STATES, SI) at self.height, commands u; JSBSim's derivatives at it (dt = 0)."""
        f = self.fdm
        for k, v in (('ic/lat-geod-rad', self.lat0), ('ic/long-gc-rad', self.lon0), ('ic/h-agl-ft', self.height / FT),
                     ('ic/u-fps', y[0] / FT), ('ic/v-fps', y[1] / FT), ('ic/w-fps', y[2] / FT), ('ic/phi-rad', y[6]),
                     ('ic/theta-rad', y[7]), ('ic/psi-true-rad', self.psi0), ('ic/p-rad_sec', y[3]),
                     ('ic/q-rad_sec', y[4]), ('ic/r-rad_sec', y[5])):
            f[k] = v
        for i, (name, prop) in enumerate(self.props):
            f[prop] = u[i]
        if not f.run_ic():
            raise RuntimeError('JSBSim RunIC failed')

    def derivatives(self, y):
        f = self.fdm
        p, q, r, phi, th = y[3], y[4], y[5], y[6], y[7]
        return np.array([f['accelerations/udot-ft_sec2'] * FT, f['accelerations/vdot-ft_sec2'] * FT,
                         f['accelerations/wdot-ft_sec2'] * FT, f['accelerations/pdot-rad_sec2'],
                         f['accelerations/qdot-rad_sec2'], f['accelerations/rdot-rad_sec2'],
                         p + math.tan(th) * (q * math.sin(phi) + r * math.cos(phi)), q * math.cos(phi) - r * math.sin(phi)])

    def hold(self, y, u, trim, seconds=5.0, settle=True):
        """Hold the airframe at y while actuators and engines run (trim: actuators pass through); with settle, stop
        once the engines' thrust is steady. Returns the derivatives at y."""
        f = self.fdm
        f.set_trim_status(bool(trim))
        last = []
        for k in range(int(round(seconds / DT))):
            self.put(y, u)
            thrust = sum(f[t] for t in self.thrust)
            last.append(thrust)
            if settle and k >= 20 and abs(thrust - last[-21]) <= 1e-10 * max(1.0, abs(thrust)):
                break
            f.run()
        self.put(y, u)
        return self.derivatives(y)

    def f(self, y, u):
        return self.hold(y, u, trim=True)


def body_state(airspeed, alpha, beta, phi, theta, turn_rate):
    p = -turn_rate * math.sin(theta)
    q = turn_rate * math.sin(phi) * math.cos(theta)
    r = turn_rate * math.cos(phi) * math.cos(theta)
    return np.array([airspeed * math.cos(alpha) * math.cos(beta), airspeed * math.sin(beta),
                     airspeed * math.sin(alpha) * math.cos(beta), p, q, r, phi, theta])


def climb(y):
    u, v, w, phi, th = y[0], y[1], y[2], y[6], y[7]
    return u * math.sin(th) - v * math.sin(phi) * math.cos(th) - w * math.cos(phi) * math.cos(th)


def trim(model, kind, airspeed, height, value=0.0, iterations=60):
    """kind level (value unused), turn (value = bank, deg) or sideslip (value = sideslip, deg). Unknowns z: alpha,
    beta (sideslip trim: bank), theta, then the four standard commands."""
    model.height = height
    g = model.gravity()
    names = list(STANDARD)
    idx = [model.inputs.index(n) for n in names]

    def unpack(z):
        alpha, x, theta = z[0], z[1], z[2]
        if kind == 'sideslip':
            beta, phi, rate = math.radians(value), x, 0.0
        else:
            beta, phi = x, math.radians(value) if kind == 'turn' else 0.0
            rate = g * math.tan(phi) / airspeed
        y = body_state(airspeed, alpha, beta, phi, theta, rate)
        u = np.zeros(len(model.inputs))
        u[idx] = z[3:]
        return y, u

    def residual(z):
        y, u = unpack(z)
        d = model.f(y, u)
        return np.r_[d[:6], climb(y)]

    # Starting point: the angle of attack whose lift balances the weight best, then the throttle whose thrust balances
    # the drag best, wings level (a poor start can leave a propeller beyond its tables, where the thrust stops changing)
    z = np.array([0.0, 0.0, 0.0, 0.7, 0.0, 0.0, 0.0])
    scan = []
    for a_deg in range(-4, 13):
        z[0] = z[2] = math.radians(a_deg)
        scan.append((abs(residual(z)[2]), a_deg))
    z[0] = z[2] = math.radians(min(scan)[1])
    scan = []
    for thr in np.arange(0.05, 1.0001, 0.05):
        z[3] = thr
        scan.append((abs(residual(z)[0]), float(thr)))
    z[3] = min(scan)[1]
    steps = np.array([1e-6] * 3 + [1e-6] * 4)
    limit = np.array([math.radians(5.0)] * 3 + [0.2] * 4)
    lo = np.array([-math.pi / 4, -math.pi / 2, -math.pi / 3] + [LIMITS[n][0] for n in names])
    hi = np.array([math.pi / 4, math.pi / 2, math.pi / 3] + [LIMITS[n][1] for n in names])
    r = residual(z)
    converged, it = False, 0
    for it in range(1, iterations + 1):
        if np.max(np.abs(r)) < 1e-7:
            converged = True
            break
        J = np.zeros((7, 7))
        for j in range(7):
            d = np.zeros(7)
            d[j] = steps[j]
            J[:, j] = (residual(z + d) - residual(z - d)) / (2 * steps[j])
        dz = np.linalg.lstsq(J, -r, rcond=None)[0]
        dz *= min(1.0, float(np.min(limit / np.maximum(np.abs(dz), 1e-300))))
        lam = 1.0
        while lam > 1e-3:
            zn = np.clip(z + lam * dz, lo, hi)
            rn = residual(zn)
            if np.linalg.norm(rn) < np.linalg.norm(r):
                break
            lam *= 0.5
        z, r = zn, rn
    y, u = unpack(z)
    model.f(y, u)
    f = model.fdm
    at_limit = [n for n, v, a, b in zip(names, z[3:], lo[3:], hi[3:]) if v <= a + 1e-9 or v >= b - 1e-9]
    out = {'kind': kind, 'airspeed_m_s': airspeed, 'height_m': height, 'requested_deg': value,
           'bank_deg': math.degrees(y[6]), 'beta_deg': f['aero/beta-deg'], 'alpha_deg': f['aero/alpha-deg'],
           'pitch_deg': math.degrees(y[7]), 'commands': {n: float(u[i]) for i, n in enumerate(model.inputs)},
           'state': {s: float(v) for s, v in zip(STATES, y)}, 'residual_max': float(np.max(np.abs(r))),
           'iterations': it, 'converged': bool(converged and not at_limit), 'commands_at_limit': at_limit}
    if kind == 'level':
        out['fgtrim_check'] = fgtrim(model, airspeed, height)
    return out


def fgtrim(model, airspeed, height):
    """JSBSim's own FGTrim (longitudinal) on a fresh instance, as a check of the Newton trim."""
    f = VC.load(model.folder, DT)
    for k, v in model.settings.items():
        if not k.startswith('avionics/'):
            f[k] = v
    for k, v in (('ic/terrain-elevation-ft', 0.0), ('ic/lat-geod-rad', model.lat0), ('ic/long-gc-rad', model.lon0),
                 ('ic/h-agl-ft', height / FT), ('ic/psi-true-rad', model.psi0), ('ic/vt-fps', airspeed / FT),
                 ('ic/gamma-deg', 0.0)):
        f[k] = v
    f.run_ic()
    f['propulsion/set-running'] = -1
    f[model.prop['throttle']] = 0.5
    try:
        f.do_trim(0)
    except Exception as exc:  # noqa: BLE001 - jsbsim.TrimFailureError
        return {'converged': False, 'error': f'{type(exc).__name__}: {exc}'}
    totals = {'elevator': f[model.prop['elevator']] + f['fcs/pitch-trim-cmd-norm'],
              'throttle': f[model.prop['throttle']]}
    return {'converged': True, 'alpha_deg': f['aero/alpha-deg'], 'pitch_deg': f['attitude/theta-deg'], **totals}


def transfer_function(a, b, c):
    """c (sI - a)^-1 b, by Faddeev-LeVerrier (small blocks)."""
    n = a.shape[0]
    den = np.real(np.poly(a))
    r = np.eye(n)
    num = []
    for k in range(n):
        num.append(float(c @ r @ b))
        if k < n - 1:
            r = a @ r + den[k + 1] * np.eye(n)
    num = np.array(num)
    keep = np.flatnonzero(np.abs(num) > 1e-9 * max(np.max(np.abs(num)), 1e-300))
    return (num[keep[0]:] if len(keep) else np.zeros(1)), den


def tf_record(num, den, delay=None):
    rec = {'num': [float(v) for v in num], 'den': [float(v) for v in den],
           'zeros': [[float(z.real), float(z.imag)] for z in np.roots(num)] if len(num) > 1 else [],
           'poles': [[float(p.real), float(p.imag)] for p in np.roots(den)]}
    if delay is not None:
        rec['delay_s'] = delay
    return rec


def tf_value(rec, w, delay=True):
    s = 1j * w
    v = np.polyval(rec['num'], s) / np.polyval(rec['den'], s)
    return v * np.exp(-s * rec.get('delay_s', 0.0)) if delay else v


def classify(eigenvalues, complex_names, real_names, block):
    """Name the modes of one block: complex pairs and real roots, each slowest first. When their count differs from
    the usual one (an unstable vehicle's short period can split into real roots), they are named by the block and their
    place: longitudinal_real_1 is the slowest real root."""
    pairs = sorted((s for s in eigenvalues if s.imag > 1e-6), key=abs)
    reals = sorted((s for s in eigenvalues if abs(s.imag) <= 1e-6), key=abs)
    named = zip(complex_names, pairs) if len(pairs) == len(complex_names) else \
        ((f'{block}_complex_{k + 1}', s) for k, s in enumerate(pairs))
    modes = [{'name': n, 'real': float(s.real), 'imag': float(s.imag), 'frequency_rad_s': float(abs(s)),
              'damping': float(-s.real / abs(s))} for n, s in named]
    named = zip(real_names, reals) if len(reals) == len(real_names) else \
        ((f'{block}_real_{k + 1}', s) for k, s in enumerate(reals))
    modes += [{'name': n, 'real': float(s.real), 'imag': 0.0, 'time_constant_s': float(-1.0 / s.real)}
              for n, s in named if abs(s.real) > 1e-9]
    return modes


def state_now(f):
    return np.array([f['velocities/u-fps'] * FT, f['velocities/v-fps'] * FT, f['velocities/w-fps'] * FT,
                     f['velocities/p-rad_sec'], f['velocities/q-rad_sec'], f['velocities/r-rad_sec'],
                     f['attitude/phi-rad'], f['attitude/theta-rad']])


def free_run(model, y0, u0, du, seconds):
    """The nonlinear model from the trim (actuators and engines at rest on u0), commands u0 + du; per step the state
    before the step and JSBSim's derivatives of that step."""
    f = model.fdm
    model.hold(y0, u0, trim=False, seconds=2.0, settle=False)
    f.set_trim_status(False)
    for (_, prop), v in zip(model.props, u0 + du):
        f[prop] = v
    ys, ds = [], []
    for _ in range(int(round(seconds / DT))):
        y = state_now(f)
        if not f.run():
            raise RuntimeError('JSBSim stopped')
        ys.append(y)
        ds.append(model.derivatives(y)[:6])
    return np.array(ys), np.array(ds)


def servo(model, y0, u0, A, B, name, seconds=1.5):
    """First-order pole of one input's actuator or engine: a small command step on the nonlinear model, minus the
    same run without the step; the airframe's own response (A times the state difference) is taken out, which leaves
    the input's effect B du filtered by the actuator or engine. A first-order step response K (1 - exp(-t / tau)) is
    fitted to the largest acceleration the input changes (K should be 1: B is the quasi-steady gain)."""
    i = model.inputs.index(name)
    du = np.zeros(len(model.inputs))
    du[i] = AMPLITUDE.get(name, 0.01)
    yb, db = free_run(model, y0, u0, 0 * du, seconds)
    ys, ds = free_run(model, y0, u0, du, seconds)
    e = (ds - db) - (A[:6] @ (ys - yb).T).T
    c = int(np.argmax(np.abs(B[:6, i])))
    s = e[:, c] / (B[c, i] * du[i])
    t = (np.arange(len(s)) + 1) * DT
    out = {'measured_on': ['udot', 'vdot', 'wdot', 'pdot', 'qdot', 'rdot'][c]}

    def fit(tau):
        g = 1.0 - np.exp(-t / tau)
        k = float(g @ s / (g @ g))
        return float(np.sum((s - k * g) ** 2)), k
    taus = np.geomspace(2e-4, 2.0, 200)
    j = int(np.argmin([fit(x)[0] for x in taus]))
    lo, hi = taus[max(j - 1, 0)], taus[min(j + 1, len(taus) - 1)]
    for _ in range(60):  # golden section on log tau
        m1, m2 = lo * (hi / lo) ** 0.382, lo * (hi / lo) ** 0.618
        if fit(m1)[0] < fit(m2)[0]:
            hi = m2
        else:
            lo = m1
    tau = math.sqrt(lo * hi)
    k = fit(tau)[1]
    err = float(np.max(np.abs(s - k * (1.0 - np.exp(-t / tau)))))
    if tau <= 1.5 * DT:
        out.update(pole_rad_s=None, gain=k, fit_error=err, note='no measurable lag (the command acts within a step)')
    else:
        out.update(pole_rad_s=1.0 / tau, gain=k, fit_error=err)
    return out


def chain_delay(model, name):
    """simhost's servo chain for an input driven by servo outputs: transport delay + half the PWM period (seconds)."""
    if not any(o['kind'] == 'servo' for o in model.outputs[name]):
        return 0.0, None
    s = model.settings
    period, phase, delay = (s.get(f'avionics/servo/{k}', 0.0) for k in ('pwm-period-s', 'pwm-phase-s', 'delay-s'))
    return delay + period / 2.0, {'pwm_period_s': period, 'pwm_phase_s': phase, 'delay_s': delay}


def linearize(model, t):
    if t['kind'] != 'level' or not t['converged']:
        raise ValueError('linearize needs a converged level trim')
    model.height = t['height_m']
    y0 = np.array([t['state'][s] for s in STATES])
    u0 = np.array([t['commands'][n] for n in model.inputs])
    nu = len(model.inputs)
    A, B = np.zeros((8, 8)), np.zeros((8, nu))
    for j in range(8):
        d = np.zeros(8)
        d[j] = 1e-4
        A[:, j] = (model.f(y0 + d, u0) - model.f(y0 - d, u0)) / 2e-4
    for j in range(nu):
        d = np.zeros(nu)
        d[j] = 1e-4
        B[:, j] = (model.f(y0, u0 + d) - model.f(y0, u0 - d)) / 2e-4
    servos = {}
    for name in STANDARD:
        s = servo(model, y0, u0, A, B, name)
        s['delay_s'], s['servo_chain'] = chain_delay(model, name)
        servos[name] = s

    u_, w_ = y0[0], y0[2]
    V2 = u_ ** 2 + y0[1] ** 2 + w_ ** 2
    V = math.sqrt(V2)

    def row(pairs):
        c = np.zeros(4)
        for k, v in pairs:
            c[k] = v
        return c
    lon_out = {'q': ('rad/s', row([(2, 1.0)])), 'theta': ('rad', row([(3, 1.0)])), 'u': ('m/s', row([(0, 1.0)])),
               'airspeed': ('m/s', row([(0, u_ / V), (1, w_ / V)])), 'alpha': ('rad', row([(0, -w_ / V2), (1, u_ / V2)]))}
    lat_out = {'p': ('rad/s', row([(1, 1.0)])), 'r': ('rad/s', row([(2, 1.0)])), 'phi': ('rad', row([(3, 1.0)])),
               'beta': ('rad', row([(0, 1.0 / V)]))}
    blocks = {'elevator': (LON, lon_out), 'throttle': (LON, lon_out), 'aileron': (LAT, lat_out), 'rudder': (LAT, lat_out)}
    tfs = {}
    for inp, (block, outs) in blocks.items():
        a = A[np.ix_(block, block)]
        b = B[block, model.inputs.index(inp)]
        pole, delay = servos[inp]['pole_rad_s'], servos[inp]['delay_s']
        for out, (unit, c) in outs.items():
            num, den = transfer_function(a, b, c)
            rec = {'unit': f'{unit} per unit command', 'airframe': tf_record(num, den)}
            if pole:
                rec['with_servo'] = tf_record(num * pole, np.polymul(den, [1.0, pole]), delay)
            else:
                rec['with_servo'] = tf_record(num, den, delay)
            tfs[f'{out}/{inp}'] = rec

    # the split blocks against the coupled 8-state model
    out_rows = {'q': 4, 'p': 3, 'r': 5}
    split = {}
    for out, inp in (('q', 'elevator'), ('p', 'aileron'), ('r', 'rudder'), ('q', 'throttle')):
        worst = 0.0
        for w in CHECK_RAD_S:
            full = np.linalg.solve(1j * w * np.eye(8) - A, B[:, model.inputs.index(inp)])[out_rows[out]]
            ours = tf_value(tfs[f'{out}/{inp}']['airframe'], w)
            worst = max(worst, abs(ours - full) / max(abs(full), 1e-12))
        split[f'{out}/{inp}'] = worst
    eig = np.linalg.eigvals(A)
    return {'trim': {k: t[k] for k in ('airspeed_m_s', 'height_m', 'alpha_deg', 'pitch_deg', 'commands')},
            'states': list(STATES), 'inputs': model.inputs, 'A': A.tolist(), 'B': B.tolist(),
            'modes': classify(np.linalg.eigvals(A[np.ix_(LON, LON)]), ('phugoid', 'short_period'), (), 'longitudinal') +
            classify(np.linalg.eigvals(A[np.ix_(LAT, LAT)]), ('dutch_roll',), ('spiral', 'roll'), 'lateral'),
            'servo': servos, 'transfer_functions': tfs,
            'eigenvalues_coupled': [[float(e.real), float(e.imag)] for e in sorted(eig, key=abs)],
            'blocks_vs_coupled': {'rad_s': list(CHECK_RAD_S), 'max_relative_difference': split,
                                  'note': 'the split blocks against the coupled 8-state model; a large value means the '
                                          'longitudinal and lateral motions are coupled at this trim'}}


def sine_check(model, t, lin):
    """The nonlinear model from the trim against with_servo (without the servo chain delay)."""
    model.height = t['height_m']
    y0 = np.array([t['state'][s] for s in STATES])
    u0 = np.array([t['commands'][n] for n in model.inputs])
    f = model.fdm
    read = {'q': lambda: f['velocities/q-rad_sec'], 'p': lambda: f['velocities/p-rad_sec'],
            'r': lambda: f['velocities/r-rad_sec'], 'airspeed': lambda: f['velocities/vt-fps'] * FT}
    rows = []
    for out, inp in CHECK_PAIRS:
        i = model.inputs.index(inp)
        amp = AMPLITUDE.get(inp, 0.01)
        rec = lin['transfer_functions'][f'{out}/{inp}']['with_servo']
        for w in CHECK_RAD_S:
            period = 2 * math.pi / w
            model.hold(y0, u0, trim=False, seconds=2.0, settle=False)
            f.set_trim_status(False)
            n = int(round((1.5 + 4 * period) / DT))
            ts, ys = np.arange(1, n + 1) * DT, np.zeros(n)
            u = u0.copy()
            for k in range(n):
                u[i] = u0[i] + amp * math.sin(w * k * DT)
                f[model.prop[inp]] = u[i]
                if not f.run():
                    raise RuntimeError('JSBSim stopped in the sine check')
                ys[k] = read[out]()
            sel = ts >= ts[-1] - 3 * period
            X = np.c_[np.sin(w * (ts[sel] - DT)), np.cos(w * (ts[sel] - DT)), np.ones(sel.sum()), ts[sel]]
            a, b, _, _ = np.linalg.lstsq(X, ys[sel], rcond=None)[0]
            meas = complex(a, b) / amp
            model_v = tf_value(rec, w, delay=False)
            db = 20 * math.log10(abs(meas) / abs(model_v))
            deg = math.degrees(math.remainder(np.angle(meas) - np.angle(model_v), 2 * math.pi))
            rows.append({'pair': f'{out}/{inp}', 'rad_s': w, 'measured_gain': abs(meas),
                         'measured_phase_deg': math.degrees(np.angle(meas)), 'model_gain': abs(model_v),
                         'model_phase_deg': math.degrees(np.angle(model_v)), 'error_db': db, 'error_deg': deg})
    worst_db = max(abs(r['error_db']) for r in rows)
    worst_deg = max(abs(r['error_deg']) for r in rows)
    return {'amplitude': {n: AMPLITUDE.get(n, 0.01) for n in STANDARD}, 'rows': rows, 'worst_db': worst_db,
            'worst_deg': worst_deg, 'passed': bool(worst_db <= CHECK_DB and worst_deg <= CHECK_DEG),
            'limits': {'db': CHECK_DB, 'deg': CHECK_DEG}}


def answers(folder, configs, level, turns, sideslips, linear, height, check):
    model = Model(folder, configs)
    xml = model.folder / f"{model.toml['vehicle'].get('jsbsim_model', model.folder.name)}.xml"
    out = {'schema_version': 1, 'tool': 'tools/linear.py', 'jsbsim': jsbsim.__version__,
           'vehicle': {'folder': model.folder.name, 'xml_sha256': sha256(xml),
                       'vehicle_toml_sha256': sha256(model.folder / 'vehicle.toml')},
           'configs': [{'file': Path(c).name, 'sha256': sha256(c)} for c in configs], 'settings': model.settings,
           'model': {'dt_s': DT, 'integrators': 'Adams-Bashforth 2', 'start_lat_lon_deg':
                     [math.degrees(model.lat0), math.degrees(model.lon0)], 'heading_deg': math.degrees(model.psi0)},
           'inputs': model.inputs, 'outputs': model.outputs, 'trims': [], 'linear': []}
    cases = [('level', v, 0.0) for v in sorted(set(level) | set(linear))]
    cases += [('turn', v, b) for v, b in turns] + [('sideslip', v, b) for v, b in sideslips]
    for kind, v, x in cases:
        t = trim(model, kind, v, height, x)
        out['trims'].append(t)
        print(f'trim {kind} {v} m/s {x:+g}: alpha {t["alpha_deg"]:.3f} deg, converged {t["converged"]}', file=sys.stderr)
        if kind == 'level' and v in linear and t['converged']:
            lin = linearize(model, t)
            fastest = max(e[0] for e in lin['eigenvalues_coupled'])
            if check and fastest > UNSTABLE_REAL:
                lin['check'] = {'skipped': f'open-loop unstable (eigenvalue real part {fastest:.3f} 1/s): the nonlinear '
                                           'model diverges from the trim, so the sine check cannot run open loop'}
            elif check:
                lin['check'] = sine_check(model, t, lin)
                print(f'  check: worst {lin["check"]["worst_db"]:.2f} dB, {lin["check"]["worst_deg"]:.1f} deg', file=sys.stderr)
            else:
                print(f'  check: {lin["check"].get("skipped", "not run")}', file=sys.stderr)
            out['linear'].append(lin)
    return out


def compare(ref, new):
    L = COMPARE_LIMITS
    items = []

    def item(what, a, b, limit, relative=False):
        if a is None or b is None:
            items.append({'item': what, 'reference': a, 'new': b, 'passed': a is None and b is None})
            return
        diff = (b - a) / abs(a) if relative and abs(a) > 1e-12 else b - a
        items.append({'item': what, 'reference': a, 'new': b, 'difference': diff, 'limit': limit,
                      'relative': relative, 'passed': bool(abs(diff) <= limit)})

    def key(t):
        return t['kind'], t['airspeed_m_s'], t['requested_deg']
    new_trims = {key(t): t for t in new['trims']}
    for t in ref['trims']:
        n = new_trims.get(key(t))
        label = f"trim {t['kind']} {t['airspeed_m_s']} m/s"
        if n is None:
            items.append({'item': label, 'passed': False, 'note': 'missing in the new answers'})
            continue
        for q in ('alpha_deg', 'pitch_deg', 'beta_deg', 'bank_deg'):
            item(f'{label} {q}', t[q], n[q], L['angle_deg'])
        for c, v in t['commands'].items():
            item(f'{label} {c}', v, n['commands'].get(c), L['throttle'] if c == 'throttle' else L['command'])
    new_lin = {l['trim']['airspeed_m_s']: l for l in new['linear']}
    for l in ref['linear']:
        v = l['trim']['airspeed_m_s']
        n = new_lin.get(v)
        if n is None:
            items.append({'item': f'linear {v} m/s', 'passed': False, 'note': 'missing in the new answers'})
            continue
        nm = {m['name']: m for m in n['modes']}
        for m in l['modes']:
            o = nm.get(m['name'])
            if 'frequency_rad_s' in m:
                item(f'linear {v} m/s {m["name"]} frequency', m['frequency_rad_s'], o and o.get('frequency_rad_s'),
                     L['mode_relative'], True)
                item(f'linear {v} m/s {m["name"]} damping', m['damping'], o and o.get('damping'), L['mode_relative'], True)
            else:
                lim = L['slow_mode_relative'] if m['name'] == 'spiral' else L['mode_relative']
                item(f'linear {v} m/s {m["name"]} time constant', m['time_constant_s'], o and o.get('time_constant_s'),
                     lim, True)
        for s, rec in l['servo'].items():
            item(f'linear {v} m/s servo {s} pole', rec['pole_rad_s'], n['servo'].get(s, {}).get('pole_rad_s'),
                 L['servo_relative'], True)
            item(f'linear {v} m/s servo {s} delay_s', rec['delay_s'], n['servo'].get(s, {}).get('delay_s'), L['delay_s'])
        if 'rows' in l.get('check', {}) and 'rows' in n.get('check', {}):
            rows = {(r['pair'], r['rad_s']): r for r in n['check']['rows']}
            for r in l['check']['rows']:
                o = rows.get((r['pair'], r['rad_s']))
                label = f"linear {v} m/s sine {r['pair']} {r['rad_s']} rad/s"
                if o is None:
                    items.append({'item': label, 'passed': False, 'note': 'missing'})
                    continue
                items.append({'item': label + ' gain', 'difference_db': 20 * math.log10(o['measured_gain'] / r['measured_gain']),
                              'limit': L['gain_db'],
                              'passed': abs(20 * math.log10(o['measured_gain'] / r['measured_gain'])) <= L['gain_db']})
                dp = math.degrees(math.remainder(math.radians(o['measured_phase_deg'] - r['measured_phase_deg']), 2 * math.pi))
                items.append({'item': label + ' phase', 'difference_deg': dp, 'limit': L['phase_deg'],
                              'passed': abs(dp) <= L['phase_deg']})
    failed = [i for i in items if not i['passed']]
    return {'verdict': 'PASS' if not failed else 'FAIL', 'items': len(items), 'failed': failed, 'limits': L,
            'all': items}


def pairs(texts):
    out = []
    for t in texts or []:
        a, b = t.split(':')
        out.append((float(a), float(b)))
    return out


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('folder', nargs='?')
    p.add_argument('--config', action='append', default=[])
    p.add_argument('--level', type=float, nargs='*', default=[])
    p.add_argument('--turn', nargs='*', help='SPEED:BANK_DEG')
    p.add_argument('--sideslip', nargs='*', help='SPEED:BETA_DEG')
    p.add_argument('--linear', type=float, nargs='*', default=[])
    p.add_argument('--height', type=float, default=100.0)
    p.add_argument('--no-check', action='store_true')
    p.add_argument('--compare', nargs=2, metavar=('REFERENCE', 'NEW'))
    p.add_argument('--out')
    a = p.parse_args()
    if a.compare:
        res = compare(*(json.loads(Path(x).read_text()) for x in a.compare))
        text = json.dumps(res, indent=1)
        if a.out:
            Path(a.out).write_text(text + '\n')
        print(json.dumps({'verdict': res['verdict'], 'items': res['items'], 'failed': res['failed']}, indent=1))
        return 0 if res['verdict'] == 'PASS' else 1
    if not a.folder or not a.out:
        p.error('a vehicle folder and --out are needed (or --compare)')
    if not (a.level or a.linear or a.turn or a.sideslip):
        p.error('nothing to do: give --level, --turn, --sideslip or --linear')
    res = answers(a.folder, a.config, a.level, pairs(a.turn), pairs(a.sideslip), a.linear, a.height, not a.no_check)
    Path(a.out).write_text(json.dumps(res, indent=1) + '\n')
    bad = [t for t in res['trims'] if not t['converged']]
    failed_checks = [l['trim']['airspeed_m_s'] for l in res['linear'] if l.get('check', {}).get('passed') is False]
    print(json.dumps({'out': a.out, 'trims': len(res['trims']), 'not_converged': len(bad), 'linear': len(res['linear']),
                      'checks_outside_limits': failed_checks}))
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
