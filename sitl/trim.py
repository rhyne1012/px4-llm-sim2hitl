#!/usr/bin/env python3
"""Trim of the SkySurfer plant (steady level flight or steady coordinated turn) and the open-loop drop test.

  <venv python> -B sitl/trim.py
      [--airspeed 15 20 25] [--height 100] [--bank 0] [--drop 20] [--plant-lib PATH] [--json]

Default: level flight at 15, 20 and 25 m/s, 100 m, each followed by a 20 s drop test. Output: a table in
SI with kts / ft alongside (or one JSON line with --json).

Trim: the equilibrium of the plant core (plant/include/plant_core.h, plant_core_eval = f(x, u) on the same code
path as the simulation). Given airspeed V, height h, bank phi (heading 0, no wind), turn rate
psi_dot = g tan(phi) / V and body rates from the Euler kinematics (p = -psi_dot sin(theta),
q = psi_dot sin(phi) cos(theta), r = psi_dot cos(phi) cos(theta)). Unknowns (12): angle of attack,
sideslip, pitch, aileron (same command on both channels, as the HITL FC sends), elevator, rudder,
throttle and the five actuator states. The actuator states are eliminated inside the residual (each
actuator derivative is affine in its own state, so its rest value follows from two evaluations); the
remaining 7 unknowns solve body accelerations, angular accelerations and vertical velocity = 0 by damped
Newton iterations (finite-difference Jacobian, step limit, line search).

The surfaces pass a rate limiter (a hidden discrete state) after their servo, so every evaluation writes
the state and steps SETTLE times before taking f(x, u).

Linearization (--linearize, wings level only): central differences of plant_core_eval around the trim.
  full: the 37 states and 5 commands as the model has them, servos included.
  airframe: 8 states (u v w p q r phi theta), inputs directly at the surfaces. The servos are taken out of the matrices:
    the actuator states are set to their rest value for each command, so no block leaves the model.
  transfer functions: longitudinal and lateral, from the airframe matrices, with and without the servo poles read from
    the full matrices. The output is checked against the frequency response of the full model.
They are small-signal models of one trim: no saturation, no rate limit, no delay. --out FILE writes everything as JSON
(analysis/matlab/linear_model.m turns it into ss and zpk objects).

Drop test: start the plant at the trim state (rate limiters settled), hold the trim commands (nothing controls the aircraft) for
--drop seconds and report the drift. A correct trim drifts only through the slow modes (spiral, phugoid).

Commands are normalised like the HIL ABI controls[0..4]: elevator + = nose up, + on either aileron
channel rolls left. The plant library defaults to the one of the active model release (no PX4 or SITL build
needed); it must have core API 1.1 (plant_core_eval).
"""
import argparse
import ctypes as C
import json
import math
import sys
from pathlib import Path

import numpy as np

G0 = 9.80665
DT = 0.004
NX = 37  # PLANT_CORE_STATE_COUNT: 13 rigid body, 5 actuators, 16 turbulence, 3 gust
SETTLE = 40  # steps for the surface rate limiters to reach the equilibrium deflection (2 deg per step)
D = C.c_double
# CoreSnapshot indices (plant/include/plant_core.h)
S_POS, S_VNED, S_EULER, S_AIRSPEED, S_SURF = 0, 13, 16, 52, 66
X_SERVO = 13  # first actuator state
INPUTS = ('aileron_left', 'aileron_right', 'elevator', 'rudder', 'throttle')  # HIL ABI controls[0..4]
AIRFRAME_STATES = ('u', 'v', 'w', 'p', 'q', 'r', 'phi', 'theta')  # m/s, rad/s, rad
CHECK_RAD_S = (0.5, 2.0, 5.0, 10.0, 20.0, 50.0)  # frequencies of the check against the full model
CHECK_LIMIT = 0.02  # a larger difference means the split or a matrix is wrong: reported, not hidden


