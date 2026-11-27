"""Deploy recipes: what one flight controller runs. The format is documented in docs/recipes.md.

A recipe is a folder in a vehicle repository:

    <recipe>/firmware/firmware.json   build recipe (make target, PX4 patches, external modules), outputs, identity
    <recipe>/firmware/<image>.px4     the built image, and parameters.json.xz: the firmware's own parameter list
    <recipe>/params.json              airframe / boot / verify_only / set values and the fc_owned patterns
    <recipe>/sd/etc/extras.txt        optional boot file; sd/etc/logging/logger_topics.txt optional logger topics
    <recipe>/hitl.json                optional flight: command script (after), check, model_config, ...

The expected parameters of an FC running a recipe are: the firmware's defaults, overlaid with the airframe and boot
values (set by the boot scripts; checked, never written), verify_only (checked, never written) and set (the only
values the toolkit writes). Parameters matching fc_owned belong to the physical FC (calibration, counters, the
operator's RC): read, but neither compared nor written.
"""
import hashlib
import json
import lzma
import re
import struct
from pathlib import Path

KINDS = {'Int32': 6, 'Float': 9}   # PX4 parameters.json type -> MAVLink param_type
SECTIONS = ['airframe', 'boot', 'verify_only', 'set']
INT32 = (-2 ** 31, 2 ** 31 - 1)
# Parameters PX4 itself rewrites, and the exact value it writes from the default. PX4 v1.18.0 EKF2 writes EKF2_SENS_EN
# at every disarm (src/modules/ekf2/EKF2.cpp, syncSensEnParam from the disarm edge): it sets only the GNSS 0 bit for GPS,
# so the default 8191 becomes 8189 after the first flight. Such a value is reported (px4_rewritten), not a failure.
PX4_REWRITES = {'EKF2_SENS_EN': lambda default: int(default) & ~0b10}


