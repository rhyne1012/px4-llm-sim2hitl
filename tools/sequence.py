"""Command scripts for the pilot (tools/pilot.py): what it does after a stable takeoff. The contract is docs/pilot.md.

A command script is a Python file in a vehicle repository, given to the pilot as `--after <path>`. It is loaded and
checked before the pilot opens its port, and then ticked by the pilot's loop on its one link: a script never opens a
socket, sleeps or starts a process. Two forms:

- build_sequence() returns a list of the actions below, and ON_FINISH says what follows the last one ('hold', 'loiter'
  or 'release'). The actions come from this module: `from sequence import Mode, Sticks, Wait`.
- make_script() returns an object with `finish` ('hold', 'loiter' or 'release'), begin(), cancel(reason) and
  tick(flight, now), for a script that reacts to PX4 (messages, a mission upload, RC switches). It checks its own
  modes and its own end.

INPUT = 'rc' at module level makes the pilot a transmitter (tools/rc_output.py) instead of a MANUAL_CONTROL source.
A script's folder's parent is appended to sys.path, so scripts in one folder import each other as <folder>.<name>.
"""
from dataclasses import dataclass
import importlib.util
import math
from pathlib import Path
import sys

FINISH = ('hold', 'loiter', 'release')
MAIN_MODES = (1, 2, 3, 4, 5, 6, 7, 8)   # PX4 custom main modes: MANUAL .. STABILIZED
STABILIZED, AUTO, AUTO_LOITER = 7, 4, 3


@dataclass(frozen=True)
class Wait:
    """Keep the last sticks for `seconds`."""
    seconds: float


@dataclass(frozen=True)
class Mode:
    """Request a PX4 mode every second until the heartbeat shows it; fails after `timeout`."""
    main_mode: int
    sub_mode: int = 0
    timeout: float = 5.


@dataclass(frozen=True)
class Expect:
    """Wait, without commanding anything, for PX4 to switch to this mode by itself (a failsafe, for example); the last
    sticks keep streaming (none after RcOff). Fails after `timeout`."""
    main_mode: int
    sub_mode: int = 0
    timeout: float = 5.


@dataclass(frozen=True)
class Select:
    """Request this mode at once and every second for `seconds`, also when PX4 already shows it: a person moving the
    mode switch. After PX4's offboard-loss fallback PX4 shows Stabilized while the person's intention is still
    OFFBOARD; Mode(7) would complete at once without a request, Select(7) ends that intention. PX4 must show the mode
    at the end. The last sticks keep streaming."""
    main_mode: int
    sub_mode: int = 0
    seconds: float = 2.


@dataclass(frozen=True)
class RcOff:
    """The transmitter off: no stick frames until RcOn (PX4's RC-loss failsafe: COM_RC_LOSS_T, then NAV_RCL_ACT).
    Heartbeats and mode requests go on (the telemetry link stays). No Sticks until RcOn; RcOn before the end."""


@dataclass(frozen=True)
class RcOn:
    """The transmitter back on, with the last sticks."""


@dataclass(frozen=True)
class Sticks:
    """MANUAL_CONTROL x/y/z/r, normalized (pitch, roll, yaw -1..1; throttle 0..1) for `seconds`; not angles."""
    pitch: float
    roll: float
    throttle: float
    seconds: float
    yaw: float = 0.


ACTIONS = (Wait, Mode, Expect, Select, RcOff, RcOn, Sticks)


def positive(value):
    return isinstance(value, (int, float)) and not isinstance(value, bool) and math.isfinite(value) and value > 0


def mode_ok(main_mode, sub_mode):
    return (type(main_mode) is int and main_mode in MAIN_MODES and type(sub_mode) is int and 0 <= sub_mode <= 255)


def validate(actions):
    off = False
    for action in actions:
        if not isinstance(action, ACTIONS):
            name = type(action).__name__
            if name in {a.__name__ for a in ACTIONS}:
                raise ValueError(f'{name} comes from {type(action).__module__}, not from the toolkit: '
                                 f'import the actions with "from sequence import {name}, ..."')
            raise ValueError('unsupported command action: ' + name)
        if isinstance(action, (RcOff, RcOn)):
            if off == isinstance(action, RcOff):
                raise ValueError('RcOff and RcOn must alternate, starting with RcOff')
            off = isinstance(action, RcOff)
        elif off and isinstance(action, Sticks):
            raise ValueError('no Sticks while the transmitter is off (RcOff ... RcOn)')
        elif isinstance(action, Wait):
            if not positive(action.seconds):
                raise ValueError('Wait.seconds must be finite and positive')
        elif isinstance(action, Select):
            if not (mode_ok(action.main_mode, action.sub_mode) and positive(action.seconds)):
                raise ValueError('Select requires a main mode 1..8, a submode 0..255 and positive seconds')
        elif isinstance(action, (Mode, Expect)):
            # 6 = OFFBOARD: PX4 enters it only while a source sends the offboard signal, and leaves it through its own
            # offboard-loss failsafe when the signal stops.
            if not (mode_ok(action.main_mode, action.sub_mode) and positive(action.timeout)):
                raise ValueError(f'{type(action).__name__} requires a main mode 1..8, a submode 0..255 and a positive '
                                 'timeout')
        elif isinstance(action, Sticks):
            values = (action.pitch, action.roll, action.yaw, action.throttle)
            if not all(isinstance(x, (int, float)) and not isinstance(x, bool) and math.isfinite(x) for x in values):
                raise ValueError('stick values must be finite numbers')
            if not (all(-1 <= x <= 1 for x in values[:3]) and 0 <= action.throttle <= 1 and positive(action.seconds)):
                raise ValueError('pitch/roll/yaw must be -1..1, throttle 0..1, seconds positive')
    if off:
        raise ValueError('RcOff without RcOn: the script must turn the transmitter back on')


