#!/usr/bin/env python3
"""Speed of a generated fast core, and of JSBSim on the same machine for comparison.

    JSBSIM_PYTHON=<unpacked jsbsim 1.3.3 wheel> <python with numpy> fastcore/bench.py vehicles/testbird [--out DIR]

The core: batches of n vehicles, 25 steps of 4 ms per call (0.1 s, a typical control period), on 1 thread and on several
threads (one slice of the batch per thread; the calls release the GIL). JSBSim: one instance, 1 ms frames as simhost
runs it, so 4 frames per 4 ms of simulated time. Writes <out>/bench.json.
"""
import argparse
import json
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
from fastcore import Core  # noqa: E402

FT = 0.3048


def flying(core, n, rng):
    x = core.zeros(n)
    core.set_state(x, pos_ned=(0, 0, 0), vel_body=np.c_[rng.uniform(15, 19, n), np.zeros(n), rng.uniform(0, 0.3, n)],
                   euler=(0.0, 0.01, 0.0), rates=(0, 0, 0), rpm=5000.0)
    u = np.zeros((n, core.nu))
    u[:, core.U['fcs/throttle-cmd-norm[0]']] = 0.64
    u[:, core.U['fcs/elevator-cmd-norm']] = 0.02
    e = core.env(n, origin_alt_msl=300.0)
    core.reset(x, u)
    return x, u, e


def time_core(core, n, threads, calls, k=25, dt=0.004):
    rng = np.random.default_rng(0)
    x, u, e = flying(core, n, rng)
    parts = np.array_split(np.arange(n), threads)
    xs = [np.ascontiguousarray(x[p]) for p in parts]
    us = [np.ascontiguousarray(u[p]) for p in parts]
    es = [np.ascontiguousarray(e[p]) for p in parts]
    for i in range(threads):   # warm up
        core.step(xs[i], us[i], es[i], dt=dt, k=k, outputs=False)
    barrier = threading.Barrier(threads + 1)

    def work(i):
        barrier.wait()
        for _ in range(calls):
            core.step(xs[i], us[i], es[i], dt=dt, k=k, outputs=False)
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
    return {'n': n, 'threads': threads, 'steps_per_call': k, 'wall_s': round(wall, 3), 'vehicle_steps': steps,
            'ns_per_vehicle_step': round(wall / steps * 1e9, 1),
            'ns_per_vehicle_step_per_thread': round(wall * threads / steps * 1e9, 1),
            'vehicle_steps_per_s': round(steps / wall), 'finite': bool(ok)}


def time_jsbsim(vehicle, frames=20000):
    from vehicle_check import load, start
    fdm = load(vehicle, 0.001)
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
    a = p.parse_args()
    name = Path(a.vehicle).resolve().name
    out = Path(a.out) if a.out else Path('build/fastcore') / name
    rep = {'vehicle': name, 'machine': {'cpu': cpu(), 'logical_cpus': os.cpu_count(), 'usable_cpus': cpus,
                                       'python': platform.python_version()}}
    for flavour, native in (('portable', False), ('native', True)):
        d = out / f'bench_{flavour}'
        gen.generate(a.vehicle, d)
        gen.build(d, name, native=native)
        core = Core(d, name)
        rows = [time_core(core, n, 1, max(4, 40000 // n)) for n in (1, 64, 1024, 4096)]
        rows += [time_core(core, 4096, t, 40) for t in a.threads if t > 1]
        rep[flavour] = rows
        print(flavour, json.dumps([{k: r[k] for k in ('n', 'threads', 'ns_per_vehicle_step', 'ns_per_vehicle_step_per_thread')} for r in rows]), flush=True)
    if os.environ.get('JSBSIM_PYTHON'):
        sys.path.insert(0, os.environ['JSBSIM_PYTHON'])
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
