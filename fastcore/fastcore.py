"""Python binding for a generated fast core (ctypes, numpy arrays; the calls release the GIL).

    import sys; sys.path.insert(0, '<toolkit>/fastcore')
    from fastcore import Core
    core = Core('build/fastcore/testbird')
    x = core.zeros(n); core.set_state(x, pos_ned=..., vel_body=..., euler=..., rates=..., rpm=...)
    u = np.zeros((n, core.nu)); u[:, core.U['fcs/throttle-cmd-norm[0]']] = 0.6
    env = core.env(n)
    core.reset(x, u)
    y = core.step(x, u, env, dt=0.004, k=25)      # 0.1 s, outputs at the final state

Arrays are float64, C-contiguous, one row per vehicle. The names of the columns are in core.X, core.U, core.E, core.Y
(from <name>_core.json).
"""
import ctypes
import json
import math
from pathlib import Path

import numpy as np

_D = ctypes.POINTER(ctypes.c_double)


def _ptr(a):
    return a.ctypes.data_as(_D) if a is not None else None


class Core:
    def __init__(self, folder, name=None):
        folder = Path(folder)
        name = name or folder.name
        self.layout = json.loads((folder / f'{name}_core.json').read_text())
        self.lib = ctypes.CDLL(str((folder / f'lib{name}_core.so').resolve()))
        self._reset = getattr(self.lib, f'{name}_reset')
        self._reset.argtypes = [ctypes.c_int, _D, _D]
        self._step = getattr(self.lib, f'{name}_step')
        self._step.argtypes = [ctypes.c_int, _D, _D, _D, ctypes.c_double, ctypes.c_int, _D]
        self._eval = getattr(self.lib, f'{name}_eval')
        self._eval.argtypes = [ctypes.c_int, _D, _D, ctypes.c_int, _D, _D]
        for k in ('_reset', '_step', '_eval'):
            getattr(self, k).restype = None
        L = self.layout
        self.X = {n: i for i, n in enumerate(L['x'])}
        self.U = {n: i for i, n in enumerate(L['u'])}
        self.E = {n: i for i, n in enumerate(L['env'])}
        self.Y = {n: i for i, n in enumerate(L['y'])}
        self.nx, self.nc, self.nu, self.ne, self.ny = len(L['x']), L['continuous'], len(L['u']), len(L['env']), len(L['y'])

    # -- arrays --------------------------------------------------------------------------------------------------------
    def zeros(self, n):
        x = np.zeros((n, self.nx))
        x[:, self.X['q0']] = 1.0
        return x

    def env(self, n, gravity=9.80665, origin_alt_msl=0.0, ground_alt_msl=0.0, wind_ned=(0.0, 0.0, 0.0)):
        e = np.zeros((n, self.ne))
        e[:, 0:3] = wind_ned
        e[:, 3] = gravity
        e[:, 4] = origin_alt_msl
        e[:, 5] = ground_alt_msl
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
            x[:, 13:13 + n_eng] = np.asarray(rpm, dtype=float).reshape(-1, n_eng) * (2.0 * math.pi / 60.0) \
                if np.ndim(rpm) else rpm * 2.0 * math.pi / 60.0

    # -- calls ---------------------------------------------------------------------------------------------------------
    def _check(self, a, cols, what):
        if a.dtype != np.float64 or not a.flags['C_CONTIGUOUS'] or a.ndim != 2 or a.shape[1] != cols:
            raise ValueError(f'{what}: need a C-contiguous float64 array of shape (n, {cols}), got {a.dtype} {a.shape}')

    def reset(self, x, u):
        self._check(x, self.nx, 'x')
        self._check(u, self.nu, 'u')
        self._reset(x.shape[0], _ptr(x), _ptr(u))

    def step(self, x, u, env, dt=0.004, k=1, y=None, outputs=True):
        """Advance x in place by k steps of dt. Returns the outputs at the final state (n, NY) unless outputs=False."""
        n = x.shape[0]
        self._check(x, self.nx, 'x')
        self._check(u, self.nu, 'u')
        self._check(env, self.ne, 'env')
        if outputs and y is None:
            y = np.empty((n, self.ny))
        self._step(n, _ptr(x), _ptr(u), _ptr(env), float(dt), int(k), _ptr(y) if outputs else None)
        return y if outputs else None

    def eval(self, x, env, jsbsim_order=False):
        """Derivatives of the continuous states (n, NC) and outputs (n, NY) at the states x."""
        n = x.shape[0]
        self._check(x, self.nx, 'x')
        self._check(env, self.ne, 'env')
        xd, y = np.empty((n, self.nc)), np.empty((n, self.ny))
        self._eval(n, _ptr(x), _ptr(env), int(bool(jsbsim_order)), _ptr(xd), _ptr(y))
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
