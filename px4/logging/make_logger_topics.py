#!/usr/bin/env python3
"""Generate an SD-card logger topic list that logs what an SDLOG_PROFILE logs, within the logger's 255 slots.

Why: PX4 v1.18's logger has 255 topic slots (src/modules/logger/logged_topics.h MAX_TOPICS_NUM). Its default set
grew (163 fixed slots, 137 in v1.17), and a multi-instance topic reserves a slot for every instance it asks for, used
or not. On this vehicle SDLOG_PROFILE 49 (default + high rate + debug) and even 41 fill the table before the debug
set: debug_vect (attitude_doublet's ad_stage record) is not logged ("Too many subscriptions", record 20261125-1430).

What: the same topics and intervals the profile gives, from PX4's own source (logged_topics.cpp), written one line per
topic instance so that only the instances this vehicle has take a slot. PX4's logger reads the list from
/fs/microsd/etc/logging/logger_topics.txt (PX4 docs, "Logging": customizing the logged topics). Since v1.18 the list is
added to SDLOG_PROFILE's topics (v1.17: it replaced them), so a recipe with this list sets SDLOG_PROFILE 0: the logger
then logs the list alone (logged_topics.cpp initialize_logged_topics).

How, as initialize_logged_topics() does for the profile's bits, in its order:
  1. each set's add_*_topics() as written: the SITL-only block left out (the list is for the FC; SITL logs the same),
     the 'estimator*' loop expanded over the firmware's topics at its kEKFVerboseIntervalMilliseconds; a topic already
     added only gets the later call's interval, per instance (LoggedTopics::add_topic);
  2. topics the firmware does not have are left out (--fw-topics: the build's msg/topics_sources);
  3. instances: a topic keeps as many as PX4 asks for, but no more than were seen (--seen: ULogs of this vehicle, or
     an existing list '<topic> <interval> <instance>' made from this FC type's logs); an optional topic never seen is
     left out (PX4 adds it only if it exists at start), a required one keeps instance 0 (PX4 always adds it).

  python3 px4/logging/make_logger_topics.py --px4 <PX4 tree> --fw-topics <build>/msg/topics_sources --profile 49 \\
      --seen LOG.ulg LIST.txt ... --out FILE

Adapted from the derived project skysurfer-unstable-sim2hitl (px4/logging/make_logger_topics.py, 2026-11-21, a model
identification list for PX4 v1.17) for v1.18's add-to-profile semantics and for any profile.
"""
import argparse
import re
import sys
import textwrap
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SETS = [(0, 'add_default_topics', 'default'), (1, 'add_estimator_replay_topics', 'estimator replay'),
        (2, 'add_thermal_calibration_topics', 'thermal calibration'),
        (3, 'add_system_identification_topics', 'system identification'), (4, 'add_high_rate_topics', 'high rate'),
        (5, 'add_debug_topics', 'debug'), (6, 'add_sensor_comparison_topics', 'sensor comparison'),
        (7, 'add_vision_and_avoidance_topics', 'vision and avoidance'),
        (11, 'add_high_rate_sensors_topics', 'high rate sensors')]
UNSUPPORTED = {8: 'raw IMU gyro FIFO', 9: 'raw IMU accel FIFO', 10: 'MAVLink tunnel'}  # not plain add_topic calls
CALL = re.compile(r'\badd_(optional_)?topic(_multi)?\(\s*"([a-z0-9_]+)"\s*(?:,\s*([0-9A-Za-z_]+))?\s*(?:,\s*([0-9A-Za-z_]+))?')
EKF_INTERVAL = re.compile(r'kEKFVerboseIntervalMilliseconds\s*=\s*(\d+)')
LINE = 78        # characters the logger reads of a line (fgets into 80 bytes, with the newline)
MULTI_MAX = 4    # instances of a multi topic without a count (ORB_MULTI_MAX_INSTANCES is larger); --seen limits it
SLOTS = 255      # logged_topics.h MAX_TOPICS_NUM


def function_body(text, name):
    start = text.index(f'void LoggedTopics::{name}()')
    depth, i = 0, text.index('{', start)
    for j in range(i, len(text)):
        depth += {'{': 1, '}': -1}.get(text[j], 0)
        if depth == 0:
            return text[i + 1:j]
    raise ValueError(name)


def calls(body, fw_topics):
    """(name, interval, instances, optional) in order, as the function calls them."""
    out, skip, ekf = [], False, 0
    for line in body.splitlines():
        s = line.strip()
        if s.startswith('#ifdef CONFIG_ARCH_BOARD_PX4_SITL'):
            skip = True
        elif skip and s.startswith('#endif'):
            skip = False
        if skip or s.startswith('//'):
            continue
        m = EKF_INTERVAL.search(s)
        if m:
            ekf = int(m.group(1))
        if 'strncmp(topic_list[i]->o_name, "estimator", 9)' in s:
            out += [(t, ekf, MULTI_MAX, True) for t in sorted(fw_topics) if t.startswith('estimator')]
            continue
        m = CALL.search(s)
        if not m:
            continue
        optional, multi, name, interval, count = bool(m.group(1)), bool(m.group(2)), m.group(3), m.group(4), m.group(5)
        interval = int(interval) if interval and interval.isdigit() else 0
        n = (int(count) if count and count.isdigit() else MULTI_MAX) if multi else 1
        out.append((name, interval, n, optional))
    return out


