#!/usr/bin/env python3
"""Speed of a generated fast core, and of JSBSim on the same machine for comparison.

    JSBSIM_PYTHON=<unpacked jsbsim 1.3.3 wheel> <python with numpy> fastcore/bench.py vehicles/testbird [--out DIR]

The core: batches of n vehicles, 25 steps of 4 ms per call (0.1 s, a typical control period), on 1 thread and on several
threads (one slice of the batch per thread; the calls release the GIL). JSBSim: one instance, 1 ms frames as simhost
runs it, so 4 frames per 4 ms of simulated time. Writes <out>/bench.json.
"""
import argparse
import json
import math
import os
import platform
import sys
import threading
import time
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
sys.path.insert(0, str(HERE.parent / 'tools'))
import gen  # noqa: E402
from fastcore import Core, load_config  # noqa: E402

FT = 0.3048


START = None   # the vehicle's level trim (trim_start), so every vehicle flies, not falls, while it is timed


def trim_start(vehicle, speed):
    """Level trim at speed and 100 m from tools/linear.py (it needs the JSBSim Python module); None without it."""
    try:
        import linear
    except ImportError:
        return None
    m = linear.Model(vehicle)
    tr = linear.trim(m, 'level', speed, 100.0)
    s = tr['state']
    return {'speed_mps': speed, 'vel_body': (s['u'], s['v'], s['w']), 'euler': (s['phi'], s['theta'], 0.0),
            'u': {prop: tr['commands'][name] for name, prop in m.props}}


def flying(core, n, rng, settings=None):
    x = core.zeros(n)
    if START:
        v = START['vel_body']
        core.set_state(x, pos_ned=(0, 0, 0), vel_body=np.c_[v[0] + rng.uniform(-0.5, 0.5, n), np.full(n, v[1]),
                                                            np.full(n, v[2])], euler=START['euler'], rates=(0, 0, 0),
                       rpm=5000.0)
        u = np.zeros((n, core.nu))
        for prop, val in START['u'].items():
            u[:, core.U[prop if prop in core.U else f'{prop}[0]']] = val
    else:   # without JSBSim: a fixed start (Testbird's level flight at 17 m/s)
        core.set_state(x, pos_ned=(0, 0, 0), vel_body=np.c_[rng.uniform(15, 19, n), np.zeros(n), rng.uniform(0, 0.3, n)],
                       euler=(0.0, 0.01, 0.0), rates=(0, 0, 0), rpm=5000.0)
        u = np.zeros((n, core.nu))
        u[:, core.U['fcs/throttle-cmd-norm[0]']] = 0.64
        u[:, core.U['fcs/elevator-cmd-norm']] = 0.02
    e = core.env(n, latitude_deg=22.9, origin_alt_msl=300.0)
    p = core.params(n, settings or {})
    core.reset(x, u, p)
    return x, u, p, e


def time_core(core, n, threads, calls, k=25, dt=0.004, settings=None, label='defaults'):
    rng = np.random.default_rng(0)
    x, u, p, e = flying(core, n, rng, settings)
    parts = np.array_split(np.arange(n), threads)
    xs = [np.ascontiguousarray(x[q]) for q in parts]
    us = [np.ascontiguousarray(u[q]) for q in parts]
    es = [np.ascontiguousarray(e[q]) for q in parts]
    ps = [np.ascontiguousarray(p[q]) for q in parts]
    for i in range(threads):   # warm up
        core.step(xs[i], us[i], ps[i], es[i], dt=dt, k=k, outputs=False)
    barrier = threading.Barrier(threads + 1)

    def work(i):
        barrier.wait()
        for _ in range(calls):
            core.step(xs[i], us[i], ps[i], es[i], dt=dt, k=k, outputs=False)
        barrier.wait()

    ts = [threading.Thread(target=work, args=(i,)) for i in range(threads)]
    for t in ts:
        t.start()
    barrier.wait()
    t0 = time.perf_counter()
    barrier.wait()
    wall = time.perf_counter() - t0
    for t in ts:
        t.join()
    steps = n * calls * k
    ok = all(np.isfinite(xi).all() for xi in xs)
    return {'n': n, 'threads': threads, 'steps_per_call': k, 'parameters': label, 'wall_s': round(wall, 3), 'vehicle_steps': steps,
            'ns_per_vehicle_step': round(wall / steps * 1e9, 1),
            'ns_per_vehicle_step_per_thread': round(wall * threads / steps * 1e9, 1),
            'vehicle_steps_per_s': round(steps / wall), 'finite': bool(ok)}