def load_script(path):
    """Load and check a command script file; returns the sequence or script object, state 'waiting'."""
    path = Path(path).expanduser().resolve()
    if path.suffix != '.py' or not path.is_file():
        raise ValueError(f'{path}: not a command script file (.py)')
    if path.name in ('sequence.py', '__init__.py'):
        raise ValueError('select a command script, not a helper module')
    if str(path.parent.parent) not in sys.path:
        sys.path.append(str(path.parent.parent))
    spec = importlib.util.spec_from_file_location('_command_script_' + path.stem, path)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    source = getattr(module, 'INPUT', 'manual')
    if source not in ('manual', 'rc'):
        raise ValueError("INPUT must be 'manual' or 'rc'")
    if callable(getattr(module, 'make_script', None)):
        script = module.make_script()
        if not all(callable(getattr(script, m, None)) for m in ('begin', 'cancel', 'tick')):
            raise ValueError('make_script() must return an object with begin(), cancel(reason) and tick(flight, now)')
        if getattr(script, 'finish', None) not in FINISH:
            raise ValueError('script finish must be hold, loiter or release')
        script.name, script.input, script.state, script.index, script.reason = path.stem, source, 'waiting', 0, ''
        return script
    if not callable(getattr(module, 'build_sequence', None)):
        raise ValueError('command script must export build_sequence() or make_script()')
    finish = getattr(module, 'ON_FINISH', None)
    if finish not in FINISH:
        raise ValueError('ON_FINISH must be hold, loiter or release')
    sequence = CommandSequence(path.stem, module.build_sequence(), finish)
    sequence.input = source
    return sequence


class CommandSequence:
    """A build_sequence() script: one action at a time, at most one step per tick; any mode PX4 shows that the
    sequence did not ask for fails it."""

    def __init__(self, name, actions, finish='hold'):
        self.name, self.actions, self.finish = name, tuple(actions), finish
        validate(self.actions)
        if finish not in FINISH:
            raise ValueError('invalid finish policy')
        self.state = 'waiting'
        self.index = 0
        self.started = self.next_mode_command = None
        self.reason = ''
        self.input = 'manual'
        self.expected_mode = (STABILIZED, 0)
        self.rc_off = False         # RcOff .. RcOn: the pilot sends no stick frames

    def begin(self):
        if self.state != 'waiting':
            raise RuntimeError('command script can only start once')
        self.state = 'running'

    def cancel(self, reason):
        if self.state in ('waiting', 'running'):
            self.state, self.reason = 'cancelled', reason

    def fail(self, flight, reason):
        self.state, self.reason = 'failed', reason
        flight.release(reason)

    def end(self, flight):
        self.state = 'complete'
        v = flight.vehicle
        if self.finish == 'release':
            flight.release('command script complete')
        elif self.finish == 'loiter':
            if (v.mode, v.sub_mode) != (AUTO, AUTO_LOITER):
                self.fail(flight, 'loiter requires PX4 AUTO_LOITER')
            else:
                # PX4 navigates; the neutral sticks keep the manual input available for PX4's RC-loss failsafe.
                flight.sticks[:] = [0, 0, round(1000 * flight.a.cruise_throttle), 0]
                flight.pitch_command = 0.
                flight.go('loiter', 'PX4 AUTO_LOITER confirmed; neutral input keepalive')
        elif v.mode != STABILIZED:
            self.fail(flight, 'hold requires Stabilized at the end of the script')
        else:
            flight.sticks[1] = flight.sticks[3] = 0

    def tick(self, flight, now):
        if self.state != 'running':
            return
        if self.index >= len(self.actions):
            self.end(flight)
            return
        action = self.actions[self.index]
        if self.started is None:
            self.started, self.next_mode_command = now, now
        v = flight.vehicle
        current = (v.mode, v.sub_mode)
        allowed = {self.expected_mode}
        if isinstance(action, (Mode, Expect, Select)):
            allowed.add((action.main_mode, action.sub_mode))
        if current not in allowed:
            self.fail(flight, 'PX4 mode changed outside the command sequence')
            return
        target = (getattr(action, 'main_mode', None), getattr(action, 'sub_mode', None))
        complete = False
        if isinstance(action, Mode):
            complete = current == target
            if not complete:
                if now - self.started >= action.timeout:
                    self.fail(flight, 'mode change timed out')
                    return
                if now >= self.next_mode_command:
                    self.next_mode_command = now + 1.
                    flight.command(flight.mode_command_id, 1, *target)
        elif isinstance(action, Expect):
            complete = current == target
            if not complete and now - self.started >= action.timeout:
                self.fail(flight, 'expected mode change timed out')
                return
        elif isinstance(action, (RcOff, RcOn)):
            self.rc_off = isinstance(action, RcOff)
            complete = True
        elif isinstance(action, Select):
            if now >= self.next_mode_command:
                self.next_mode_command = now + 1.
                flight.command(flight.mode_command_id, 1, *target)
            if now - self.started >= action.seconds:
                if current != target:
                    self.fail(flight, 'selected mode not shown')
                    return
                complete = True
        elif isinstance(action, Sticks):
            flight.sticks[:] = [round(1000 * action.pitch), round(1000 * action.roll),
                                round(1000 * action.throttle), round(1000 * action.yaw)]
            flight.pitch_command = -action.pitch * flight.pitch_scale
            complete = now - self.started >= action.seconds
        else:  # Wait: the last sticks keep streaming
            complete = now - self.started >= action.seconds
        if complete:
            if isinstance(action, (Mode, Expect, Select)):
                self.expected_mode = target
            self.index += 1
            self.started = None