def default_plant_lib():
    """The plant library of the active model release (no PX4 or SITL build needed)."""
    import sys

    sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'hitl'))
    from host.release import read_release

    release, manifest = read_release(Path(__file__).resolve().parents[1] / 'hitl')
    return release / manifest['plant_library']


class _Initial(C.Structure):
    _fields_ = [('velocity_body_m_s', D * 3), ('height_m', D), ('euler_deg', D * 3)]


class Core:
    """The plant core through ctypes (plant_core.h, API 1.1)."""

    def __init__(self, path):
        self.lib = C.CDLL(str(path))
        self.lib.plant_core_size.restype = C.c_size_t
        self.lib.plant_core_api_version.restype = C.c_uint32
        if self.lib.plant_core_api_version() < 0x00010100:
            raise RuntimeError(f'{path}: core API {self.lib.plant_core_api_version():#x} has no plant_core_eval')
        self.path = Path(path)
        self.size = self.lib.plant_core_size()

    def new(self, height):
        core = C.create_string_buffer(self.size)
        ic = _Initial((D * 3)(10.0, 0.0, 0.0), height, (D * 3)(0.0, 0.0, 0.0))
        assert self.lib.plant_core_init(core, C.byref(ic)) == 0
        # The first step loads the integrators from the initial-condition input, which would overwrite a state
        # written by plant_core_eval; step once so that the template is past it.
        assert self.lib.plant_core_step(core, (D * 16)(), None) == 0
        return core

    def eval(self, template, x, controls, settle=SETTLE):
        """f(x, u) with the hidden discrete states settled: the surfaces pass a rate limiter after their
        servo transfer function, and the limiter keeps its previous output, so x is written and stepped
        `settle` times (continuous states reset to x each time) before the result is taken."""
        core = C.create_string_buffer(self.size)
        self.lib.plant_core_copy(core, template)
        xdot, snap = (D * NX)(), (D * 72)()
        u = (D * 16)(*(list(controls) + [0.0] * (16 - len(controls))))
        xs = (D * NX)(*x)
        for _ in range(settle):
            code = self.lib.plant_core_eval(core, xs, u, xdot, snap)
            if code:
                break
        return code, np.array(xdot[:]), np.array(snap[:]), core, u


def quaternion(phi, theta, psi):
    cr, sr, cp, sp, cy, sy = (math.cos(phi / 2), math.sin(phi / 2), math.cos(theta / 2), math.sin(theta / 2),
                              math.cos(psi / 2), math.sin(psi / 2))
    return [cr * cp * cy + sr * sp * sy, sr * cp * cy - cr * sp * sy, cr * sp * cy + sr * cp * sy,
            cr * cp * sy - sr * sp * cy]


def state(z, actuators, airspeed, height, bank):
    alpha, beta, theta = z[0], z[1], z[2]
    psi_dot = G0 * math.tan(bank) / airspeed
    x = [0.0, 0.0, -height]
    x += [airspeed * math.cos(alpha) * math.cos(beta), airspeed * math.sin(beta), airspeed * math.sin(alpha) * math.cos(beta)]
    x += quaternion(bank, theta, 0.0)
    x += [-psi_dot * math.sin(theta), psi_dot * math.sin(bank) * math.cos(theta), psi_dot * math.cos(bank) * math.cos(theta)]
    x += list(actuators) + [0.0] * 16 + [0.0, 0.0, 0.0]  # turbulence filters and gust distances at rest
    return x


def controls(z):
    aileron, elevator, rudder, throttle = z[3], z[4], z[5], z[6]
    return [aileron, aileron, elevator, rudder, throttle]


