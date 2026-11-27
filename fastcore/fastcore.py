"""Python binding for a generated fast core (ctypes, numpy arrays; the calls release the GIL).

    import sys; sys.path.insert(0, '<toolkit>/fastcore')
    from fastcore import Core, load_config
    core = Core('build/fastcore/testbird')
    x = core.zeros(n); core.set_state(x, pos_ned=..., vel_body=..., euler=..., rates=..., rpm=...)
    u = np.zeros((n, core.nu)); u[:, core.U['fcs/throttle-cmd-norm[0]']] = 0.6
    p = core.params(n, load_config('vehicles/testbird/configs/aft_cg.toml'))   # per-vehicle parameters
    env = core.env(n, latitude_deg=22.9)
    core.reset(x, u, p)
    y = core.step(x, u, p, env, dt=0.004, k=25)   # 0.1 s, outputs at the final state

Arrays are float64, C-contiguous, one row per vehicle. The names of the columns are in core.X, core.U, core.P, core.E,
core.Y (from <name>_core.json). Parameters use their JSBSim property names and units, the same names an override file
gives JSBSim, so one configuration file serves both.
"""
import ctypes
import json
import math
import tomllib
from pathlib import Path

import numpy as np

_D = ctypes.POINTER(ctypes.c_double)
EARTH_RATE = 7.292115e-5   # rad/s, WGS84 (JSBSim FGInertial)


def _ptr(a):
    return a.ctypes.data_as(_D) if a is not None else None


def load_config(*paths):
    """Property settings from configuration files (TOML, a [set] table of property = value); later files win."""
    out = {}
    for path in paths:
        d = tomllib.loads(Path(path).read_text())
        for k, v in d.get('set', {}).items():
            out[k] = float(v)
    return out


class Core:
    def __init__(self, folder, name=None):
        folder = Path(folder)
        name = name or folder.name
        self.layout = json.loads((folder / f'{name}_core.json').read_text())
        self.lib = ctypes.CDLL(str((folder / f'lib{name}_core.so').resolve()))
        self._reset = getattr(self.lib, f'{name}_reset')
        self._reset.argtypes = [ctypes.c_int, _D, _D, _D]
        self._reset.restype = None
        self._step = getattr(self.lib, f'{name}_step')
        self._step.argtypes = [ctypes.c_int, _D, _D, _D, _D, ctypes.c_double, ctypes.c_int, _D]
        self._step.restype = ctypes.c_int
        self._eval = getattr(self.lib, f'{name}_eval')
        self._eval.argtypes = [ctypes.c_int, _D, _D, _D, ctypes.c_int, _D, _D]
        self._eval.restype = None
        L = self.layout
        self.X = {n: i for i, n in enumerate(L['x'])}
        self.U = {n: i for i, n in enumerate(L['u'])}
        self.P = {n: i for i, n in enumerate(L['p'])}
        self.E = {n: i for i, n in enumerate(L['env'])}
        self.Y = {n: i for i, n in enumerate(L['y'])}
        self.nx, self.nc, self.nu, self.ne, self.ny = len(L['x']), L['continuous'], len(L['u']), len(L['env']), len(L['y'])
        self.np = len(L['p'])

    # -- arrays --------------------------------------------------------------------------------------------------------
    def zeros(self, n):
        x = np.zeros((n, self.nx))
        x[:, self.X['q0']] = 1.0
        return x

    def params(self, n, *settings):
        """Parameters for n vehicles: the vehicle's defaults, then each settings dict (property -> value) in order. An
        unknown property is an error: the core cannot represent it, and JSBSim would silently create it."""
        p = np.tile(np.asarray(self.layout['p_default'], dtype=float), (n, 1)) if self.np else np.zeros((n, 1))
        for s in settings:
            for k, v in s.items():
                if k not in self.P:
                    raise KeyError(f'{k} is not a parameter of this core (see {self.layout["vehicle"]}_core.json "p")')
                p[:, self.P[k]] = v
        return np.ascontiguousarray(p)

    def env(self, n, latitude_deg, gravity=9.80665, origin_alt_msl=0.0, ground_alt_msl=0.0, wind_ned=(0.0, 0.0, 0.0),
            earth_rate=EARTH_RATE):
        """The environment: the latitude sets the Earth rate's direction (Coriolis); earth_rate=0 for a non-rotating
        Earth. gravity is the effective gravity there (gravitation and centrifugal)."""
        e = np.zeros((n, self.ne))
        e[:, 0:3] = wind_ned
        e[:, 3] = gravity
        e[:, 4] = origin_alt_msl
        e[:, 5] = ground_alt_msl
        e[:, 6] = latitude_deg
        e[:, 7] = earth_rate
        return e

    def set_state(self, x, pos_ned=None, vel_body=None, euler=None, rates=None, rpm=None):
        if pos_ned is not None:
            x[:, 0:3] = pos_ned
        if vel_body is not None:
            x[:, 3:6] = vel_body
        if euler is not None:
            e = np.broadcast_to(np.asarray(euler, dtype=float), (x.shape[0], 3))
            x[:, 6:10] = euler_to_quat(e[:, 0], e[:, 1], e[:, 2])
        if rates is not None:
            x[:, 10:13] = rates
        if rpm is not None:
            n_eng = sum(1 for k in self.X if k.startswith('omega_rps['))
            x[:, 13:13 + n_eng] = np.broadcast_to(np.asarray(rpm, dtype=float).reshape(-1, 1) if np.ndim(rpm) == 1
                                                  else np.asarray(rpm, dtype=float), (x.shape[0], n_eng)) * (2 * math.pi / 60)

    # -- calls ---------------------------------------------------------------------------------------------------------
    def _check(self, a, cols, what):
        if a.dtype != np.float64 or not a.flags['C_CONTIGUOUS'] or a.ndim != 2 or a.shape[1] != max(cols, 1):
            raise ValueError(f'{what}: need a C-contiguous float64 array of shape (n, {cols}), got {a.dtype} {a.shape}')

    def reset(self, x, u, p):
        self._check(x, self.nx, 'x')
        self._check(u, self.nu, 'u')
        self._check(p, self.np, 'p')
        self._reset(x.shape[0], _ptr(x), _ptr(u), _ptr(p))

    def step(self, x, u, p, env, dt=0.004, k=1, y=None, outputs=True):
        """Advance x in place by k steps of dt. Returns the outputs at the final state (n, NY) unless outputs=False."""
        n = x.shape[0]
        for a, c, w in ((x, self.nx, 'x'), (u, self.nu, 'u'), (p, self.np, 'p'), (env, self.ne, 'env')):
            self._check(a, c, w)
        if outputs and y is None:
            y = np.empty((n, self.ny))
        bad = self._step(n, _ptr(x), _ptr(u), _ptr(p), _ptr(env), float(dt), int(k), _ptr(y) if outputs else None)
        if bad:
            raise ValueError(f'vehicle {bad - 1}: servo-chain times must be whole multiples of dt={dt} and the delay at '
                             f'most {self.layout["servo_capacity_steps"]} steps')
        return y if outputs else None

    def eval(self, x, p, env, jsbsim_order=False):
        """Derivatives of the continuous states (n, NC) and outputs (n, NY) at the states x."""
        n = x.shape[0]
        for a, c, w in ((x, self.nx, 'x'), (p, self.np, 'p'), (env, self.ne, 'env')):
            self._check(a, c, w)
        xd, y = np.empty((n, self.nc)), np.empty((n, self.ny))
        self._eval(n, _ptr(x), _ptr(p), _ptr(env), int(bool(jsbsim_order)), _ptr(xd), _ptr(y))
        return xd, y


