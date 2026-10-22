/*
 * Academic License - for use in teaching, academic research, and meeting
 * course requirements at degree granting institutions only.  Not for
 * government, commercial, or other organizational use.
 *
 * File: SkySurfer_Core_private.h
 *
 * Code generated for Simulink model 'SkySurfer_Core'.
 *
 * Model version                  : 14.13
 * Simulink Coder version         : 26.2 (R2026b) 22-May-2026
 * C/C++ source code generated on : Thu Oct 22 23:54:04 2026
 *
 * Target selection: ert.tlc
 * Embedded hardware selection: Intel->x86-64 (Linux 64)
 * Code generation objectives: Unspecified
 * Validation result: Not run
 */

#ifndef SkySurfer_Core_private_h_
#define SkySurfer_Core_private_h_
#include <stdbool.h>
#include <stdint.h>
#include "complex_types.h"
#include "SkySurfer_Core.h"
#include "SkySurfer_Core_types.h"

/* Private macros used by the generated code to access rtModel */
#ifndef rtmSetFirstInitCond
#define rtmSetFirstInitCond(rtm, val)  ((rtm)->Timing.firstInitCondFlag = (val))
#endif

#ifndef rtmIsFirstInitCond
#define rtmIsFirstInitCond(rtm)        ((rtm)->Timing.firstInitCondFlag)
#endif

#ifndef rtmIsMajorTimeStep
#define rtmIsMajorTimeStep(rtm)        (((rtm)->Timing.simTimeStep) == MAJOR_TIME_STEP)
#endif

#ifndef rtmIsMinorTimeStep
#define rtmIsMinorTimeStep(rtm)        (((rtm)->Timing.simTimeStep) == MINOR_TIME_STEP)
#endif

#ifndef rtmSetTPtr
#define rtmSetTPtr(rtm, val)           ((rtm)->Timing.t = (val))
#endif

extern double rt_atan2d_snf(double u0, double u1);
extern double rt_powd_snf(double u0, double u1);
extern void rt_mrdivide_U1d1x3_U2d3x3_Yd1x3_snf(const double u0[3], const double
  u1[9], double y[3]);
extern double rt_urand_Upu32_Yd_f_pw_snf(uint32_t *u);
extern double rt_nrand_Upu32_Yd_f_pw_snf(uint32_t *u);
extern uint32_t plook_bincpa(double u, const double bp[], uint32_t maxIndex,
  double *fraction, uint32_t *prevIndex);
extern double intrp2d_la_pw(const uint32_t bpIndex[], const double frac[], const
  double table[], const uint32_t stride, const uint32_t maxIndex[]);
extern double look1_binlcpw(double u0, const double bp0[], const double table[],
  uint32_t maxIndex);
extern uint32_t plook_binx(double u, const double bp[], uint32_t maxIndex,
  double *fraction);
extern double intrp3d_l_pw(const uint32_t bpIndex[], const double frac[], const
  double table[], const uint32_t stride[]);
extern uint32_t plook_binc(double u, const double bp[], uint32_t maxIndex,
  double *fraction);
extern uint32_t binsearch_u32d_prevIdx(double u, const double bp[], uint32_t
  startIndex, uint32_t maxIndex);
extern uint32_t binsearch_u32d(double u, const double bp[], uint32_t startIndex,
  uint32_t maxIndex);
extern void SkySurfer_Core_Distanceintogusty_Init(double *rty_x,
  P_Distanceintogusty_SkySurfer_Core_T *localP,
  X_Distanceintogusty_SkySurfer_Core_T *localX);
extern void SkySurfer_Core_Distanceintogusty_Reset
  (P_Distanceintogusty_SkySurfer_Core_T *localP,
   X_Distanceintogusty_SkySurfer_Core_T *localX);
extern void SkySurfer_Core_Distanceintogusty_Deriv(double rtu_V, double rtp_d_m,
  DW_Distanceintogusty_SkySurfer_Core_T *localDW,
  P_Distanceintogusty_SkySurfer_Core_T *localP,
  X_Distanceintogusty_SkySurfer_Core_T *localX,
  XDot_Distanceintogusty_SkySurfer_Core_T *localXdot);
extern void SkySurfer_Core_Distanceintogusty_Disable
  (DW_Distanceintogusty_SkySurfer_Core_T *localDW);
extern void SkySurfer_Core_Distanceintogusty(RT_MODEL_SkySurfer_Core_T * const
  SkySurfer_Core_M, bool rtu_Enable, double *rty_x, double rtp_d_m,
  DW_Distanceintogusty_SkySurfer_Core_T *localDW,
  P_Distanceintogusty_SkySurfer_Core_T *localP,
  X_Distanceintogusty_SkySurfer_Core_T *localX,
  XDis_Distanceintogusty_SkySurfer_Core_T *localXdis);

/* private model entry point functions */
extern void SkySurfer_Core_derivatives(RT_MODEL_SkySurfer_Core_T *const
  SkySurfer_Core_M);

#endif                                 /* SkySurfer_Core_private_h_ */

/*
 * File trailer for generated code.
 *
 * [EOF]
 */
