/* Servo signal chain: between a flight controller's outputs and the vehicle's actuator commands.
 *
 * A servo samples its command once per PWM frame, a fixed phase into the frame, and holds it; a pure transport delay
 * follows. The mechanical part (lag, rate limit) is the vehicle's own JSBSim actuator. Motors do not go through it.
 *
 * One implementation for every user: simhost runs it at its 1 ms physics step, fast cores at their own step. Times are
 * whole multiples of the caller's step, so the same settings give the same chain at any step. At each tick the output
 * is the value held D ticks earlier; the hold takes a new command on the tick `phase` of each frame of `frame` ticks.
 *
 * Plain C99, header only. The state is an array of doubles so it can live inside a fast core's state vector:
 *   [0] tick within the PWM frame, [1] delay-line head, [2, 2+n) held values, then capacity x n delay-line values. */
#ifndef SERVO_CHAIN_H
#define SERVO_CHAIN_H

#include <math.h>

typedef struct {
  int frame, phase, delay; /* in ticks; frame 1, phase 0, delay 0 is the plain latch */
} sc_ticks;

static inline int sc_state_size(int n, int capacity) { return 2 + n + n * capacity; }

/* Convert period, phase and delay in seconds to ticks of dt. A period of 0 means no PWM hold. Returns 0, or -1 when a
 * time is not a whole multiple of dt, the phase is not inside the frame, or the delay exceeds the capacity. */
static inline int sc_ticks_from(double period_s, double phase_s, double delay_s, double dt, int capacity, sc_ticks *t)
{
  const double eps = 1e-9;
  double f = period_s / dt, ph = phase_s / dt, d = delay_s / dt;
  if (!(dt > 0.0) || period_s < 0.0 || phase_s < 0.0 || delay_s < 0.0) return -1;
  if (fabs(f - floor(f + 0.5)) > eps * (1.0 + f) || fabs(ph - floor(ph + 0.5)) > eps * (1.0 + ph) ||
      fabs(d - floor(d + 0.5)) > eps * (1.0 + d))
    return -1;
  t->frame = period_s > 0.0 ? (int)floor(f + 0.5) : 1;
  t->phase = (int)floor(ph + 0.5);
  t->delay = (int)floor(d + 0.5);
  if (t->frame < 1 || t->phase >= t->frame || t->delay > capacity) return -1;
  return 0;
}

/* Start at rest on the commands cmd[0..n): the hold and the delay line already hold them; the frame starts now. */
static inline void sc_reset(double *st, int n, int capacity, const double *cmd)
{
  st[0] = 0.0;
  st[1] = 0.0;
  for (int i = 0; i < n; ++i) {
    st[2 + i] = cmd[i];
    for (int k = 0; k < capacity; ++k) st[2 + n + k * n + i] = cmd[i];
  }
}

/* One tick: commands in, actuator commands out. */
static inline void sc_tick(double *st, int n, int capacity, const sc_ticks *t, const double *cmd, double *out)
{
  int tick = (int)st[0], head = (int)st[1];
  double *held = st + 2, *line = st + 2 + n;
  const int sample = tick == t->phase;
  (void)capacity;
  if (t->delay > 0 && head >= t->delay) head = 0; /* the delay was shortened */
  for (int i = 0; i < n; ++i) {
    const double h = sample ? cmd[i] : held[i];
    held[i] = h;
    if (t->delay > 0) {
      out[i] = line[head * n + i];
      line[head * n + i] = h;
    } else {
      out[i] = h;
    }
  }
  if (t->delay > 0) head = (head + 1) % t->delay;
  tick = tick + 1 >= t->frame ? 0 : tick + 1;
  st[0] = (double)tick;
  st[1] = (double)head;
}

#endif