def euler_to_quat(phi, theta, psi):
    """Body-to-NED quaternion (scalar first) of 3-2-1 Euler angles."""
    cr, sr = np.cos(np.asarray(phi) / 2), np.sin(np.asarray(phi) / 2)
    cp, sp = np.cos(np.asarray(theta) / 2), np.sin(np.asarray(theta) / 2)
    cy, sy = np.cos(np.asarray(psi) / 2), np.sin(np.asarray(psi) / 2)
    return np.stack([cr * cp * cy + sr * sp * sy, sr * cp * cy - cr * sp * sy,
                     cr * sp * cy + sr * cp * sy, cr * cp * sy - sr * sp * cy], axis=-1)


def quat_to_euler(q):
    q = np.asarray(q)
    q0, q1, q2, q3 = q[..., 0], q[..., 1], q[..., 2], q[..., 3]
    phi = np.arctan2(2 * (q0 * q1 + q2 * q3), 1 - 2 * (q1 * q1 + q2 * q2))
    theta = np.arcsin(np.clip(2 * (q0 * q2 - q3 * q1), -1, 1))
    psi = np.arctan2(2 * (q0 * q3 + q1 * q2), 1 - 2 * (q2 * q2 + q3 * q3))
    return np.stack([phi, theta, psi], axis=-1)


class ServoChainRef:
    """An independent Python implementation of avionics/servo_chain.h, for checks: PWM hold, then delay, in ticks."""

    def __init__(self, n, period_s, phase_s, delay_s, dt, cmd):
        def ticks(t):
            k = round(t / dt)
            if abs(k * dt - t) > 1e-9 * (1 + abs(t)):
                raise ValueError(f'{t} s is not a multiple of {dt} s')
            return k
        self.frame = ticks(period_s) if period_s > 0 else 1
        self.phase = ticks(phase_s)
        self.delay = ticks(delay_s)
        self.tick = 0
        self.held = list(cmd)
        self.line = [list(cmd) for _ in range(self.delay)]

    def __call__(self, cmd):
        if self.tick == self.phase:
            self.held = list(cmd)
        self.tick = (self.tick + 1) % self.frame
        if not self.delay:
            return list(self.held)
        self.line.append(list(self.held))
        return self.line.pop(0)
