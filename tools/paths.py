"""Where the toolkit keeps its files on this computer: the one place for its name.

    cache()   ~/.cache/px4-jsbsim-sim2hitl/v2 (XDG_CACHE_HOME): board records and roles, deploy reports, firmware build
              records, SITL FC builds and instances, flight runs
    config()  ~/.config/px4-jsbsim-sim2hitl (XDG_CONFIG_HOME): px4_root, the PX4 tree when SIM2HITL_PX4_ROOT is not set

The toolkit was called px4-llm-sim2hitl until v2.1.1. Its v2 files moved with the name; v1 keeps the old name (a
~/.cache/px4-llm-sim2hitl without a v2 folder is v1's and is not touched). A v2 folder still at the old place stops
the tools with the command that moves it, so board roles and flash records are never silently left behind.
"""
import os
import sys
from pathlib import Path

NAME = 'px4-jsbsim-sim2hitl'
OLD_NAME = 'px4-llm-sim2hitl'   # the name before v2.1.1


def _base(variable, default):
    return Path(os.environ.get(variable) or Path.home() / default)


def cache():
    base = _base('XDG_CACHE_HOME', '.cache')
    new, old = base / NAME / 'v2', base / OLD_NAME / 'v2'
    if old.is_dir() and not new.exists():
        sys.exit(f'{old} holds this computer\'s toolkit files (board roles, flash records, runs) under the toolkit\'s '
                 f'name before v2.1.1; move it first: mkdir -p {new.parent} && mv {old} {new}')
    return new


def config():
    return _base('XDG_CONFIG_HOME', '.config') / NAME