def time_jsbsim(vehicle, frames=20000):
    from vehicle_check import load, start
    fdm = load(vehicle, 0.001)
    for k in ('rate/rotational', 'rate/translational', 'position/rotational', 'position/translational'):
        fdm[f'simulation/integrator/{k}'] = 3   # Adams-Bashforth 2, as simhost
    if START:
        start(fdm, 300.0, START['speed_mps'], math.degrees(START['euler'][1]))
        for prop, val in START['u'].items():
            fdm[prop] = val
    else:
        start(fdm, 300.0, 17.0, 1.0)
        fdm['fcs/throttle-cmd-norm'] = 0.64
        fdm['fcs/elevator-cmd-norm'] = 0.02
    for _ in range(1000):
        fdm.run()
    t0 = time.perf_counter()
    for _ in range(frames):
        fdm.run()
    wall = time.perf_counter() - t0
    return {'frames_1ms': frames, 'wall_s': round(wall, 3), 'us_per_1ms_frame': round(wall / frames * 1e6, 2),
            'us_per_4ms_of_flight': round(4 * wall / frames * 1e6, 2)}


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('vehicle')
    p.add_argument('--out', help='default build/fastcore/<vehicle>')
    cpus = len(os.sched_getaffinity(0))
    p.add_argument('--threads', type=int, nargs='+', default=sorted({1, 4, max(1, cpus // 2), cpus}),
                   help='default: 1, 4, half and all of the CPUs this process may use')
    p.add_argument('--speed', type=float, default=17.0, help='airspeed of the level trim the vehicles start from (m/s)')
    a = p.parse_args()
    global START
    if os.environ.get('JSBSIM_PYTHON'):
        sys.path.insert(0, os.environ['JSBSIM_PYTHON'])
    START = trim_start(a.vehicle, a.speed)
    name = Path(a.vehicle).resolve().name
    out = Path(a.out) if a.out else Path('build/fastcore') / name
    rep = {'vehicle': name, 'machine': {'cpu': cpu(), 'logical_cpus': os.cpu_count(), 'usable_cpus': cpus,
                                       'python': platform.python_version()},
           'start': START or 'fixed: 15-19 m/s, throttle 0.64, elevator 0.02 (no JSBSim Python module for a trim)'}
    for flavour, native in (('portable', False), ('native', True)):
        d = out / f'bench_{flavour}'
        gen.generate(a.vehicle, d)
        gen.build(d, name, native=native)
        core = Core(d, name)
        rows = [time_core(core, n, 1, max(4, 40000 // n)) for n in (1, 64, 1024, 4096)]
        rows += [time_core(core, 4096, t, 40) for t in a.threads if t > 1]
        for cfg in sorted((Path(a.vehicle) / 'configs').glob('*.toml')):   # the vehicle's configurations (servo chain, ...)
            rows.append(time_core(core, 4096, 1, 10, settings=load_config(cfg), label=cfg.name))
        rep[flavour] = rows
        print(flavour, json.dumps([{k: r[k] for k in ('n', 'threads', 'parameters', 'ns_per_vehicle_step', 'ns_per_vehicle_step_per_thread')} for r in rows]), flush=True)
    try:
        rep['jsbsim'] = time_jsbsim(a.vehicle)
        print('jsbsim', json.dumps(rep['jsbsim']), flush=True)
    except ImportError:
        rep['jsbsim'] = 'not measured: no JSBSim Python module'
    (out / 'bench.json').write_text(json.dumps(rep, indent=1) + '\n')
    print(json.dumps({'bench': str(out / 'bench.json')}))


def cpu():
    try:
        for line in Path('/proc/cpuinfo').read_text().splitlines():
            if line.startswith('model name'):
                return line.split(':', 1)[1].strip()
    except OSError:
        pass
    return platform.processor()


if __name__ == '__main__':
    main()
