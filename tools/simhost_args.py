"""simhost's command-line arguments for a vehicle folder, its configuration files and scenario events."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'fastcore'))
from fastcore import load_config  # noqa: E402  (the one reader of configuration files, shared with the fast core)


def simhost_vehicle_args(toml, configs=(), events=()):
    """simhost arguments for a vehicle: its actuator map and servo channels, start position and record properties
    (vehicle.toml), its configuration files (JSBSim property and servo-chain settings, applied before the start), and
    scenario events (T:PROPERTY=VALUE)."""
    args, servo = [], []
    for m in toml['actuators']:
        args += ['--actuator', f"{m['channel']}:{m['property']}:{m['gain']}:{m.get('offset', 0.0)}"]
        if m.get('kind') == 'servo' and m['channel'] not in servo:
            servo.append(m['channel'])
    for ch in servo:
        args += ['--servo-channel', str(ch)]
    start = toml.get('start', {})
    for key, opt in (('lat_deg', '--lat'), ('lon_deg', '--lon'), ('agl_m', '--agl'), ('heading_deg', '--heading')):
        if key in start:
            args += [opt, repr(float(start[key]))]
    for prop in toml.get('record', {}).get('properties', []):
        args += ['--record-property', prop]
    for k, v in load_config(*configs).items():
        args += ['--set', f'{k}={v!r}']
    for e in events:
        args += ['--at', e]
    return args
