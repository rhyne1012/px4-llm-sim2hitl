/* Atmospheric turbulence of every generated fast core (see fastcore/README.md, Turbulence).
 *
 * JSBSim 1.3.3 FGWinds::Turbulence (models/atmosphere/FGWinds.cpp) for its types ttMilspec (3) and ttTustin (4):
 * the scale lengths and intensities of MIL-F-8785C (below 1000 ft from the wind at 20 ft, above 2000 ft from the
 * probability-of-exceedance table, linear in between) and the filters of Yeager 1998 (NASA CR-1998-206937), in its
 * Tustin form of the Dryden filters (4) or in the first-order forms of MIL-STD-1797A it cites (3). The translational
 * part is added to the wind in NED; the rotational part is subtracted from the body rates the aerodynamics see
 * (FGAuxiliary::Run: vAeroPQR = vPQR - TurbPQR). Both are computed once per step from the state at its start and held
 * over the step, as JSBSim computes them once per frame. The units inside are JSBSim's (ft, ft/s); the held outputs are
 * SI.
 *
 * One difference from JSBSim, on purpose: the random numbers. JSBSim draws them from its generator
 * (simulation/randomseed). The core makes them from the vehicle's seed and a step counter (SplitMix64, Box-Muller), so
 * a run is reproduced from its parameters alone, the vehicles of a batch are independent, and k steps in one call
 * give the same numbers as k calls. The sequences are not JSBSim's; their statistics are checked against JSBSim and
 * against the formulas (fastcore/check.py, turbulence). */
#ifndef FASTCORE_TURBULENCE_H
#define FASTCORE_TURBULENCE_H

#include <math.h>
#include <stdint.h>
#include "fastcore.h"

/* The state of one vehicle, in this order (fastcore/gen.py TURB_STATES names them): the step counter, the wind azimuth
 * psiw, JSBSim's filter memories (xi_*_km1/km2, nu_*_km1/km2), then the held outputs: the turbulence wind in NED (m/s)
 * and the turbulence rates in body axes (rad/s). */
enum {
  FT_COUNTER, FT_PSIW,
  FT_XU1, FT_NU1, FT_XV1, FT_XV2, FT_NV1, FT_NV2, FT_XW1, FT_XW2, FT_NW1, FT_NW2, FT_XP1, FT_NP1, FT_XQ1, FT_XR1,
  FT_WIND_N, FT_WIND_E, FT_WIND_D, FT_P, FT_Q, FT_R,
  FT_NSTATE
};

/* atmosphere/turb-type: 0 ttNone and 1 ttStandard (not implemented in JSBSim: no turbulence), 3 ttMilspec,
 * 4 ttTustin. 2 (ttCulp) and anything else the core does not have. */
static inline int fc_turbulence_type_ok(double type)
{
  const int t = (int)type;
  return t == 0 || t == 1 || t == 3 || t == 4;
}

/* SplitMix64's finalizer (Steele, Lea, Flood 2014). */
static inline uint64_t fc_turb_mix(uint64_t z)
{
  z += 0x9E3779B97F4A7C15ull;
  z = (z ^ (z >> 30)) * 0xBF58476D1CE4E5B9ull;
  z = (z ^ (z >> 27)) * 0x94D049BB133111EBull;
  return z ^ (z >> 31);
}

/* Four standard normal numbers for step `counter` of the vehicle with `seed` (both whole numbers in doubles; the seed
 * is truncated toward zero): uniforms in (0, 1) from the mixed seed and the counter, two Box-Muller pairs. */
static inline void fc_turb_normals(double seed, double counter, double n[4])
{
  const uint64_t s = fc_turb_mix((uint64_t)(int64_t)seed), c = (uint64_t)counter;
  double uu[4];
  for (unsigned j = 0; j < 4; ++j)
    uu[j] = ((double)(fc_turb_mix(s ^ (c * 4u + j)) >> 11) + 0.5) * (1.0 / 9007199254740992.0);
  for (unsigned j = 0; j < 4; j += 2) {
    const double r = sqrt(-2.0 * log(uu[j])), a = 2.0 * FC_PI * uu[j + 1];
    n[j] = r * cos(a);
    n[j + 1] = r * sin(a);
  }
}

/* MIL-F-8785C Figure 7 (JSBSim's POE_Table): turbulence intensity (ft/s) against altitude (ft), one row per
 * probability-of-exceedance index 1-7. */
