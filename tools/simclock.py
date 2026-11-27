"""The clock of a pilot process: the wall clock, or simhost's simulated clock in lockstep.

    clock = simclock.from_env()                 # SIM2HITL_SIMCLOCK, SIM2HITL_PILOTSYNC
    clock.monotonic(); clock.sleep(seconds); clock.allow(until)

simhost writes the simulated time to its --simclock file every step, and in lockstep does not step past the time its
--pilot-sync file allows while that file was written within the last second of wall time. Both files hold 16 bytes:
two little-endian uint64, the time in ns, then the CLOCK_MONOTONIC ns of the write. simhost creates both at its start,
so the pilot starts after simhost.

Without a simclock path (HITL, or a SITL that is not in lockstep) this is time.monotonic and time.sleep. With one,
monotonic() is the simulated time and never goes back. sleep() waits in short wall-time slices and gives up after
WALL_BOUND times the asked time plus 5 s of wall time, so a stopped simhost cannot hang the pilot. With a pilot-sync
path as well, the process gates the simulation: allow(t) lets simhost step up to simulated time t, and every sleep()
allows its own wake-up, so the pilot gates from its first wait. Only the one process that flies writes the sync file.

Each file is read and written as one copy of 16 bytes: a reader can never see a half-cleared value (struct.pack_into
clears its bytes before it writes them; a reader then read 0 and slept for thousands of simulated seconds).
"""
import math
import mmap
import os
import struct
import time

WALL_BOUND = 4.0


class Clock:
    def __init__(self, path=None, sync=None):
        self.path = path
        self.map = self.sync = None
        self.last = 0.0
        if path:
            with open(path, 'rb') as f:
                self.map = mmap.mmap(f.fileno(), 16, access=mmap.ACCESS_READ)
        if path and sync:
            with open(sync, 'r+b') as f:
                self.sync = mmap.mmap(f.fileno(), 16)

    @property
    def simulated(self):
        return self.map is not None

    def allow(self, until):
        """Let simhost step up to simulated time `until` (s); nothing on the wall clock or without a sync file."""
        if self.sync is not None:
            self.sync[0:16] = struct.pack('<QQ', math.ceil(until * 1e9), time.monotonic_ns())  # never below until

    def monotonic(self):
        if self.map is None:
            return time.monotonic()
        self.last = max(self.last, int.from_bytes(self.map[0:8], 'little') / 1e9)
        return self.last

    def sleep(self, seconds):
        if self.map is None:
            time.sleep(seconds)
            return
        end, wall_end = self.monotonic() + seconds, time.monotonic() + WALL_BOUND * seconds + 5
        self.allow(end)
        while self.monotonic() < end and time.monotonic() < wall_end:
            time.sleep(0.0002)


def from_env(sync=True):
    """The clock named by SIM2HITL_SIMCLOCK (and, with sync, SIM2HITL_PILOTSYNC); the wall clock without them."""
    path = os.environ.get('SIM2HITL_SIMCLOCK') or None
    gate = os.environ.get('SIM2HITL_PILOTSYNC') or None
    for name, value in (('SIM2HITL_SIMCLOCK', path), ('SIM2HITL_PILOTSYNC', gate if sync else None)):
        if value and not (os.path.isfile(value) and os.path.getsize(value) >= 16):
            raise RuntimeError(f'{name}={value}: no 16-byte clock file (start simhost first)')
    return Clock(path, gate if sync else None)