def sha256(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def load_firmware_params(path):
    """name -> entry of a PX4 parameters.json(.xz)."""
    raw = Path(path).read_bytes()
    listing = json.loads(lzma.decompress(raw) if str(path).endswith('.xz') else raw)
    out = {}
    for p in listing['parameters']:
        if p['name'] in out:
            raise ValueError(f'{path}: parameter {p["name"]} listed twice')
        out[p['name']] = p
    unknown = {p['type'] for p in out.values()} - set(KINDS)
    if unknown:
        raise ValueError(f'{path}: unknown parameter types {sorted(unknown)}')
    return out


def is_int32(value):
    return (not isinstance(value, bool) and isinstance(value, (int, float)) and float(value).is_integer()
            and INT32[0] <= value <= INT32[1])


def same(kind, a, b):
    """Equal as PX4 stores them: Int32 exactly, Float as float32."""
    if kind == 6:
        return is_int32(a) and is_int32(b) and int(a) == int(b)
    return struct.pack('<f', float(a)) == struct.pack('<f', float(b))


class Recipe:
    def __init__(self, folder, repo=None):
        self.dir = Path(folder).resolve()
        self.name = self.dir.name
        self.repo = Path(repo).resolve() if repo else find_repo(self.dir)
        self.firmware_info_path = self.dir / 'firmware' / 'firmware.json'
        self.firmware_info = json.loads(self.firmware_info_path.read_text())
        self.params_path = self.dir / 'params.json'
        self.params = json.loads(self.params_path.read_text())
        h = self.dir / 'hitl.json'
        self.hitl = json.loads(h.read_text()) if h.exists() else {}
        sd = self.dir / 'sd' / 'etc'
        self.boot_file = sd / 'extras.txt' if (sd / 'extras.txt').is_file() else None
        self.logger_topics = sd / 'logging' / 'logger_topics.txt' if (sd / 'logging' / 'logger_topics.txt').is_file() else None

    # -- firmware ------------------------------------------------------------------------------------------------------
    @property
    def build_recipe(self):
        return self.firmware_info.get('recipe')

    @property
    def image(self):
        out = (self.firmware_info.get('outputs') or {}).get('firmware')
        return self.dir / 'firmware' / out['file'] if out else None

    @property
    def firmware_params_path(self):
        return self.dir / self.params['firmware_params']['file']

    def local_problems(self):
        """The image and the parameter list on disk must be the ones the recipe records."""
        problems = []
        out = self.firmware_info.get('outputs') or {}
        if not self.image or not self.image.is_file():
            problems.append('no built image (build the recipe first)')
        elif sha256(self.image) != out['firmware']['sha256']:
            problems.append(f'{self.image.name}: SHA-256 differs from firmware.json')
        listing = self.firmware_params_path
        if not listing.is_file():
            problems.append('no firmware parameter list (build the recipe first)')
        else:
            actual = sha256(listing)
            for what, recorded in (('params.json firmware_params', self.params['firmware_params']['sha256']),
                                   ('firmware.json parameters', (out.get('parameters') or {}).get('sha256'))):
                if recorded != actual:
                    problems.append(f'{what}: {recorded} != {actual}')
        return problems

    def expected_board_version(self):
        """AUTOPILOT_VERSION.board_version of this firmware: PX4 reports the USB product id (CONFIG_CDCACM_PRODUCTID),
        which differs from the image's board id on some boards (Cube Orange+: 4184 against 1063)."""
        e = self.firmware_info['embedded']
        return e.get('board_version', e['board_id'])

    # -- parameters ----------------------------------------------------------------------------------------------------
    def managed(self):
        """name -> (expected value, section) for every parameter the recipe states."""
        out = {}
        for section in SECTIONS:
            for name, entry in self.params.get(section, {}).items():
                if name in out:
                    raise ValueError(f'{name} is in both {out[name][1]} and {section}')
                out[name] = (entry['value'], section)
        return out

    def owned(self, firmware):
        rule = re.compile('|'.join(self.params['fc_owned']['patterns']))
        return sorted(n for n in firmware if rule.search(n))

    def to_write(self):
        """The values the toolkit writes: the 'set' section only."""
        return {name: entry['value'] for name, entry in self.params.get('set', {}).items()}

    def check(self, readback):
        """Compare a readback (tools/fc.py read_all) with the recipe. Verdict PASS, FAIL (a value differs, or the FC
        or the local files are not this recipe's firmware) or INCOMPLETE (the readback is incomplete or inconsistent,
        or the recipe's lists no longer match the firmware)."""
        firmware = load_firmware_params(self.firmware_params_path)
        owned = set(self.owned(firmware))
        expected = self.managed()
        report = {k: [] for k in ('local_mismatch', 'identity', 'structure', 'wrong_value', 'not_default',
                                  'unknown_name', 'not_read', 'not_in_firmware', 'fc_owned_set_changed', 'redundant',
                                  'px4_rewritten')}
        report['local_mismatch'] = self.local_problems()
        version = readback.get('autopilot_version')
        e = self.firmware_info.get('embedded') or {}
        if not version:
            report['identity'].append({'problem': 'missing AUTOPILOT_VERSION', 'kind': 'incomplete'})
        else:
            if version.get('board_version') != self.expected_board_version():
                report['identity'].append({'problem': 'board', 'fc': version.get('board_version'),
                                           'expected': self.expected_board_version(), 'kind': 'fail'})
            if version.get('git_hash_prefix') != e['git_hash'][:10]:
                report['identity'].append({'problem': 'git hash', 'fc': version.get('git_hash_prefix'),
                                           'expected': e['git_hash'][:10], 'kind': 'fail'})
            if e.get('nuttx_git_hash') and version.get('os_hash_prefix') != e['nuttx_git_hash'][:16]:
                report['identity'].append({'problem': 'NuttX hash', 'fc': version.get('os_hash_prefix'),
                                           'expected': e['nuttx_git_hash'][:16], 'kind': 'fail'})
        resolved = self.params['fc_owned'].get('resolved_names', [])
        if resolved and sorted(owned) != resolved:
            report['fc_owned_set_changed'] = [{'added': sorted(owned - set(resolved)), 'removed': sorted(set(resolved) - owned)}]
        if not readback.get('complete'):
            report['structure'].append({'problem': 'readback incomplete', 'missing_indices': readback.get('missing_indices', [])[:20]})
        values = {}
        for entry in readback['parameters']:
            name = entry['name']
            if name in values:
                report['structure'].append({'problem': 'duplicate name', 'name': name})
                continue
            values[name] = entry
            if name not in firmware:
                report['not_in_firmware'].append(name)
            elif entry.get('type') != KINDS[firmware[name]['type']]:
                report['structure'].append({'problem': 'type', 'name': name, 'fc': entry.get('type'),
                                            'firmware': KINDS[firmware[name]['type']]})
        report['not_read'] = sorted(n for n in firmware if n not in values)
        for name, (value, section) in sorted(expected.items()):
            if name not in firmware:
                report['unknown_name'].append({'name': name, 'section': section})
            elif name in owned:
                raise ValueError(f'{name} is both fc_owned and in {section}')
            elif section == 'set' and same(KINDS[firmware[name]['type']], value, firmware[name].get('default', 0)):
                report['redundant'].append(name)   # equals the default: harmless, but not needed
        bad = {x['name'] for x in report['structure'] if 'name' in x}
        for name, entry in sorted(firmware.items()):
            if name in owned or name not in values or name in bad:
                continue
            kind, got = KINDS[entry['type']], values[name]['value']
            if name in expected:
                want, section = expected[name]
                if got is None or not same(kind, got, want):
                    report['wrong_value'].append({'name': name, 'section': section, 'fc': got, 'expected': want})
            elif got is None or not same(kind, got, entry.get('default', 0)):
                default = entry.get('default', 0)
                if name in PX4_REWRITES and got is not None and same(kind, got, PX4_REWRITES[name](default)):
                    report['px4_rewritten'].append({'name': name, 'fc': got, 'default': default})
                else:
                    report['not_default'].append({'name': name, 'fc': got, 'default': default})
        failed = (report['local_mismatch'] or report['wrong_value'] or report['not_default']
                  or any(x['kind'] == 'fail' for x in report['identity']))
        incomplete = (report['structure'] or report['not_read'] or report['not_in_firmware'] or report['unknown_name']
                      or report['fc_owned_set_changed'] or report['identity'])
        report['verdict'] = 'FAIL' if failed else 'INCOMPLETE' if incomplete else 'PASS'
        report.update(autopilot_version=version, fc_owned_skipped=len(owned),
                      managed={s: len(self.params.get(s, {})) for s in SECTIONS})
        return report


def find_repo(path):
    """The vehicle repository a recipe belongs to: the nearest folder upwards with sim2hitl.lock (or .git)."""
    p = Path(path).resolve()
    for d in [p, *p.parents]:
        if (d / 'sim2hitl.lock').exists():
            return d
    for d in [p, *p.parents]:
        if (d / '.git').exists():
            return d
    raise ValueError(f'{path}: not inside a vehicle repository (no sim2hitl.lock or .git above it)')