def residual(core, template, z, airspeed, height, bank):
    """Residual for the 7 unknowns; the actuator states are set to their rest values for the commands
    (each actuator derivative is affine in its own state: two evaluations give the root)."""
    u = controls(z)
    code0, xdot0, _, _, _ = core.eval(template, state(z, [0.0] * 5, airspeed, height, bank), u)
    code1, xdot1, _, _, _ = core.eval(template, state(z, [1.0] * 5, airspeed, height, bank), u)
    if code0 or code1:
        raise RuntimeError(f'plant_core_eval returned {code0 or code1}')
    slope = xdot1[13:18] - xdot0[13:18]
    actuators = -xdot0[13:18] / slope
    code, xdot, snap, _, _ = core.eval(template, state(z, actuators, airspeed, height, bank), u)
    if code != 0:
        raise RuntimeError(f'plant_core_eval returned {code}')
    f = np.concatenate([xdot[3:6], xdot[10:13] * 10.0, [snap[S_VNED + 2]]])
    return f, snap, actuators, float(np.max(np.abs(xdot[13:18])))


def trim(core, airspeed, height=100.0, bank_deg=0.0, iterations=100):
    """Unknowns z = [alpha, beta, theta, aileron, elevator, rudder, throttle]; damped Newton with line search."""
    bank = math.radians(bank_deg)
    template = core.new(height)
    # Throttle starts high: with the thrust lapse (T = max(0, Ts - K V sqrt(Ts))) a low throttle gives no thrust at
    # speed, hence no slope to follow (23 m/s did not converge from 0.2, 2026-10-25).
    z = np.array([math.radians(3.0), 0.0, math.radians(3.0), 0.0, 0.3, 0.0, 0.8])
    lower = np.array([-0.3, -0.3, -1.2, -1.0, -1.0, -1.0, 0.0])
    upper = np.array([0.3, 0.3, 1.2, 1.0, 1.0, 1.0, 1.0])
    step = 1e-7
    f, snap, actuators, act_res = residual(core, template, z, airspeed, height, bank)
    for _ in range(iterations):
        if np.max(np.abs(f)) < 1e-11:
            break
        steps = np.where(z + step > upper, -step, step)  # at a limit the plant clips the command: difference inward
        jac = np.column_stack([(residual(core, template, z + np.eye(7)[k] * steps[k], airspeed, height, bank)[0] - f)
                               / steps[k] for k in range(7)])
        dz = np.linalg.lstsq(jac, -f, rcond=None)[0]
        dz *= min(1.0, 0.2 / max(1e-12, np.max(np.abs(dz))))  # at most 0.2 (rad or command) per iteration
        scale, norm = 1.0, np.linalg.norm(f)
        while scale > 1e-4:
            candidate = np.clip(z + scale * dz, lower, upper)
            fc, sc, ac, ar = residual(core, template, candidate, airspeed, height, bank)
            if np.linalg.norm(fc) < norm:
                z, f, snap, actuators, act_res = candidate, fc, sc, ac, ar
                break
            scale *= 0.5
        else:
            break
    u = controls(z)
    psi_dot = G0 * math.tan(bank) / airspeed
    radius = airspeed ** 2 / (G0 * math.tan(bank)) if bank else math.inf
    residual_max = max(float(np.max(np.abs(f))), act_res)
    return {
        'airspeed_m_s': airspeed, 'airspeed_kts': airspeed / 0.514444, 'height_m': height, 'height_ft': height / 0.3048,
        'bank_deg': bank_deg, 'turn_rate_deg_s': math.degrees(psi_dot), 'turn_radius_m': radius,
        'turn_radius_ft': radius / 0.3048, 'load_factor': 1.0 / math.cos(bank),
        'alpha_deg': math.degrees(z[0]), 'beta_deg': math.degrees(z[1]), 'pitch_deg': math.degrees(z[2]),
        'aileron': float(u[0]), 'elevator': float(u[2]), 'rudder': float(u[3]), 'throttle': float(u[4]),
        'surface_deg': {'aileron_left': snap[S_SURF], 'aileron_right': snap[S_SURF + 1], 'elevator': snap[S_SURF + 2],
                        'rudder': snap[S_SURF + 3]},
        'residual_max': residual_max, 'converged': bool(residual_max < 1e-8),
        'state': state(z, actuators, airspeed, height, bank), 'controls': [float(v) for v in u],
    }


