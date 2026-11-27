/* Shared physics of every generated fast core (see fastcore/README.md).
 *
 * The generator (fastcore/gen.py) writes the vehicle-specific part of a core -- aerodynamic functions, flight-control
 * components, mass, propulsion constants -- and includes this header for what every vehicle shares. Formulas follow
 * JSBSim 1.3.3 where the core reproduces JSBSim; the file and function named in each comment is the reference.
 * Units: JSBSim units (ft, slug, lbf, Rankine) inside the vehicle functions, SI at the core's interface. */
#ifndef FASTCORE_H
#define FASTCORE_H

#include <math.h>

/* Exact conversion factors. JSBSim's internal ft is 0.3048 m (FGJSBBase::fttom). */
#define FC_FT 0.3048                       /* m per ft */
#define FC_LBF 4.4482216152605             /* N per lbf */
#define FC_FTLBF (FC_LBF * FC_FT)          /* N m per ft lbf */
#define FC_SLUG (FC_LBF / FC_FT)           /* kg per slug */
#define FC_SLUGFT2 (FC_SLUG * FC_FT * FC_FT) /* kg m^2 per slug ft^2 */
#define FC_PI 3.14159265358979323846

static inline double fc_clip(double v, double lo, double hi) { return v < lo ? lo : (v > hi ? hi : v); }

/* FGFunction <quotient>: JSBSim returns HUGE_VAL for a zero denominator. */
static inline double fc_div(double a, double b) { return b != 0.0 ? a / b : HUGE_VAL; }

/* FGTable::GetValue(key) (math/FGTable.cpp): linear interpolation, the end values outside the range. The interval search
 * is binary; it finds the same interval as JSBSim's linear search (the first breakpoint >= key). */
static inline double fc_table1(double key, const double *xs, const double *ys, int n)
{
  if (key <= xs[0]) return ys[0];
  if (key >= xs[n - 1]) return ys[n - 1];
  int lo = 0, hi = n - 1; /* xs[lo] < key <= xs[hi] */
  while (hi - lo > 1) {
    int mid = (lo + hi) >> 1;
    if (xs[mid] < key) lo = mid; else hi = mid;
  }
  double f = (key - xs[lo]) / (xs[hi] - xs[lo]);
  return f * (ys[hi] - ys[lo]) + ys[lo];
}

/* FGTable::GetValue(rowKey, colKey) (math/FGTable.cpp), including its clamping of both factors to [0, 1].
 * data is row-major, nr rows by nc columns. */
static inline double fc_table2(double rk, double ck, const double *rows, int nr, const double *cols, int nc,
                               const double *data)
{
  if (nc == 1) return fc_table1(rk, rows, data, nr);
  int c = 1;
  while (cols[c] < ck && c < nc - 1) c++;
  double cf = fc_clip((ck - cols[c - 1]) / (cols[c] - cols[c - 1]), 0.0, 1.0);
  if (nr == 1) return cf * (data[c] - data[c - 1]) + data[c - 1];
  int r = 1;
  while (rows[r] < rk && r < nr - 1) r++;
  double rf = fc_clip((rk - rows[r - 1]) / (rows[r] - rows[r - 1]), 0.0, 1.0);
  double c1 = rf * data[r * nc + c - 1] + (1.0 - rf) * data[(r - 1) * nc + c - 1];
  double c2 = rf * data[r * nc + c] + (1.0 - rf) * data[(r - 1) * nc + c];
  return cf * (c2 - c1) + c1;
}

/* FGStandardAtmosphere (models/atmosphere/FGStandardAtmosphere.cpp), standard day, dry air, first layer only: valid for
 * geopotential altitudes below 36089.2388 ft (11 km), and below sea level with the same lapse rate.
 * h_ft is the geometric altitude above sea level. */
#define FC_KGTOSLUG 0.06852168
#define FC_RSTAR (8.31432 * FC_KGTOSLUG / (1.8 * FC_FT * FC_FT))
#define FC_MAIR (28.9645 * FC_KGTOSLUG / 1000.0)
#define FC_RDRY (FC_RSTAR / FC_MAIR)                     /* ft lbf / (slug R) */
#define FC_G0 (9.80665 / FC_FT)                          /* ft/s^2 */
#define FC_EARTH_RADIUS_ISA (6356766.0 / FC_FT)          /* ft */
#define FC_T_SL 518.67                                   /* R */
#define FC_P_SL 2116.228                                 /* psf */
#define FC_LAPSE0 ((389.97 - 518.67) / 36089.2388)       /* R/ft */

static inline void fc_atmosphere(double h_ft, double *T_R, double *P_psf, double *rho_slugft3)
{
  double hgp = h_ft * FC_EARTH_RADIUS_ISA / (FC_EARTH_RADIUS_ISA + h_ft);
  double T = FC_T_SL + FC_LAPSE0 * hgp;
  double P = FC_P_SL * pow(FC_T_SL / T, FC_G0 / (FC_RDRY * FC_LAPSE0));
  *T_R = T;
  *P_psf = P;
  *rho_slugft3 = P / (FC_RDRY * T);
}

/* Body-to-NED rotation matrix of a unit quaternion (scalar first). */
static inline void fc_quat_dcm(const double *q, double C[3][3])
{
  double q0 = q[0], q1 = q[1], q2 = q[2], q3 = q[3];
  C[0][0] = q0 * q0 + q1 * q1 - q2 * q2 - q3 * q3;
  C[0][1] = 2.0 * (q1 * q2 - q0 * q3);
  C[0][2] = 2.0 * (q1 * q3 + q0 * q2);
  C[1][0] = 2.0 * (q1 * q2 + q0 * q3);
  C[1][1] = q0 * q0 - q1 * q1 + q2 * q2 - q3 * q3;
  C[1][2] = 2.0 * (q2 * q3 - q0 * q1);
  C[2][0] = 2.0 * (q1 * q3 - q0 * q2);
  C[2][1] = 2.0 * (q2 * q3 + q0 * q1);
  C[2][2] = q0 * q0 - q1 * q1 - q2 * q2 + q3 * q3;
}

static inline void fc_quat_normalize(double *q)
{
  double n = sqrt(q[0] * q[0] + q[1] * q[1] + q[2] * q[2] + q[3] * q[3]);
  if (n > 0.0) { q[0] /= n; q[1] /= n; q[2] /= n; q[3] /= n; }
}

#endif