def seen_instances(paths):
    """topic -> instances seen: ULogs (analysis/ulog.py) or lists '<topic> <interval> <instance>'."""
    sys.path.insert(0, str(ROOT / 'analysis'))
    import ulog  # noqa: E402
    seen = {}
    for path in map(Path, paths):
        if path.suffix == '.ulg':
            items = [(name, multi) for (name, multi) in ulog.read(path).topics]
        else:
            items = [(w[0], int(w[2])) for w in (x.split() for x in path.read_text().splitlines())
                     if len(w) == 3 and not w[0].startswith('#')]
        for name, instance in items:
            seen[name] = max(seen.get(name, 0), instance + 1)
    return seen


def fw_topic_names(path):
    path = Path(path)
    if path.is_dir():
        return {m for f in path.glob('*') for m in re.findall(r'ORB_DEFINE\(([a-z0-9_]+)', f.read_text(errors='replace'))}
    return set(path.read_text().split())


def main():
    ap = argparse.ArgumentParser(description=__doc__.split('\n')[0])
    ap.add_argument('--px4', required=True, type=Path, help='PX4 tree of the locked version')
    ap.add_argument('--fw-topics', required=True, type=Path,
                    help='the firmware build\'s msg/topics_sources folder (ORB_DEFINE names), or one name per line')
    ap.add_argument('--profile', required=True, type=int, help='the SDLOG_PROFILE whose topics to list')
    ap.add_argument('--seen', nargs='*', default=[], help='ULogs of this vehicle / lists made from this FC type\'s logs')
    ap.add_argument('--note', default='', help='one line on what the list is for, written into its header')
    ap.add_argument('--out', required=True, type=Path)
    a = ap.parse_args()
    bad = [f'{b} ({w})' for b, w in UNSUPPORTED.items() if a.profile & (1 << b)]
    if bad:
        sys.exit('profile bits not supported here: ' + ', '.join(bad))
    text = (a.px4 / 'src/modules/logger/logged_topics.cpp').read_text()
    fw = fw_topic_names(a.fw_topics)
    sets = [(fn, label) for bit, fn, label in SETS if a.profile & (1 << bit)]
    interval, optional, order = {}, {}, []   # (name, instance) -> interval; name -> optional in every call
    for fn, _ in sets:
        for name, ms, n, opt in calls(function_body(text, fn), fw):
            if name not in fw:
                continue
            optional[name] = optional.get(name, True) and opt
            for i in range(n):
                if (name, i) not in interval:
                    order.append((name, i))
                interval[(name, i)] = ms          # a later call sets the interval of an instance already added
    seen = seen_instances(a.seen) if a.seen else None
    lines, dropped = [], []
    for name, i in order:
        if seen is not None:
            if name not in seen:
                if optional[name]:
                    if i == 0:
                        dropped.append(name)
                    continue
                if i > 0:
                    continue
            elif i >= seen[name]:
                continue
        lines.append(f'{name} {interval[(name, i)]} {i}')
    if len(lines) > SLOTS:
        sys.exit(f'{len(lines)} topic instances: more than the logger\'s {SLOTS} slots')
    head = [f'PX4 logger topic list = SDLOG_PROFILE {a.profile} '
            f'({" + ".join(label for _, label in sets)}) of {a.px4.name}, generated by '
            'px4/logging/make_logger_topics.py: do not edit. Use with SDLOG_PROFILE 0 (since v1.18 a list is added to '
            'the profile\'s topics).']
    if a.note:
        head.append(a.note)
    sources = ', '.join(Path(s).name for s in a.seen) or 'the counts PX4 asks for'
    head += [f'Instances from: {sources}.',
             f'Optional topics never seen on this vehicle (left out): {" ".join(dropped) or "none"}.',
             f'{len(lines)} topic instances (logger limit {SLOTS}). Format: <topic> <interval ms, 0 = every sample> '
             '<instance>.']
    head = ['# ' + w for x in head for w in textwrap.wrap(x, LINE - 2)]
    if max(len(x) for x in head + lines) > LINE:
        sys.exit(f'a line is longer than the logger reads ({LINE} characters)')
    a.out.write_text('\n'.join(head + lines) + '\n')
    print(f'{a.out}: {len(lines)} topic instances, {len(dropped)} optional topics left out')


if __name__ == '__main__':
    main()