def drop(core, trim_result, seconds=20.0):
    """Hold the trim commands from the trim state; report the drift after `seconds`."""
    template = core.new(trim_result['height_m'])
    code, _, first, live, u = core.eval(template, trim_result['state'], trim_result['controls'])
    assert code == 0, code
    snap = (D * 72)()
    rows = [first]
    for _ in range(int(round(seconds / DT)) - 1):
        if core.lib.plant_core_step(live, u, snap) != 0:
            break
        rows.append(np.array(snap[:]))
    rows = np.array(rows)
    heading = np.unwrap(rows[:, S_EULER + 2])
    t = np.arange(len(rows)) * DT
    return {
        'seconds': float(t[-1] + DT),
        'airspeed_change_m_s': float(rows[-1, S_AIRSPEED] - rows[0, S_AIRSPEED]),
        'height_change_m': float(-(rows[-1, S_POS + 2] - rows[0, S_POS + 2])),
        'pitch_change_deg': math.degrees(rows[-1, S_EULER + 1] - rows[0, S_EULER + 1]),
        'roll_change_deg': math.degrees(rows[-1, S_EULER] - rows[0, S_EULER]),
        'turn_rate_deg_s': math.degrees((heading[-1] - heading[0]) / t[-1]) if t[-1] > 0 else 0.0,
        'max_abs': {'airspeed_m_s': float(np.max(np.abs(rows[:, S_AIRSPEED] - rows[0, S_AIRSPEED]))),
                    'height_m': float(np.max(np.abs(rows[:, S_POS + 2] - rows[0, S_POS + 2]))),
                    'pitch_deg': math.degrees(np.max(np.abs(rows[:, S_EULER + 1] - rows[0, S_EULER + 1]))),
                    'roll_deg': math.degrees(np.max(np.abs(rows[:, S_EULER] - rows[0, S_EULER])))},
    }


def transfer_function(a, b, c):
    """c (sI - a)^-1 b for one input and one output, by Faddeev-LeVerrier: numpy only, for the small airframe blocks."""
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
    return num[keep[0]:] if len(keep) else np.zeros(1), den


def with_servo(num, den, pole):
    """Multiply by the unit-gain first-order servo pole / (s + pole)."""
    return num * pole, np.polymul(den, [1.0, pole])


def _tf_record(num, den):
    return {'num': [float(v) for v in num], 'den': [float(v) for v in den], 'gain': float(num[0]),
            'zeros': [[float(z.real), float(z.imag)] for z in np.roots(num)],
            'poles': [[float(p.real), float(p.imag)] for p in np.roots(den)]}


def _classify(eigenvalues, complex_names, real_names):
    """Name the modes of one block: complex pairs and real roots, each slowest first."""
    pairs = sorted((s for s in eigenvalues if s.imag > 1e-6), key=abs)
    reals = sorted((s for s in eigenvalues if abs(s.imag) <= 1e-6), key=abs)
    named = zip(complex_names, pairs) if len(pairs) == len(complex_names) else (('mode', s) for s in pairs)
    modes = [{'name': name, 'real': float(s.real), 'imag': float(s.imag), 'frequency_rad_s': float(abs(s)),
              'damping': float(-s.real / abs(s))} for name, s in named]
    named = zip(real_names, reals) if len(reals) == len(real_names) else (('mode', s) for s in reals)
    modes += [{'name': name, 'real': float(s.real), 'imag': 0.0, 'time_constant_s': float(-1.0 / s.real)}
              for name, s in named if abs(s.real) > 1e-9]
    return modes