static const double FC_TURB_POE_ROWS[7] = {1, 2, 3, 4, 5, 6, 7};
static const double FC_TURB_POE_ALT[12] = {500, 1750, 3750, 7500, 15000, 25000, 35000, 45000, 55000, 65000, 75000, 80000};
static const double FC_TURB_POE[7 * 12] = {
  3.2,  2.2,  1.5,  0.0,  0.0,  0.0,  0.0,  0.0,  0.0,  0.0,  0.0,  0.0,
  4.2,  3.6,  3.3,  1.6,  0.0,  0.0,  0.0,  0.0,  0.0,  0.0,  0.0,  0.0,
  6.6,  6.9,  7.4,  6.7,  4.6,  2.7,  0.4,  0.0,  0.0,  0.0,  0.0,  0.0,
  8.6,  9.6, 10.6, 10.1,  8.0,  6.6,  5.0,  4.2,  2.7,  0.0,  0.0,  0.0,
 11.8, 13.0, 16.0, 15.1, 11.6,  9.7,  8.1,  8.2,  7.9,  4.9,  3.2,  2.1,
 15.6, 17.6, 23.0, 23.6, 22.1, 20.0, 16.0, 15.1, 12.1,  7.9,  6.2,  5.1,
 18.7, 21.5, 28.4, 30.2, 30.7, 31.0, 25.2, 23.1, 17.5, 10.7,  8.4,  7.2};

static inline double fc_sqr(double v) { return v * v; }

/* One step for one vehicle (FGWinds::Turbulence, then the psiw update of FGWinds::Run). t: the state above. type, w20
 * (atmosphere/turbulence/milspec/windspeed_at_20ft_AGL-fps), severity (atmosphere/turbulence/milspec/severity, an
 * integer in JSBSim) and seed (simulation/randomseed): the parameters. C: body to NED. uvw: body velocity relative to
 * the ground (m/s). wind: the mean wind in NED (m/s). h: altitude above sea level (ft; JSBSim uses in.AltitudeASL).
 * b_w: wingspan (ft). T_V: the step (s). The type must pass fc_turbulence_type_ok. */
