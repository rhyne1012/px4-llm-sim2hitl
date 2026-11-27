"""Transmitter emulation for the pilot: sticks and switches as RC_CHANNELS_OVERRIDE, through the FC's RC calibration.

PX4 v1.18.0 turns RC_CHANNELS_OVERRIDE into input_rc (mavlink_receiver.cpp:2256-2341), and rc_update normalizes each
channel with the FC's own RCn_MIN/TRIM/MAX/REV, with no dead zone (rc_update.cpp:439-458). A throttle trim at the
minimum is moved to the middle (rc_update.cpp:172-189), so throttle spans -1..1 like MANUAL_CONTROL z/500-1
(mavlink_receiver.cpp:2357-2364). Here the normalized stick values a MANUAL_CONTROL frame carries are turned back into
PWM through that calibration. Switch positions use rc_update's thresholds (524-537) and its mode-slot formula (568-592).
RCn_REV is an INT32 parameter in v1.18 (REAL32 before); it is read as a number either way.
PX4 acts on switch changes only, so the first frame already carries the intended switch positions.
"""
import math

STICKS = {'roll': 'RC_MAP_ROLL', 'pitch': 'RC_MAP_PITCH', 'throttle': 'RC_MAP_THROTTLE', 'yaw': 'RC_MAP_YAW'}
SWITCHES = {'arm': ('RC_MAP_ARM_SW', 'RC_ARMSWITCH_TH'), 'offboard': ('RC_MAP_OFFB_SW', 'RC_OFFB_TH')}
MODE_SWITCH = 'RC_MAP_FLTMODE'
FLTMODE = {'MANUAL': 0, 'ALTITUDE': 1, 'POSITION': 2, 'MISSION': 3, 'HOLD': 4, 'RETURN': 5, 'STABILIZED': 8}
CHANNELS = 18                     # RC_CHANNELS_OVERRIDE carries 18; channels 9-18 sent as 0 are ignored by PX4
SLOTS = 6


def required_params(params=None):
    """Parameter names to read back: maps and thresholds first, then the calibration of every mapped channel."""
    names = list(STICKS.values()) + [m for m, _ in SWITCHES.values()] + [t for _, t in SWITCHES.values()]
    names += [MODE_SWITCH] + [f'COM_FLTMODE{i}' for i in range(1, SLOTS + 1)]
    if params is not None:
        for name in list(STICKS.values()) + [m for m, _ in SWITCHES.values()] + [MODE_SWITCH]:
            channel = int(params.get(name, 0) or 0)
            if channel > 0:
                names += [f'RC{channel}_{k}' for k in ('MIN', 'TRIM', 'MAX', 'REV')]
    return names


def slot_value(slot):
    """Normalized channel value at the centre of a mode slot (the inverse of rc_update.cpp:577-586)."""
    value = ((slot - 1 + .5 - 1 / SLOTS) * 2.1 - 1 / SLOTS) / SLOTS - 1.05
    return max(-1., min(1., value))


class RcOutput:
    def __init__(self, params):
        self.channel = {}
        for name, param in list(STICKS.items()) + [(k, m) for k, (m, _) in SWITCHES.items()] + [('mode', MODE_SWITCH)]:
            channel = int(params.get(param, 0) or 0)
            if channel > 0:
                if not 1 <= channel <= CHANNELS:
                    raise ValueError(f'{param}={channel} outside 1..{CHANNELS}')
                self.channel[name] = channel
        missing = [n for n in STICKS if n not in self.channel]
        if missing:
            raise ValueError('sticks not mapped on the FC: ' + ', '.join(STICKS[n] for n in missing))
        if len(set(self.channel.values())) != len(self.channel):
            raise ValueError('two RC functions share one channel')
        self.calibration = {}
        for name, channel in self.channel.items():
            low, trim, high, rev = (float(params[f'RC{channel}_{k}']) for k in ('MIN', 'TRIM', 'MAX', 'REV'))
            if not (math.isfinite(low) and math.isfinite(high) and low < high and low <= trim <= high):
                raise ValueError(f'RC{channel} calibration invalid')
            if name == 'throttle' and ((rev < 0 and trim == high) or (rev >= 0 and trim == low)):
                trim = (low + high) / 2      # rc_update.cpp:182-187
            self.calibration[channel] = (low, trim, high, rev < 0)
        self.threshold = {k: float(params.get(t, .75)) for k, (_, t) in SWITCHES.items()}
        self.slots = {}
        for slot in range(1, SLOTS + 1):
            mode = int(params.get(f'COM_FLTMODE{slot}', -1))
            self.slots.setdefault(mode, slot)
        self.switch = {'arm': True, 'offboard': False}
        self.mode = None
        self.sticks = [0, 0, 0, 0]       # MANUAL_CONTROL convention: x pitch, y roll (-1000..1000), z throttle 0..1000, r yaw

    def pwm(self, channel, value):
        low, trim, high, reverse = self.calibration[channel]
        value = max(-1., min(1., -value if reverse else value))
        return int(round(trim + value * ((high - trim) if value >= 0 else (trim - low))))

    def set_mode(self, mode):
        """Put the flight-mode switch on the slot that holds this mode (COM_FLTMODEn)."""
        if 'mode' not in self.channel:
            raise ValueError('no flight-mode switch mapped (RC_MAP_FLTMODE)')
        if FLTMODE[mode] not in self.slots:
            raise ValueError(f'{mode} is on no flight-mode slot (COM_FLTMODE1..6)')
        self.mode = mode

    def switch_value(self, name, on):
        # rc_update: (0.5 * value + 0.5) > threshold is ON; a negative threshold inverts the switch.
        return (1. if on else -1.) * (-1. if self.threshold[name] < 0 else 1.)

    def values(self):
        """18 PWM values for RC_CHANNELS_OVERRIDE; unmapped channels 1-8 at 1500, 9-18 at 0 (ignored)."""
        out = [1500] * 8 + [0] * (CHANNELS - 8)
        x, y, z, r = self.sticks
        normalized = {'pitch': x / 1000, 'roll': y / 1000, 'throttle': z / 500 - 1, 'yaw': r / 1000}
        for name, value in normalized.items():
            out[self.channel[name] - 1] = self.pwm(self.channel[name], value)
        for name, on in self.switch.items():
            if name in self.channel:
                out[self.channel[name] - 1] = self.pwm(self.channel[name], self.switch_value(name, on))
        if 'mode' in self.channel and self.mode is not None:
            out[self.channel['mode'] - 1] = self.pwm(self.channel['mode'], slot_value(self.slots[FLTMODE[self.mode]]))
        return out
