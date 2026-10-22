/*
 * Academic License - for use in teaching, academic research, and meeting
 * course requirements at degree granting institutions only.  Not for
 * government, commercial, or other organizational use.
 *
 * File: SkySurfer_Core_types.h
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

#ifndef SkySurfer_Core_types_h_
#define SkySurfer_Core_types_h_
#ifndef DEFINED_TYPEDEF_FOR_struct_E6DgqKtWQeTvqZ51i6aBTH_
#define DEFINED_TYPEDEF_FOR_struct_E6DgqKtWQeTvqZ51i6aBTH_

typedef struct {
  double vd;
  double rollingFriction;
  double naturalFreq;
  double spring;
  double damper;
} struct_E6DgqKtWQeTvqZ51i6aBTH;

#endif

#ifndef DEFINED_TYPEDEF_FOR_struct_pj9o0ruoSIJrFqhg8Kr6MC_
#define DEFINED_TYPEDEF_FOR_struct_pj9o0ruoSIJrFqhg8Kr6MC_

typedef struct {
  struct_E6DgqKtWQeTvqZ51i6aBTH contact;
} struct_pj9o0ruoSIJrFqhg8Kr6MC;

#endif

/* Parameters for system: '<S140>/Distance into gust (y)' */
typedef struct P_Distanceintogusty_SkySurfer_Core_T_
  P_Distanceintogusty_SkySurfer_Core_T;

/* Parameters (default storage) */
typedef struct P_SkySurfer_Core_T_ P_SkySurfer_Core_T;

/* Forward declaration for rtModel */
typedef struct tag_RTM_SkySurfer_Core_T RT_MODEL_SkySurfer_Core_T;

#endif                                 /* SkySurfer_Core_types_h_ */

/*
 * File trailer for generated code.
 *
 * [EOF]
 */