static inline void fc_turbulence(double *t, double type, double w20, double severity, double seed, const double C[3][3],
                                 const double *uvw, const double *wind, double h, double b_w, double T_V)
{
  const int tt = (int)type, idx = (int)severity;
  int on = 0;
  if (tt == 3 || tt == 4) {
    /* airspeed relative to the air mass without the turbulence */
    const double wb[3] = {C[0][0] * wind[0] + C[1][0] * wind[1] + C[2][0] * wind[2],
                          C[0][1] * wind[0] + C[1][1] * wind[1] + C[2][1] * wind[2],
                          C[0][2] * wind[0] + C[1][2] * wind[1] + C[2][2] * wind[2]};
    const double V = sqrt(fc_sqr(uvw[0] - wb[0]) + fc_sqr(uvw[1] - wb[1]) + fc_sqr(uvw[2] - wb[2])) / FC_FT;
    on = idx != 0 && V != 0.0;
    if (on) {
      double L_u, L_w, sig_u, sig_w;
      if (b_w == 0.) b_w = 30.;
      if (h <= 10.) h = 10;
      if (h <= 1000) {
        L_u = h / pow(0.177 + 0.000823 * h, 1.2);
        L_w = h;
        sig_w = 0.1 * w20;
        sig_u = sig_w / pow(0.177 + 0.000823 * h, 0.4);
      } else if (h <= 2000) {
        L_u = L_w = 1000 + (h - 1000.) / 1000. * 750.;
        sig_u = sig_w = 0.1 * w20 + (h - 1000.) / 1000. *
                        (fc_table2(idx, h, FC_TURB_POE_ROWS, 7, FC_TURB_POE_ALT, 12, FC_TURB_POE) - 0.1 * w20);
      } else {
        L_u = L_w = 1750.;
        sig_u = sig_w = fc_table2(idx, h, FC_TURB_POE_ROWS, 7, FC_TURB_POE_ALT, 12, FC_TURB_POE);
      }
      const double sig_p = 1.9 / sqrt(L_w * b_w) * sig_w, L_p = sqrt(L_w * b_w) / 2.6;
      const double tau_u = L_u / V, tau_w = L_w / V, tau_p = L_p / V, tau_q = 4 * b_w / FC_PI / V,
                   tau_r = 3 * b_w / FC_PI / V;
      double nu[4];
      fc_turb_normals(seed, t[FT_COUNTER], nu);
      const double nu_u = nu[0], nu_v = nu[1], nu_w = nu[2], nu_p = nu[3];
      double xi_u, xi_v, xi_w, xi_p, xi_q, xi_r;
      if (tt == 4) {
        const double omega_w = V / L_w, omega_v = V / L_u,
                     C_BL = 1 / tau_u / tan(T_V / 2 / tau_u), C_BLp = 1 / tau_p / tan(T_V / 2 / tau_p),
                     C_BLq = 1 / tau_q / tan(T_V / 2 / tau_q), C_BLr = 1 / tau_r / tan(T_V / 2 / tau_r);
        xi_u = -(1 - C_BL * tau_u) / (1 + C_BL * tau_u) * t[FT_XU1]
             + sig_u * sqrt(2 * tau_u / T_V) / (1 + C_BL * tau_u) * (nu_u + t[FT_NU1]);
        xi_v = -2 * (fc_sqr(omega_v) - fc_sqr(C_BL)) / fc_sqr(omega_v + C_BL) * t[FT_XV1]
             - fc_sqr(omega_v - C_BL) / fc_sqr(omega_v + C_BL) * t[FT_XV2]
             + sig_u * sqrt(3 * omega_v / T_V) / fc_sqr(omega_v + C_BL) * (
                   (C_BL + omega_v / sqrt(3.)) * nu_v + 2 / sqrt(3.) * omega_v * t[FT_NV1]
                 + (omega_v / sqrt(3.) - C_BL) * t[FT_NV2]);
        xi_w = -2 * (fc_sqr(omega_w) - fc_sqr(C_BL)) / fc_sqr(omega_w + C_BL) * t[FT_XW1]
             - fc_sqr(omega_w - C_BL) / fc_sqr(omega_w + C_BL) * t[FT_XW2]
             + sig_w * sqrt(3 * omega_w / T_V) / fc_sqr(omega_w + C_BL) * (
                   (C_BL + omega_w / sqrt(3.)) * nu_w + 2 / sqrt(3.) * omega_w * t[FT_NW1]
                 + (omega_w / sqrt(3.) - C_BL) * t[FT_NW2]);
        xi_p = -(1 - C_BLp * tau_p) / (1 + C_BLp * tau_p) * t[FT_XP1]
             + sig_p * sqrt(2 * tau_p / T_V) / (1 + C_BLp * tau_p) * (nu_p + t[FT_NP1]);
        xi_q = -(1 - 4 * b_w * C_BLq / FC_PI / V) / (1 + 4 * b_w * C_BLq / FC_PI / V) * t[FT_XQ1]
             + C_BLq / V / (1 + 4 * b_w * C_BLq / FC_PI / V) * (xi_w - t[FT_XW1]);
        xi_r = -(1 - 3 * b_w * C_BLr / FC_PI / V) / (1 + 3 * b_w * C_BLr / FC_PI / V) * t[FT_XR1]
             + C_BLr / V / (1 + 3 * b_w * C_BLr / FC_PI / V) * (xi_v - t[FT_XV1]);
      } else {
        xi_u = (1 - T_V / tau_u) * t[FT_XU1] + sig_u * sqrt(2 * T_V / tau_u) * nu_u;
        xi_v = (1 - 2 * T_V / tau_u) * t[FT_XV1] + sig_u * sqrt(4 * T_V / tau_u) * nu_v;
        xi_w = (1 - 2 * T_V / tau_w) * t[FT_XW1] + sig_w * sqrt(4 * T_V / tau_w) * nu_w;
        xi_p = (1 - T_V / tau_p) * t[FT_XP1] + sig_p * sqrt(2 * T_V / tau_p) * nu_p;
        xi_q = (1 - T_V / tau_q) * t[FT_XQ1] + FC_PI / 4 / b_w * (xi_w - t[FT_XW1]);
        xi_r = (1 - T_V / tau_r) * t[FT_XR1] + FC_PI / 3 / b_w * (xi_v - t[FT_XV1]);
      }
      /* rotate by the wind azimuth; the rates from that frame into body axes (Tl2b) */
      const double cospsi = cos(t[FT_PSIW]), sinpsi = sin(t[FT_PSIW]);
      t[FT_WIND_N] = (cospsi * xi_u + sinpsi * xi_v) * FC_FT;
      t[FT_WIND_E] = (-sinpsi * xi_u + cospsi * xi_v) * FC_FT;
      t[FT_WIND_D] = xi_w * FC_FT;
      const double l[3] = {cospsi * xi_p + sinpsi * xi_q, -sinpsi * xi_p + cospsi * xi_q, xi_r};
      t[FT_P] = C[0][0] * l[0] + C[1][0] * l[1] + C[2][0] * l[2];
      t[FT_Q] = C[0][1] * l[0] + C[1][1] * l[1] + C[2][1] * l[2];
      t[FT_R] = C[0][2] * l[0] + C[1][2] * l[1] + C[2][2] * l[2];
      t[FT_XU1] = xi_u; t[FT_NU1] = nu_u;
      t[FT_XV2] = t[FT_XV1]; t[FT_XV1] = xi_v; t[FT_NV2] = t[FT_NV1]; t[FT_NV1] = nu_v;
      t[FT_XW2] = t[FT_XW1]; t[FT_XW1] = xi_w; t[FT_NW2] = t[FT_NW1]; t[FT_NW1] = nu_w;
      t[FT_XP1] = xi_p; t[FT_NP1] = nu_p;
      t[FT_XQ1] = xi_q;
      t[FT_XR1] = xi_r;
    }
  }
  if (!on) {   /* the filter memories stay as they are, as in JSBSim */
    t[FT_WIND_N] = t[FT_WIND_E] = t[FT_WIND_D] = 0.0;
    t[FT_P] = t[FT_Q] = t[FT_R] = 0.0;
  }
  /* FGWinds::Run: psiw follows the mean wind when its north part is not zero */
  if (wind[0] != 0.0) {
    double psi = atan2(wind[1], wind[0]);
    if (psi < 0) psi += 2 * FC_PI;
    t[FT_PSIW] = psi;
  }
  t[FT_COUNTER] += 1.0;
}

#endif
