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
        if bad > 0:
            raise ValueError(f'vehicle {bad - 1}: servo-chain times must be whole multiples of dt={dt} and the delay at '
                             f'most {self.layout["servo_capacity_steps"]} steps')
        if bad < 0:
            raise ValueError(f'vehicle {-bad - 1}: atmosphere/turb-type must be 0, 1 (none), 3 (Milspec) or 4 (Tustin)')
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


TURB_STATES = ('counter', 'psiw_rad', 'xi_u_km1', 'nu_u_km1', 'xi_v_km1', 'xi_v_km2', 'nu_v_km1', 'nu_v_km2', 'xi_w_km1',
               'xi_w_km2', 'nu_w_km1', 'nu_w_km2', 'xi_p_km1', 'nu_p_km1', 'xi_q_km1', 'xi_r_km1',
               'wind_n_mps', 'wind_e_mps', 'wind_d_mps', 'p_rps', 'q_rps', 'r_rps')
_POE_ALT = np.array([500, 1750, 3750, 7500, 15000, 25000, 35000, 45000, 55000, 65000, 75000, 80000], float)
_POE = np.array([[3.2, 2.2, 1.5, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                 [4.2, 3.6, 3.3, 1.6, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0, 0.0],
                 [6.6, 6.9, 7.4, 6.7, 4.6, 2.7, 0.4, 0.0, 0.0, 0.0, 0.0, 0.0],
                 [8.6, 9.6, 10.6, 10.1, 8.0, 6.6, 5.0, 4.2, 2.7, 0.0, 0.0, 0.0],
                 [11.8, 13.0, 16.0, 15.1, 11.6, 9.7, 8.1, 8.2, 7.9, 4.9, 3.2, 2.1],
                 [15.6, 17.6, 23.0, 23.6, 22.1, 20.0, 16.0, 15.1, 12.1, 7.9, 6.2, 5.1],
                 [18.7, 21.5, 28.4, 30.2, 30.7, 31.0, 25.2, 23.1, 17.5, 10.7, 8.4, 7.2]])
_M64 = (1 << 64) - 1


def _mix(z):
    z = (z + 0x9E3779B97F4A7C15) & _M64
    z = ((z ^ (z >> 30)) * 0xBF58476D1CE4E5B9) & _M64
    z = ((z ^ (z >> 27)) * 0x94D049BB133111EB) & _M64
    return z ^ (z >> 31)


def turb_normals(seed, counter):
    """The four standard normal numbers of runtime/turbulence.h fc_turb_normals for one vehicle and step."""
    s, c = _mix(int(seed) & _M64), int(counter)
    uu = [((_mix(s ^ ((c * 4 + j) & _M64)) >> 11) + 0.5) / 9007199254740992.0 for j in range(4)]
    out = []
    for j in (0, 2):
        r, a = math.sqrt(-2.0 * math.log(uu[j])), 2.0 * math.pi * uu[j + 1]
        out += [r * math.cos(a), r * math.sin(a)]
    return out


class TurbulenceRef:
    """An independent Python transcription of JSBSim 1.3.3 FGWinds::Turbulence (types 3 Milspec and 4 Tustin) and the
    core's random numbers, for checks: one vehicle, one step from the state at its start. Units as JSBSim's inside;
    wind_ned (m/s) and pqr_body (rad/s) are the held outputs."""

    def __init__(self, type_, w20_fps, severity, seed, wingspan_ft):
        self.type, self.w20, self.idx, self.seed = int(type_), float(w20_fps), int(severity), seed
        self.b = wingspan_ft if wingspan_ft != 0 else 30.0
        self.s = dict.fromkeys(TURB_STATES, 0.0)
        self.counter = 0

    def sigma_scale(self, h):
        h = max(h, 10.0)
        if h <= 1000:
            return h / (0.177 + 0.000823 * h) ** 1.2, h, 0.1 * self.w20 / (0.177 + 0.000823 * h) ** 0.4, 0.1 * self.w20
        poe = float(np.interp(h, _POE_ALT, _POE[min(max(self.idx, 1), 7) - 1]))
        if h <= 2000:
            L = 1000 + (h - 1000.) / 1000. * 750.
            sig = 0.1 * self.w20 + (h - 1000.) / 1000. * (poe - 0.1 * self.w20)
            return L, L, sig, sig
        return 1750.0, 1750.0, poe, poe

    def step(self, C, uvw_mps, wind_ned_mps, h_ft, T_V):
        """C: body to NED (3x3). Returns (wind_ned_mps, pqr_body) after the step."""
        s, ft = self.s, 0.3048
        V = np.linalg.norm(np.asarray(uvw_mps) - C.T @ np.asarray(wind_ned_mps)) / ft
        on = self.type in (3, 4) and self.idx != 0 and V != 0
        if on:
            L_u, L_w, sig_u, sig_w = self.sigma_scale(h_ft)
            b = self.b
            sig_p, L_p = 1.9 / math.sqrt(L_w * b) * sig_w, math.sqrt(L_w * b) / 2.6
            tau_u, tau_w, tau_p, tau_q, tau_r = L_u / V, L_w / V, L_p / V, 4 * b / math.pi / V, 3 * b / math.pi / V
            nu_u, nu_v, nu_w, nu_p = turb_normals(self.seed, self.counter)
            if self.type == 4:
                om_w, om_v = V / L_w, V / L_u
                cb, cbp = 1 / tau_u / math.tan(T_V / 2 / tau_u), 1 / tau_p / math.tan(T_V / 2 / tau_p)
                cbq, cbr = 1 / tau_q / math.tan(T_V / 2 / tau_q), 1 / tau_r / math.tan(T_V / 2 / tau_r)
                r3 = math.sqrt(3.0)

                def second(om, sig, nu, x1, x2, n1, n2):
                    return (-2 * (om ** 2 - cb ** 2) / (om + cb) ** 2 * x1 - (om - cb) ** 2 / (om + cb) ** 2 * x2
                            + sig * math.sqrt(3 * om / T_V) / (om + cb) ** 2
                            * ((cb + om / r3) * nu + 2 / r3 * om * n1 + (om / r3 - cb) * n2))
                xi_u = (-(1 - cb * tau_u) / (1 + cb * tau_u) * s['xi_u_km1']
                        + sig_u * math.sqrt(2 * tau_u / T_V) / (1 + cb * tau_u) * (nu_u + s['nu_u_km1']))
                xi_v = second(om_v, sig_u, nu_v, s['xi_v_km1'], s['xi_v_km2'], s['nu_v_km1'], s['nu_v_km2'])
                xi_w = second(om_w, sig_w, nu_w, s['xi_w_km1'], s['xi_w_km2'], s['nu_w_km1'], s['nu_w_km2'])
                xi_p = (-(1 - cbp * tau_p) / (1 + cbp * tau_p) * s['xi_p_km1']
                        + sig_p * math.sqrt(2 * tau_p / T_V) / (1 + cbp * tau_p) * (nu_p + s['nu_p_km1']))
                gq, gr = 4 * b * cbq / math.pi / V, 3 * b * cbr / math.pi / V
                xi_q = -(1 - gq) / (1 + gq) * s['xi_q_km1'] + cbq / V / (1 + gq) * (xi_w - s['xi_w_km1'])
                xi_r = -(1 - gr) / (1 + gr) * s['xi_r_km1'] + cbr / V / (1 + gr) * (xi_v - s['xi_v_km1'])
            else:
                xi_u = (1 - T_V / tau_u) * s['xi_u_km1'] + sig_u * math.sqrt(2 * T_V / tau_u) * nu_u
                xi_v = (1 - 2 * T_V / tau_u) * s['xi_v_km1'] + sig_u * math.sqrt(4 * T_V / tau_u) * nu_v
                xi_w = (1 - 2 * T_V / tau_w) * s['xi_w_km1'] + sig_w * math.sqrt(4 * T_V / tau_w) * nu_w
                xi_p = (1 - T_V / tau_p) * s['xi_p_km1'] + sig_p * math.sqrt(2 * T_V / tau_p) * nu_p
                xi_q = (1 - T_V / tau_q) * s['xi_q_km1'] + math.pi / 4 / b * (xi_w - s['xi_w_km1'])
                xi_r = (1 - T_V / tau_r) * s['xi_r_km1'] + math.pi / 3 / b * (xi_v - s['xi_v_km1'])
            cp, sp = math.cos(s['psiw_rad']), math.sin(s['psiw_rad'])
            s['wind_n_mps'], s['wind_e_mps'], s['wind_d_mps'] = ((cp * xi_u + sp * xi_v) * ft,
                                                                (-sp * xi_u + cp * xi_v) * ft, xi_w * ft)
            s['p_rps'], s['q_rps'], s['r_rps'] = C.T @ np.array([cp * xi_p + sp * xi_q, -sp * xi_p + cp * xi_q, xi_r])
            s['xi_u_km1'], s['nu_u_km1'] = xi_u, nu_u
            s['xi_v_km2'], s['xi_v_km1'], s['nu_v_km2'], s['nu_v_km1'] = s['xi_v_km1'], xi_v, s['nu_v_km1'], nu_v
            s['xi_w_km2'], s['xi_w_km1'], s['nu_w_km2'], s['nu_w_km1'] = s['xi_w_km1'], xi_w, s['nu_w_km1'], nu_w
            s['xi_p_km1'], s['nu_p_km1'], s['xi_q_km1'], s['xi_r_km1'] = xi_p, nu_p, xi_q, xi_r
        else:
            for k in ('wind_n_mps', 'wind_e_mps', 'wind_d_mps', 'p_rps', 'q_rps', 'r_rps'):
                s[k] = 0.0
        if wind_ned_mps[0] != 0.0:
            psi = math.atan2(wind_ned_mps[1], wind_ned_mps[0])
            s['psiw_rad'] = psi + 2 * math.pi if psi < 0 else psi
        self.counter += 1
        s['counter'] = float(self.counter)
        return (np.array([s['wind_n_mps'], s['wind_e_mps'], s['wind_d_mps']]),
                np.array([s['p_rps'], s['q_rps'], s['r_rps']]))