def linearize(core, trim_result):
    """Linear models around a wings-level trim; see the module docstring."""
    if trim_result['bank_deg'] != 0.0 or not trim_result['converged']:
        raise ValueError('linearize needs a converged wings-level trim')
    template = core.new(trim_result['height_m'])
    x0, u0 = np.array(trim_result['state']), np.array(trim_result['controls'])

    def f(x, u):
        code, xdot, _, _, _ = core.eval(template, list(x), list(u))
        if code:
            raise RuntimeError(f'plant_core_eval returned {code}')
        return xdot

    a_full, b_full = np.zeros((NX, NX)), np.zeros((NX, len(INPUTS)))
    for j in range(NX):
        step = np.zeros(NX)
        step[j] = 1e-5 * max(1.0, abs(x0[j]))
        a_full[:, j] = (f(x0 + step, u0) - f(x0 - step, u0)) / (2 * step[j])
    for j in range(len(INPUTS)):
        step = np.zeros(len(INPUTS))
        step[j] = 1e-5
        b_full[:, j] = (f(x0, u0 + step) - f(x0, u0 - step)) / (2 * step[j])

    servo = np.arange(X_SERVO, X_SERVO + len(INPUTS))
    a_servo, b_servo = a_full[np.ix_(servo, servo)], b_full[servo, :]
    # Which servo each command drives, and its pole, from the matrices (the state order is not the command order)
    channel = np.argmax(np.abs(b_servo), axis=0)
    poles = {INPUTS[i]: float(-a_servo[channel[i], channel[i]]) for i in range(len(INPUTS))}

    def airframe(y, du):
        x = x0.copy()
        x[3:6] = y[:3]
        x[6:10] = quaternion(y[6], y[7], 0.0)
        x[10:13] = y[3:6]
        x[servo] = x0[servo] - np.linalg.solve(a_servo, b_servo @ du)  # the servos at rest for this command
        xdot = f(x, u0 + du)
        p, q, r, phi, theta = y[3], y[4], y[5], y[6], y[7]
        return np.r_[xdot[3:6], xdot[10:13],
                     p + math.tan(theta) * (q * math.sin(phi) + r * math.cos(phi)),
                     q * math.cos(phi) - r * math.sin(phi)]

    y0 = np.r_[x0[3:6], x0[10:13], 0.0, math.radians(trim_result['pitch_deg'])]
    a, b = np.zeros((8, 8)), np.zeros((8, len(INPUTS)))
    zero = np.zeros(len(INPUTS))
    for j in range(8):
        step = np.zeros(8)
        step[j] = 1e-5
        a[:, j] = (airframe(y0 + step, zero) - airframe(y0 - step, zero)) / 2e-5
    for j in range(len(INPUTS)):
        step = np.zeros(len(INPUTS))
        step[j] = 1e-5
        b[:, j] = (airframe(y0, step) - airframe(y0, -step)) / 2e-5

    lon = [AIRFRAME_STATES.index(n) for n in ('u', 'w', 'q', 'theta')]
    lat = [AIRFRAME_STATES.index(n) for n in ('v', 'p', 'r', 'phi')]
    u_trim, w_trim = y0[0], y0[2]
    speed2 = u_trim ** 2 + y0[1] ** 2 + w_trim ** 2

    def row(names, values):
        c = np.zeros(4)
        for name, value in zip(names, values):
            c[name] = value
        return c

    # Outputs of each block: name, unit, row in the block's own states
    lon_out = {'q': ('rad/s', row([2], [1.0])), 'theta': ('rad', row([3], [1.0])), 'u': ('m/s', row([0], [1.0])),
               'alpha': ('rad', row([0, 1], [-w_trim / speed2, u_trim / speed2]))}
    lat_out = {'p': ('rad/s', row([1], [1.0])), 'r': ('rad/s', row([2], [1.0])), 'phi': ('rad', row([3], [1.0])),
               'beta': ('rad', row([0], [1.0 / math.sqrt(speed2)]))}
    index = {name: i for i, name in enumerate(INPUTS)}
    # The FC sends one aileron command on both channels (+ rolls left), so the lateral input is their sum
    inputs = {'elevator': (lon, lon_out, b[:, index['elevator']], poles['elevator']),
              'throttle': (lon, lon_out, b[:, index['throttle']], poles['throttle']),
              'aileron': (lat, lat_out, b[:, index['aileron_left']] + b[:, index['aileron_right']],
                          poles['aileron_right']),
              'rudder': (lat, lat_out, b[:, index['rudder']], poles['rudder'])}
    functions = {}
    for inp, (block, outputs, column, pole) in inputs.items():
        a_block = a[np.ix_(block, block)]
        for out, (unit, c) in outputs.items():
            num, den = transfer_function(a_block, column[block], c)
            snum, sden = with_servo(num, den, pole)
            functions[f'{out}/{inp}'] = {'unit': unit + ' per unit command', 'airframe': _tf_record(num, den),
                                         'with_servo': _tf_record(snum, sden)}

    # Check against the full model, which keeps the coupling this split ignores
    full_input = {'elevator': b_full[:, index['elevator']], 'throttle': b_full[:, index['throttle']],
                  'aileron': b_full[:, index['aileron_left']] + b_full[:, index['aileron_right']],
                  'rudder': b_full[:, index['rudder']]}
    pairs = {'q/elevator': 10 + 1, 'u/throttle': 3, 'p/aileron': 10, 'r/rudder': 10 + 2}
    worst = 0.0
    for key, state_index in pairs.items():
        record = functions[key]['with_servo']
        for w in CHECK_RAD_S:
            full = np.linalg.solve(1j * w * np.eye(NX) - a_full, full_input[key.split('/')[1]])[state_index]
            ours = np.polyval(record['num'], 1j * w) / np.polyval(record['den'], 1j * w)
            worst = max(worst, abs(ours - full) / max(abs(full), 1e-12))
    return {
        'states_full': 'position_ned[3] velocity_body[3] quaternion[4] rates_body[3] servos[5] turbulence[16] gust[3]',
        'inputs': list(INPUTS), 'A_full': a_full.tolist(), 'B_full': b_full.tolist(),
        'states_airframe': list(AIRFRAME_STATES), 'A_airframe': a.tolist(), 'B_airframe': b.tolist(),
        'servo_pole_rad_s': poles,
        'modes': _classify(np.linalg.eigvals(a[np.ix_(lon, lon)]), ('phugoid', 'short_period'), ()) +
        _classify(np.linalg.eigvals(a[np.ix_(lat, lat)]), ('dutch_roll',), ('spiral', 'roll')),
        'transfer_functions': functions,
        'check_against_full_model': {'rad_s': list(CHECK_RAD_S), 'max_relative_error': worst,
                                     'passed': bool(worst < CHECK_LIMIT)},
    }


