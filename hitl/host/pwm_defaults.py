"""Values PX4 v1.18 writes on its own when an output channel gets a function.

Two output drivers do it, the same way (PX4IO::update_params in src/drivers/px4io/px4io.cpp: the IO board's
PWM_MAIN on boards with one, only while disarmed; PWMOut::update_params in src/drivers/pwm_out/PWMOut.cpp: the FMU
outputs, PWM_MAIN on boards without an IO board and PWM_AUX on boards with one):
  - a channel whose function goes from unset (0) to a servo (201-215; 201-208 until v1.17) gets its disarmed value set to 1500; when none
    of the channels of its timer group was set, a timer rate of 400 Hz is also set to 50 Hz;
  - a channel whose function goes from unset to a motor (101-112) gets its minimum set to 1100 and maximum to 1900.
Both look at parameter changes at most once a second (uORB::SubscriptionInterval parameter_update 1_s): the first
function write is acted on at once, the next ones about 1 s later. The first cycle after a boot only notes which
channels are set.

Seen 2026-11-22 in a derived project (Cube Orange+, a deploy that set four channels from 0 to servos): px4io set the
release's disarmed values 1425/1450/1350 to 1500 after the deploy had written them, the deploy's check saw another
writer and rolled back. So the tools that write parameters (host/core.py param-deploy, deploy/flight_switch.py) write
function changes first, wait SETTLE_S after the last one, then write the release's values, and check them again after
another SETTLE_S.

Not modelled: the timer rate (it depends on the board's timer groups). A release that sets a timer of a group that
was unset to 400 Hz would see it set to 50 Hz; the readback after the reboot shows it.
"""
import re

WAIT_S = 3.0    # how long PX4 may take to write its own value after a function write
SETTLE_S = 2.5  # after the last function write PX4 acts on: before writing the release's values, and before checking
SERVO = range(201, 216)  # Servo 1..15 (PX4 v1.18 output_functions.yaml; 8 in v1.17)
MOTOR = range(101, 113)
FUNCTION = re.compile(r'(PWM_(?:MAIN|AUX))_FUNC(\d+)')


def automatic_values(name, old, new):
    """[(parameter, value)] PX4 sets on its own after the write name: old -> new (an output function from unset)."""
    m = FUNCTION.fullmatch(name)
    if not m or old is None or new is None or round(old) != 0:
        return []
    prefix, channel = m.groups()
    function = round(new)
    if function in SERVO:
        return [(f'{prefix}_DIS{channel}', 1500)]
    if function in MOTOR:
        return [(f'{prefix}_MIN{channel}', 1100), (f'{prefix}_MAX{channel}', 1900)]
    return []


def is_function(name):
    return FUNCTION.fullmatch(name) is not None
