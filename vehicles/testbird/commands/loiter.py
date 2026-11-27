"""Testbird: after the pilot's level-off, hand the aircraft to PX4's loiter (AUTO_LOITER) and keep it there 60 s."""
from sequence import Mode, Wait

ON_FINISH = 'loiter'


def build_sequence():
    return [Mode(4, 3, timeout=8.), Wait(60.)]