def _factors(pairs):
    """'(s+a) (s^2+bs+c)' from [re, im] roots, slowest first."""
    roots = sorted((complex(*p) for p in pairs if p[1] >= -1e-9), key=abs)
    text = []
    for s in roots:
        if abs(s.imag) > 1e-6:
            text.append(f'(s²{-2 * s.real:+.3f}s{abs(s) ** 2:+.3f})')
        else:
            text.append('s' if abs(s.real) < 1e-7 else f'(s{-s.real:+.3f})')
    return ' '.join(text) or '1'


def linear_table(result):
    lin = result['linear']
    lines = [f"linear model at {result['airspeed_m_s']:.1f} m/s, {result['height_m']:.0f} m "
             f"(small signal; no saturation, rate limit or delay)", 'modes:']
    for m in lin['modes']:
        if m['imag']:
            lines.append(f"  {m['name']:13s} {m['real']:9.3f} ±{m['imag']:7.3f}i   {m['frequency_rad_s']:6.2f} rad/s, "
                         f"damping {m['damping']:.3f}")
        else:
            lines.append(f"  {m['name']:13s} {m['real']:9.3f}            "
                         + (f"UNSTABLE, doubles in {math.log(2) / m['real']:.1f} s" if m['real'] > 0
                            else f"time constant {m['time_constant_s']:.3f} s"))
    lines.append('servo poles (rad/s): ' + ', '.join(f'{k} {v:.1f}' for k, v in lin['servo_pole_rad_s'].items()))
    lines.append('transfer functions, airframe only, per unit command (+ aileron rolls left, + elevator noses up):')
    for key in ('q/elevator', 'theta/elevator', 'alpha/elevator', 'u/throttle', 'p/aileron', 'phi/aileron', 'r/rudder',
                'beta/rudder'):
        tf = lin['transfer_functions'][key]['airframe']
        lines.append(f"  {key:15s} = {tf['gain']:9.3f} {_factors(tf['zeros'])} / {_factors(tf['poles'])}")
    check = lin['check_against_full_model']
    lines.append(f"check against the full {NX}-state model, {check['rad_s'][0]:g}-{check['rad_s'][-1]:g} rad/s: "
                 f"max error {100 * check['max_relative_error']:.2f} %" + ('' if check['passed'] else '   CHECK FAILED'))
    return '\n'.join(lines)


def table(results):
    lines = ['airspeed            height          bank   alpha  pitch   beta  elevator aileron  rudder throttle'
             ' | drop: dV m/s    dh m  dpitch   droll turn deg/s']
    for r in results:
        d = r.get('drop')
        row = (f"{r['airspeed_m_s']:5.1f} m/s {r['airspeed_kts']:5.1f} kts {r['height_m']:5.0f} m {r['height_ft']:4.0f} ft "
               f"{r['bank_deg']:5.1f} {r['alpha_deg']:6.2f} {r['pitch_deg']:6.2f} {r['beta_deg']:6.2f}  "
               f"{r['elevator']:7.4f} {r['aileron']:7.4f} {r['rudder']:7.4f}  {r['throttle']:7.4f}")
        if d:
            row += (f" | {d['airspeed_change_m_s']:+7.3f} {d['height_change_m']:+7.2f} {d['pitch_change_deg']:+7.2f} "
                    f"{d['roll_change_deg']:+7.2f} {d['turn_rate_deg_s']:+8.2f}")
        lines.append(row + ('' if r['converged'] else '   NOT CONVERGED'))
    return '\n'.join(lines)


def main():
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument('--airspeed', type=float, nargs='+', default=[15.0, 20.0, 25.0])
    parser.add_argument('--height', type=float, default=100.0)
    parser.add_argument('--bank', type=float, default=0.0, help='deg; non-zero = steady coordinated turn')
    parser.add_argument('--drop', type=float, default=20.0, help='open-loop seconds from the trim (0 = none)')
    parser.add_argument('--plant-lib', type=Path)
    parser.add_argument('--linearize', action='store_true', help='linear model and transfer functions (wings level)')
    parser.add_argument('--out', type=Path, help='write the results as JSON to this new file')
    parser.add_argument('--json', action='store_true')
    args = parser.parse_args()
    if args.linearize and args.bank:
        parser.error('--linearize needs --bank 0')
    if args.out and args.out.exists():
        parser.error(f'{args.out} exists')
    core = Core(args.plant_lib or default_plant_lib())
    results = []
    for airspeed in args.airspeed:
        r = trim(core, airspeed, args.height, args.bank)
        if args.drop > 0:
            r['drop'] = drop(core, r, args.drop)
        if args.linearize:
            r['linear'] = linearize(core, r)
        results.append(r)
    report = {'plant_lib': str(core.path), 'trims': results}
    if args.out:
        args.out.write_text(json.dumps(report))
    if args.json:
        print(json.dumps(report))
    else:
        print(f'plant library: {core.path}')
        print(table(results))
        for r in results:
            if 'linear' in r:
                print()
                print(linear_table(r))
    if any(not r['linear']['check_against_full_model']['passed'] for r in results if 'linear' in r):
        sys.exit(1)


if __name__ == '__main__':
    main()
