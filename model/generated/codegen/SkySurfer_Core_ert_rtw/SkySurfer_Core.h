/*
 * Academic License - for use in teaching, academic research, and meeting
 * course requirements at degree granting institutions only.  Not for
 * government, commercial, or other organizational use.
 *
 * File: SkySurfer_Core.h
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

#ifndef SkySurfer_Core_h_
#define SkySurfer_Core_h_
#ifndef SkySurfer_Core_COMMON_INCLUDES_
#define SkySurfer_Core_COMMON_INCLUDES_
#include <stdbool.h>
#include <stdint.h>
#include "complex_types.h"
#include "rtw_continuous.h"
#include "rtw_solver.h"
#endif                                 /* SkySurfer_Core_COMMON_INCLUDES_ */

#include "SkySurfer_Core_types.h"
#include <string.h>
#include "rt_nonfinite.h"
#include "rtGetInf.h"
#include "rtGetNaN.h"
#include "rt_defines.h"

/* Macros for accessing real-time model data structure */
#ifndef rtmGetContStateDisabled
#define rtmGetContStateDisabled(rtm)   ((rtm)->contStateDisabled)
#endif

#ifndef rtmSetContStateDisabled
#define rtmSetContStateDisabled(rtm, val) ((rtm)->contStateDisabled = (val))
#endif

#ifndef rtmGetContStates
#define rtmGetContStates(rtm)          ((rtm)->contStates)
#endif

#ifndef rtmSetContStates
#define rtmSetContStates(rtm, val)     ((rtm)->contStates = (val))
#endif

#ifndef rtmGetContTimeOutputInconsistentWithStateAtMajorStepFlag
#define rtmGetContTimeOutputInconsistentWithStateAtMajorStepFlag(rtm) ((rtm)->CTOutputIncnstWithState)
#endif

#ifndef rtmSetContTimeOutputInconsistentWithStateAtMajorStepFlag
#define rtmSetContTimeOutputInconsistentWithStateAtMajorStepFlag(rtm, val) ((rtm)->CTOutputIncnstWithState = (val))
#endif

#ifndef rtmGetDerivCacheNeedsReset
#define rtmGetDerivCacheNeedsReset(rtm) ((rtm)->derivCacheNeedsReset)
#endif

#ifndef rtmSetDerivCacheNeedsReset
#define rtmSetDerivCacheNeedsReset(rtm, val) ((rtm)->derivCacheNeedsReset = (val))
#endif

#ifndef rtmGetIntgData
#define rtmGetIntgData(rtm)            ((rtm)->intgData)
#endif

#ifndef rtmSetIntgData
#define rtmSetIntgData(rtm, val)       ((rtm)->intgData = (val))
#endif

#ifndef rtmGetOdeF
#define rtmGetOdeF(rtm)                ((rtm)->odeF)
#endif

#ifndef rtmSetOdeF
#define rtmSetOdeF(rtm, val)           ((rtm)->odeF = (val))
#endif

#ifndef rtmGetOdeY
#define rtmGetOdeY(rtm)                ((rtm)->odeY)
#endif

#ifndef rtmSetOdeY
#define rtmSetOdeY(rtm, val)           ((rtm)->odeY = (val))
#endif

#ifndef rtmGetPeriodicContStateIndices
#define rtmGetPeriodicContStateIndices(rtm) ((rtm)->periodicContStateIndices)
#endif

#ifndef rtmSetPeriodicContStateIndices
#define rtmSetPeriodicContStateIndices(rtm, val) ((rtm)->periodicContStateIndices = (val))
#endif

#ifndef rtmGetPeriodicContStateRanges
#define rtmGetPeriodicContStateRanges(rtm) ((rtm)->periodicContStateRanges)
#endif

#ifndef rtmSetPeriodicContStateRanges
#define rtmSetPeriodicContStateRanges(rtm, val) ((rtm)->periodicContStateRanges = (val))
#endif

#ifndef rtmGetRootDWork
#define rtmGetRootDWork(rtm)           ((rtm)->dwork)
#endif

#ifndef rtmSetRootDWork
#define rtmSetRootDWork(rtm, val)      ((rtm)->dwork = (val))
#endif

#ifndef rtmGetZCCacheNeedsReset
#define rtmGetZCCacheNeedsReset(rtm)   ((rtm)->zCCacheNeedsReset)
#endif

#ifndef rtmSetZCCacheNeedsReset
#define rtmSetZCCacheNeedsReset(rtm, val) ((rtm)->zCCacheNeedsReset = (val))
#endif

#ifndef rtmGetdX
#define rtmGetdX(rtm)                  ((rtm)->derivs)
#endif

#ifndef rtmSetdX
#define rtmSetdX(rtm, val)             ((rtm)->derivs = (val))
#endif

#ifndef rtmGetErrorStatus
#define rtmGetErrorStatus(rtm)         ((rtm)->errorStatus)
#endif

#ifndef rtmSetErrorStatus
#define rtmSetErrorStatus(rtm, val)    ((rtm)->errorStatus = (val))
#endif

#ifndef rtmGetStopRequested
#define rtmGetStopRequested(rtm)       ((rtm)->Timing.stopRequestedFlag)
#endif

#ifndef rtmSetStopRequested
#define rtmSetStopRequested(rtm, val)  ((rtm)->Timing.stopRequestedFlag = (val))
#endif

#ifndef rtmGetStopRequestedPtr
#define rtmGetStopRequestedPtr(rtm)    (&((rtm)->Timing.stopRequestedFlag))
#endif

#ifndef rtmGetT
#define rtmGetT(rtm)                   (rtmGetTPtr((rtm))[0])
#endif

#ifndef rtmGetTPtr
#define rtmGetTPtr(rtm)                ((rtm)->Timing.t)
#endif

#ifndef rtmGetTStart
#define rtmGetTStart(rtm)              ((rtm)->Timing.tStart)
#endif

/* Block signals and states (default storage) for system '<S140>/Distance into gust (y)' */
typedef struct {
  bool Distanceintogusty_MODE;         /* '<S140>/Distance into gust (y)' */
} DW_Distanceintogusty_SkySurfer_Core_T;

/* Continuous states for system '<S140>/Distance into gust (y)' */
typedef struct {
  double DistanceintoGustxLimitedtogustlengthd_CSTATE;
               /* '<S146>/Distance into Gust (x) (Limited to gust length d) ' */
} X_Distanceintogusty_SkySurfer_Core_T;

/* State derivatives for system '<S140>/Distance into gust (y)' */
typedef struct {
  double DistanceintoGustxLimitedtogustlengthd_CSTATE;
               /* '<S146>/Distance into Gust (x) (Limited to gust length d) ' */
} XDot_Distanceintogusty_SkySurfer_Core_T;

/* State Disabled for system '<S140>/Distance into gust (y)' */
typedef struct {
  bool DistanceintoGustxLimitedtogustlengthd_CSTATE;
               /* '<S146>/Distance into Gust (x) (Limited to gust length d) ' */
} XDis_Distanceintogusty_SkySurfer_Core_T;

/* Block signals and states (default storage) for system '<Root>' */
typedef struct {
  DW_Distanceintogusty_SkySurfer_Core_T Distanceintogustz;/* '<S140>/Distance into gust (z)' */
  DW_Distanceintogusty_SkySurfer_Core_T Distanceintogusty;/* '<S140>/Distance into gust (y)' */
  double Reshape2[3];                  /* '<S18>/Reshape2' */
  double Selector2[9];                 /* '<S16>/Selector2' */
  double Product1[3];                  /* '<S142>/Product1' */
  double Windspeedatreferenceheight[3];
                                   /* '<S144>/Wind speed at reference height' */
  double Product[4];                   /* '<S160>/Product' */
  double Selector1[9];                 /* '<S16>/Selector1' */
  double Selector[9];                  /* '<S16>/Selector' */
  double Reshape[3];                   /* '<S16>/Reshape' */
  double Sum[3];                       /* '<S6>/Sum' */
  double TmpSignalConversionAtQ0123Inport1[4];/* '<S14>/qdot' */
  double w[2];                         /* '<S166>/w' */
  double w_c[2];                       /* '<S166>/w ' */
  double LwgV1[2];                     /* '<S166>/Lwg//V 1' */
  double w_b[2];                       /* '<S165>/w' */
  double w_j[2];                       /* '<S165>/w ' */
  double w1[2];                        /* '<S165>/w 1' */
  double w_k[2];                       /* '<S164>/w' */
  double w1_h[2];                      /* '<S164>/w1' */
  double w_m[2];                       /* '<S163>/w' */
  double UnaryMinus[2];                /* '<S163>/Unary Minus' */
  double w_jm[2];                      /* '<S162>/w' */
  double w_kq[2];                      /* '<S161>/w' */
  double sigma_w[2];                   /* '<S161>/sigma_w' */
  double Switch[3];                    /* '<S7>/Switch' */
  double Switch1[3];                   /* '<S7>/Switch1' */
  double NextOutput[4];                /* '<S160>/White Noise' */
  double Product2_DWORK4[9];           /* '<S16>/Product2' */
  double Gain;                         /* '<S13>/Gain' */
  double q0;                           /* '<S21>/q0' */
  double q1;                           /* '<S21>/q1' */
  double q2;                           /* '<S21>/q2' */
  double q3;                           /* '<S21>/q3' */
  double lnref_heightz0;               /* '<S144>/ln(ref_height//z0)' */
  double UnitConversion;               /* '<S149>/Unit Conversion' */
  double Sqrt;                         /* '<S11>/Sqrt' */
  double UnitConversion_m;             /* '<S187>/Unit Conversion' */
  double sigma_wg;                     /* '<S168>/sigma_wg ' */
  double PreLookUpIndexSearchprobofexceed_o2;
                        /* '<S167>/PreLook-Up Index Search  (prob of exceed)' */
  double UnitConversion_n;             /* '<S153>/Unit Conversion' */
  double RateLimiter;                  /* '<S3>/Rate Limiter' */
  double RateLimiter3;                 /* '<S3>/Rate Limiter3' */
  double RateLimiter1;                 /* '<S3>/Rate Limiter1' */
  double RateLimiter2;                 /* '<S3>/Rate Limiter2' */
  double Gain_g;                       /* '<S3>/Gain' */
  double Gain1;                        /* '<S3>/Gain1' */
  double Gain2;                        /* '<S3>/Gain2' */
  double Gain6;                        /* '<S3>/Gain6' */
  double Limit_THR;                    /* '<S3>/Limit_THR' */
  double sqrt_a;                       /* '<S166>/sqrt' */
  double w4;                           /* '<S161>/w4' */
  double u16;                          /* '<S161>/u^1//6' */
  double DistanceintoGustxLimitedtogustlengthd;
               /* '<S147>/Distance into Gust (x) (Limited to gust length d) ' */
  double DistanceintoGustxLimitedtogustlengthd_k;
               /* '<S146>/Distance into Gust (x) (Limited to gust length d) ' */
  double DistanceintoGustxLimitedtogustlengthd_l;
                /* '<S145>/Distance into Gust (x) (Limited to gust length d)' */
  double Merge;                        /* '<S42>/Merge' */
  double Merge_i;                      /* '<S46>/Merge' */
  double PrevY;                        /* '<S3>/Rate Limiter' */
  double LastMajorTime;                /* '<S3>/Rate Limiter' */
  double PrevY_p;                      /* '<S3>/Rate Limiter3' */
  double LastMajorTime_e;              /* '<S3>/Rate Limiter3' */
  double PrevY_d;                      /* '<S3>/Rate Limiter1' */
  double LastMajorTime_p;              /* '<S3>/Rate Limiter1' */
  double PrevY_m;                      /* '<S3>/Rate Limiter2' */
  double LastMajorTime_d;              /* '<S3>/Rate Limiter2' */
  uint32_t RandSeed[4];                /* '<S160>/White Noise' */
  uint32_t PreLookUpIndexSearchprobofexceed_o1;
                        /* '<S167>/PreLook-Up Index Search  (prob of exceed)' */
  uint32_t PreLookUpIndexSearchaltitude_DWORK1;
                              /* '<S167>/PreLook-Up Index Search  (altitude)' */
  uint32_t PreLookUpIndexSearchprobofexceed_DWORK1;
                        /* '<S167>/PreLook-Up Index Search  (prob of exceed)' */
  int8_t If_ActiveSubsystem;           /* '<S36>/If' */
  int8_t ifHeightMaxlowaltitudeelseifHeightMinisotropicaltitude_ActiveSubsystem;
  /* '<S156>/if Height < Max low altitude  elseif Height > Min isotropic altitude ' */
  int8_t
    ifHeightMaxlowaltitudeelseifHeightMinisotropicaltitude_ActiveSubsystem_l;
  /* '<S155>/if Height < Max low altitude  elseif Height > Min isotropic altitude ' */
  int8_t If1_ActiveSubsystem;          /* '<S41>/If1' */
  int8_t If_ActiveSubsystem_i;         /* '<S42>/If' */
  int8_t If_ActiveSubsystem_a;         /* '<S46>/If' */
  bool HiddenBuf_InsertedFor_Distanceintogusty_at_inport_1;/* '<S140>/Logical Operator1' */
  bool HiddenBuf_InsertedFor_Distanceintogustz_at_inport_1;/* '<S140>/Logical Operator3' */
  bool XYZe_DWORK1;                    /* '<S6>/XYZe' */
  bool UVWb_DWORK1;                    /* '<S6>/UVWb' */
  bool Q0123_DWORK1;                   /* '<S14>/Q0123' */
  bool PrevLimited;                    /* '<S3>/Rate Limiter' */
  bool PrevLimited_j;                  /* '<S3>/Rate Limiter3' */
  bool PrevLimited_j4;                 /* '<S3>/Rate Limiter1' */
  bool PrevLimited_n;                  /* '<S3>/Rate Limiter2' */
  bool Hwgws_MODE;                     /* '<S151>/Hwgw(s)' */
  bool Hvgws_MODE;                     /* '<S151>/Hvgw(s)' */
  bool Hugws_MODE;                     /* '<S151>/Hugw(s)' */
  bool Hrgw_MODE;                      /* '<S150>/Hrgw' */
  bool Hqgw_MODE;                      /* '<S150>/Hqgw' */
  bool Hpgw_MODE;                      /* '<S150>/Hpgw' */
  bool Distanceintogustx_MODE;         /* '<S140>/Distance into gust (x)' */
  bool Aerodynamic_MODE;               /* '<S5>/Aerodynamic' */
} DW_SkySurfer_Core_T;

/* Continuous states (default storage) */
typedef struct {
  double XYZe_CSTATE[3];               /* '<S6>/XYZe' */
  double UVWb_CSTATE[3];               /* '<S6>/UVWb' */
  double Q0123_CSTATE[4];              /* '<S14>/Q0123' */
  double PQR_CSTATE[3];                /* '<S6>/PQR' */
  double TransferFcn3_CSTATE;          /* '<S3>/Transfer Fcn3' */
  double TransferFcn_CSTATE;           /* '<S3>/Transfer Fcn' */
  double TransferFcn4_CSTATE;          /* '<S3>/Transfer Fcn4' */
  double TransferFcn1_CSTATE;          /* '<S3>/Transfer Fcn1' */
  double TransferFcn2_CSTATE;          /* '<S3>/Transfer Fcn2' */
  double wg_p1_CSTATE[2];              /* '<S166>/wg_p1' */
  double wg_p2_CSTATE[2];              /* '<S166>/wg_p2' */
  double vg_p1_CSTATE[2];              /* '<S165>/vg_p1' */
  double vgw_p2_CSTATE[2];             /* '<S165>/vgw_p2' */
  double ug_p_CSTATE[2];               /* '<S164>/ug_p' */
  double rgw_p_CSTATE[2];              /* '<S163>/rgw_p' */
  double qgw_p_CSTATE[2];              /* '<S162>/qgw_p' */
  double pgw_p_CSTATE[2];              /* '<S161>/pgw_p' */
  X_Distanceintogusty_SkySurfer_Core_T Distanceintogustz;/* '<S140>/Distance into gust (y)' */
  X_Distanceintogusty_SkySurfer_Core_T Distanceintogusty;/* '<S140>/Distance into gust (y)' */
  double DistanceintoGustxLimitedtogustlengthd_CSTATE_p;
                /* '<S145>/Distance into Gust (x) (Limited to gust length d)' */
} X_SkySurfer_Core_T;

/* State derivatives (default storage) */
typedef struct {
  double XYZe_CSTATE[3];               /* '<S6>/XYZe' */
  double UVWb_CSTATE[3];               /* '<S6>/UVWb' */
  double Q0123_CSTATE[4];              /* '<S14>/Q0123' */
  double PQR_CSTATE[3];                /* '<S6>/PQR' */
  double TransferFcn3_CSTATE;          /* '<S3>/Transfer Fcn3' */
  double TransferFcn_CSTATE;           /* '<S3>/Transfer Fcn' */
  double TransferFcn4_CSTATE;          /* '<S3>/Transfer Fcn4' */
  double TransferFcn1_CSTATE;          /* '<S3>/Transfer Fcn1' */
  double TransferFcn2_CSTATE;          /* '<S3>/Transfer Fcn2' */
  double wg_p1_CSTATE[2];              /* '<S166>/wg_p1' */
  double wg_p2_CSTATE[2];              /* '<S166>/wg_p2' */
  double vg_p1_CSTATE[2];              /* '<S165>/vg_p1' */
  double vgw_p2_CSTATE[2];             /* '<S165>/vgw_p2' */
  double ug_p_CSTATE[2];               /* '<S164>/ug_p' */
  double rgw_p_CSTATE[2];              /* '<S163>/rgw_p' */
  double qgw_p_CSTATE[2];              /* '<S162>/qgw_p' */
  double pgw_p_CSTATE[2];              /* '<S161>/pgw_p' */
  XDot_Distanceintogusty_SkySurfer_Core_T Distanceintogustz;/* '<S140>/Distance into gust (y)' */
  XDot_Distanceintogusty_SkySurfer_Core_T Distanceintogusty;/* '<S140>/Distance into gust (y)' */
  double DistanceintoGustxLimitedtogustlengthd_CSTATE_p;
                /* '<S145>/Distance into Gust (x) (Limited to gust length d)' */
} XDot_SkySurfer_Core_T;

/* State disabled  */
typedef struct {
  bool XYZe_CSTATE[3];                 /* '<S6>/XYZe' */
  bool UVWb_CSTATE[3];                 /* '<S6>/UVWb' */
  bool Q0123_CSTATE[4];                /* '<S14>/Q0123' */
  bool PQR_CSTATE[3];                  /* '<S6>/PQR' */
  bool TransferFcn3_CSTATE;            /* '<S3>/Transfer Fcn3' */
  bool TransferFcn_CSTATE;             /* '<S3>/Transfer Fcn' */
  bool TransferFcn4_CSTATE;            /* '<S3>/Transfer Fcn4' */
  bool TransferFcn1_CSTATE;            /* '<S3>/Transfer Fcn1' */
  bool TransferFcn2_CSTATE;            /* '<S3>/Transfer Fcn2' */
  bool wg_p1_CSTATE[2];                /* '<S166>/wg_p1' */
  bool wg_p2_CSTATE[2];                /* '<S166>/wg_p2' */
  bool vg_p1_CSTATE[2];                /* '<S165>/vg_p1' */
  bool vgw_p2_CSTATE[2];               /* '<S165>/vgw_p2' */
  bool ug_p_CSTATE[2];                 /* '<S164>/ug_p' */
  bool rgw_p_CSTATE[2];                /* '<S163>/rgw_p' */
  bool qgw_p_CSTATE[2];                /* '<S162>/qgw_p' */
  bool pgw_p_CSTATE[2];                /* '<S161>/pgw_p' */
  XDis_Distanceintogusty_SkySurfer_Core_T Distanceintogustz;/* '<S140>/Distance into gust (y)' */
  XDis_Distanceintogusty_SkySurfer_Core_T Distanceintogusty;/* '<S140>/Distance into gust (y)' */
  bool DistanceintoGustxLimitedtogustlengthd_CSTATE_p;
                /* '<S145>/Distance into Gust (x) (Limited to gust length d)' */
} XDis_SkySurfer_Core_T;

/* Invariant block signals (default storage) */
typedef struct {
  const double TmpSignalConversionAtForEachSubsystemInport2[3];
} ConstB_SkySurfer_Core_T;

#ifndef ODE4_INTG
#define ODE4_INTG

/* ODE4 Integration Data */
typedef struct {
  double *y;                           /* output */
  double *f[4];                        /* derivatives */
} ODE4_IntgData;

#endif

/* External inputs (root inport signals with default storage) */
typedef struct {
  double Controls[16];                 /* '<Root>/Controls' */
  double InitialConditions[7];         /* '<Root>/InitialConditions' */
  double Wind[4];                      /* '<Root>/Wind' */
} ExtU_SkySurfer_Core_T;

/* External outputs (root outports fed by signals with default storage) */
typedef struct {
  double CoreSnapshot[72];             /* '<Root>/CoreSnapshot' */
} ExtY_SkySurfer_Core_T;

/* Parameters for system: '<S140>/Distance into gust (y)' */
struct P_Distanceintogusty_SkySurfer_Core_T_ {
  double x_Y0;                         /* Expression: [0]
                                        * Referenced by: '<S146>/x'
                                        */
  double DistanceintoGustxLimitedtogustlengthd_IC;/* Expression: 0
                                                   * Referenced by: '<S146>/Distance into Gust (x) (Limited to gust length d) '
                                                   */
  double DistanceintoGustxLimitedtogustlengthd_LowerSat;/* Expression: 0
                                                         * Referenced by: '<S146>/Distance into Gust (x) (Limited to gust length d) '
                                                         */
};

/* Parameters (default storage) */
struct P_SkySurfer_Core_T_ {
  struct_pj9o0ruoSIJrFqhg8Kr6MC uavData;/* Variable: uavData
                                         * Referenced by:
                                         *   '<S192>/Damper'
                                         *   '<S192>/Spring Kp'
                                         *   '<S193>/friction coefficient'
                                         *   '<S193>/vd'
                                         */
  double Aeroelasticity_AIL[2];        /* Variable: Aeroelasticity_AIL
                                        * Referenced by:
                                        *   '<S7>/Aeroelasticity_AIL'
                                        *   '<S7>/Aeroelasticity_AIL1'
                                        */
  double Aeroelasticity_ELE[2];        /* Variable: Aeroelasticity_ELE
                                        * Referenced by: '<S7>/Aeroelasticity_ELE'
                                        */
  double Aeroelasticity_Gain_AIL[2];   /* Variable: Aeroelasticity_Gain_AIL
                                        * Referenced by:
                                        *   '<S7>/Aeroelasticity_AIL'
                                        *   '<S7>/Aeroelasticity_AIL1'
                                        */
  double Aeroelasticity_Gain_ELE[2];   /* Variable: Aeroelasticity_Gain_ELE
                                        * Referenced by: '<S7>/Aeroelasticity_ELE'
                                        */
  double Aeroelasticity_Gain_RUD[2];   /* Variable: Aeroelasticity_Gain_RUD
                                        * Referenced by: '<S7>/Aeroelasticity_RUD'
                                        */
  double Aeroelasticity_RUD[2];        /* Variable: Aeroelasticity_RUD
                                        * Referenced by: '<S7>/Aeroelasticity_RUD'
                                        */
  double AoA[6];                       /* Variable: AoA
                                        * Referenced by:
                                        *   '<S91>/CD_base'
                                        *   '<S91>/CD_dailL'
                                        *   '<S91>/CD_dailR'
                                        *   '<S91>/CD_dele'
                                        *   '<S91>/CD_dp'
                                        *   '<S91>/CD_dq'
                                        *   '<S91>/CD_dr'
                                        *   '<S91>/CD_drud'
                                        *   '<S93>/CL_base'
                                        *   '<S93>/CL_dailL'
                                        *   '<S93>/CL_dailR'
                                        *   '<S93>/CL_dele'
                                        *   '<S93>/CL_dp'
                                        *   '<S93>/CL_dq'
                                        *   '<S93>/CL_dr'
                                        *   '<S93>/CL_drud'
                                        *   '<S94>/CMl_base'
                                        *   '<S94>/CMl_dailL'
                                        *   '<S94>/CMl_dailR'
                                        *   '<S94>/CMl_dele'
                                        *   '<S94>/CMl_dp'
                                        *   '<S94>/CMl_dq'
                                        *   '<S94>/CMl_dr'
                                        *   '<S94>/CMl_drud'
                                        *   '<S95>/CMm_base'
                                        *   '<S95>/CMm_dailL'
                                        *   '<S95>/CMm_dailR'
                                        *   '<S95>/CMm_dele'
                                        *   '<S95>/CMm_dp'
                                        *   '<S95>/CMm_dq'
                                        *   '<S95>/CMm_dr'
                                        *   '<S95>/CMm_drud'
                                        *   '<S96>/CMn_base'
                                        *   '<S96>/CMn_dailL'
                                        *   '<S96>/CMn_dailR'
                                        *   '<S96>/CMn_dele'
                                        *   '<S96>/CMn_dp'
                                        *   '<S96>/CMn_dq'
                                        *   '<S96>/CMn_dr'
                                        *   '<S96>/CMn_drud'
                                        *   '<S97>/CS_base'
                                        *   '<S97>/CS_dailL'
                                        *   '<S97>/CS_dailR'
                                        *   '<S97>/CS_dele'
                                        *   '<S97>/CS_dp'
                                        *   '<S97>/CS_dq'
                                        *   '<S97>/CS_dr'
                                        *   '<S97>/CS_drud'
                                        */
  double AoS[3];                       /* Variable: AoS
                                        * Referenced by:
                                        *   '<S91>/CD_base'
                                        *   '<S91>/CD_dailL'
                                        *   '<S91>/CD_dailR'
                                        *   '<S91>/CD_dele'
                                        *   '<S91>/CD_dp'
                                        *   '<S91>/CD_dq'
                                        *   '<S91>/CD_dr'
                                        *   '<S91>/CD_drud'
                                        *   '<S93>/CL_base'
                                        *   '<S93>/CL_dailL'
                                        *   '<S93>/CL_dailR'
                                        *   '<S93>/CL_dele'
                                        *   '<S93>/CL_dp'
                                        *   '<S93>/CL_dq'
                                        *   '<S93>/CL_dr'
                                        *   '<S93>/CL_drud'
                                        *   '<S94>/CMl_base'
                                        *   '<S94>/CMl_dailL'
                                        *   '<S94>/CMl_dailR'
                                        *   '<S94>/CMl_dele'
                                        *   '<S94>/CMl_dp'
                                        *   '<S94>/CMl_dq'
                                        *   '<S94>/CMl_dr'
                                        *   '<S94>/CMl_drud'
                                        *   '<S95>/CMm_base'
                                        *   '<S95>/CMm_dailL'
                                        *   '<S95>/CMm_dailR'
                                        *   '<S95>/CMm_dele'
                                        *   '<S95>/CMm_dp'
                                        *   '<S95>/CMm_dq'
                                        *   '<S95>/CMm_dr'
                                        *   '<S95>/CMm_drud'
                                        *   '<S96>/CMn_base'
                                        *   '<S96>/CMn_dailL'
                                        *   '<S96>/CMn_dailR'
                                        *   '<S96>/CMn_dele'
                                        *   '<S96>/CMn_dp'
                                        *   '<S96>/CMn_dq'
                                        *   '<S96>/CMn_dr'
                                        *   '<S96>/CMn_drud'
                                        *   '<S97>/CS_base'
                                        *   '<S97>/CS_dailL'
                                        *   '<S97>/CS_dailR'
                                        *   '<S97>/CS_dele'
                                        *   '<S97>/CS_dp'
                                        *   '<S97>/CS_dq'
                                        *   '<S97>/CS_dr'
                                        *   '<S97>/CS_drud'
                                        */
  double CD_fix_AVL;                   /* Variable: CD_fix_AVL
                                        * Referenced by: '<S90>/Constant'
                                        */
  double CD_fix_VSP;                   /* Variable: CD_fix_VSP
                                        * Referenced by: '<S91>/Constant'
                                        */
  double CDd01[60];                    /* Variable: CDd01
                                        * Referenced by: '<S90>/CDd01'
                                        */
  double CDd02[60];                    /* Variable: CDd02
                                        * Referenced by: '<S90>/CDd02'
                                        */
  double CDd03[60];                    /* Variable: CDd03
                                        * Referenced by: '<S90>/CDd03'
                                        */
  double CDd04[60];                    /* Variable: CDd04
                                        * Referenced by: '<S90>/CDd04'
                                        */
  double CDp[60];                      /* Variable: CDp
                                        * Referenced by: '<S90>/CDp'
                                        */
  double CDq[60];                      /* Variable: CDq
                                        * Referenced by: '<S90>/CDq'
                                        */
  double CDr[60];                      /* Variable: CDr
                                        * Referenced by: '<S90>/CDr'
                                        */
  double CDtot[60];                    /* Variable: CDtot
                                        * Referenced by: '<S90>/CDtot'
                                        */
  double CG_m[3];                      /* Variable: CG_m
                                        * Referenced by:
                                        *   '<S7>/b2'
                                        *   '<S7>/b4'
                                        */
  double CLd01[60];                    /* Variable: CLd01
                                        * Referenced by: '<S92>/CLd01'
                                        */
  double CLd02[60];                    /* Variable: CLd02
                                        * Referenced by: '<S92>/CLd02'
                                        */
  double CLd03[60];                    /* Variable: CLd03
                                        * Referenced by: '<S92>/CLd03'
                                        */
  double CLd04[60];                    /* Variable: CLd04
                                        * Referenced by: '<S92>/CLd04'
                                        */
  double CLp[60];                      /* Variable: CLp
                                        * Referenced by: '<S92>/CLp'
                                        */
  double CLq[60];                      /* Variable: CLq
                                        * Referenced by: '<S92>/CLq'
                                        */
  double CLr[60];                      /* Variable: CLr
                                        * Referenced by: '<S92>/CLr'
                                        */
  double CLtot[60];                    /* Variable: CLtot
                                        * Referenced by: '<S92>/CLtot'
                                        */
  double CYd01[60];                    /* Variable: CYd01
                                        * Referenced by: '<S98>/CYd01'
                                        */
  double CYd02[60];                    /* Variable: CYd02
                                        * Referenced by: '<S98>/CYd02'
                                        */
  double CYd03[60];                    /* Variable: CYd03
                                        * Referenced by: '<S98>/CYd03'
                                        */
  double CYd04[60];                    /* Variable: CYd04
                                        * Referenced by: '<S98>/CYd04'
                                        */
  double CYp[60];                      /* Variable: CYp
                                        * Referenced by: '<S98>/CYp'
                                        */
  double CYq[60];                      /* Variable: CYq
                                        * Referenced by: '<S98>/CYq'
                                        */
  double CYr[60];                      /* Variable: CYr
                                        * Referenced by: '<S98>/CYr'
                                        */
  double CYtot[60];                    /* Variable: CYtot
                                        * Referenced by: '<S98>/CYtot'
                                        */
  double Cld01[60];                    /* Variable: Cld01
                                        * Referenced by: '<S99>/Cld01'
                                        */
  double Cld02[60];                    /* Variable: Cld02
                                        * Referenced by: '<S99>/Cld02'
                                        */
  double Cld03[60];                    /* Variable: Cld03
                                        * Referenced by: '<S99>/Cld03'
                                        */
  double Cld04[60];                    /* Variable: Cld04
                                        * Referenced by: '<S99>/Cld04'
                                        */
  double Clp[60];                      /* Variable: Clp
                                        * Referenced by: '<S99>/Clp'
                                        */
  double Clq[60];                      /* Variable: Clq
                                        * Referenced by: '<S99>/Clq'
                                        */
  double Clr[60];                      /* Variable: Clr
                                        * Referenced by: '<S99>/Clr'
                                        */
  double Cltot[60];                    /* Variable: Cltot
                                        * Referenced by: '<S99>/Cltot'
                                        */
  double Cmd01[60];                    /* Variable: Cmd01
                                        * Referenced by: '<S100>/Cmd01'
                                        */
  double Cmd02[60];                    /* Variable: Cmd02
                                        * Referenced by: '<S100>/Cmd02'
                                        */
  double Cmd03[60];                    /* Variable: Cmd03
                                        * Referenced by: '<S100>/Cmd03'
                                        */
  double Cmd04[60];                    /* Variable: Cmd04
                                        * Referenced by: '<S100>/Cmd04'
                                        */
  double Cmp[60];                      /* Variable: Cmp
                                        * Referenced by: '<S100>/Cmp'
                                        */
  double Cmq[60];                      /* Variable: Cmq
                                        * Referenced by: '<S100>/Cmq'
                                        */
  double Cmr[60];                      /* Variable: Cmr
                                        * Referenced by: '<S100>/Cmr'
                                        */
  double Cmtot[60];                    /* Variable: Cmtot
                                        * Referenced by: '<S100>/Cmtot'
                                        */
  double Cnd01[60];                    /* Variable: Cnd01
                                        * Referenced by: '<S101>/Cnd01'
                                        */
  double Cnd02[60];                    /* Variable: Cnd02
                                        * Referenced by: '<S101>/Cnd02'
                                        */
  double Cnd03[60];                    /* Variable: Cnd03
                                        * Referenced by: '<S101>/Cnd03'
                                        */
  double Cnd04[60];                    /* Variable: Cnd04
                                        * Referenced by: '<S101>/Cnd04'
                                        */
  double Cnp[60];                      /* Variable: Cnp
                                        * Referenced by: '<S101>/Cnp'
                                        */
  double Cnq[60];                      /* Variable: Cnq
                                        * Referenced by: '<S101>/Cnq'
                                        */
  double Cnr[60];                      /* Variable: Cnr
                                        * Referenced by: '<S101>/Cnr'
                                        */
  double Cntot[60];                    /* Variable: Cntot
                                        * Referenced by: '<S101>/Cntot'
                                        */
  double Inertia0[9];                  /* Variable: Inertia0
                                        * Referenced by: '<S4>/const2'
                                        */
  double Mach[2];                      /* Variable: Mach
                                        * Referenced by:
                                        *   '<S91>/CD_base'
                                        *   '<S91>/CD_dailL'
                                        *   '<S91>/CD_dailR'
                                        *   '<S91>/CD_dele'
                                        *   '<S91>/CD_dp'
                                        *   '<S91>/CD_dq'
                                        *   '<S91>/CD_dr'
                                        *   '<S91>/CD_drud'
                                        *   '<S93>/CL_base'
                                        *   '<S93>/CL_dailL'
                                        *   '<S93>/CL_dailR'
                                        *   '<S93>/CL_dele'
                                        *   '<S93>/CL_dp'
                                        *   '<S93>/CL_dq'
                                        *   '<S93>/CL_dr'
                                        *   '<S93>/CL_drud'
                                        *   '<S94>/CMl_base'
                                        *   '<S94>/CMl_dailL'
                                        *   '<S94>/CMl_dailR'
                                        *   '<S94>/CMl_dele'
                                        *   '<S94>/CMl_dp'
                                        *   '<S94>/CMl_dq'
                                        *   '<S94>/CMl_dr'
                                        *   '<S94>/CMl_drud'
                                        *   '<S95>/CMm_base'
                                        *   '<S95>/CMm_dailL'
                                        *   '<S95>/CMm_dailR'
                                        *   '<S95>/CMm_dele'
                                        *   '<S95>/CMm_dp'
                                        *   '<S95>/CMm_dq'
                                        *   '<S95>/CMm_dr'
                                        *   '<S95>/CMm_drud'
                                        *   '<S96>/CMn_base'
                                        *   '<S96>/CMn_dailL'
                                        *   '<S96>/CMn_dailR'
                                        *   '<S96>/CMn_dele'
                                        *   '<S96>/CMn_dp'
                                        *   '<S96>/CMn_dq'
                                        *   '<S96>/CMn_dr'
                                        *   '<S96>/CMn_drud'
                                        *   '<S97>/CS_base'
                                        *   '<S97>/CS_dailL'
                                        *   '<S97>/CS_dailR'
                                        *   '<S97>/CS_dele'
                                        *   '<S97>/CS_dp'
                                        *   '<S97>/CS_dq'
                                        *   '<S97>/CS_dr'
                                        *   '<S97>/CS_drud'
                                        */
  double Mass0;                        /* Variable: Mass0
                                        * Referenced by: '<S4>/const1'
                                        */
  double S;                            /* Variable: S
                                        * Referenced by:
                                        *   '<S7>/Aerodynamic Forces and Moments '
                                        *   '<S7>/Aerodynamic Forces and Moments 1'
                                        */
  double XREF_m[3];                    /* Variable: XREF_m
                                        * Referenced by:
                                        *   '<S7>/b1'
                                        *   '<S7>/b3'
                                        */
  double alpha_avl[6];                 /* Variable: alpha_avl
                                        * Referenced by:
                                        *   '<S90>/CDd01'
                                        *   '<S90>/CDd02'
                                        *   '<S90>/CDd03'
                                        *   '<S90>/CDd04'
                                        *   '<S90>/CDp'
                                        *   '<S90>/CDq'
                                        *   '<S90>/CDr'
                                        *   '<S90>/CDtot'
                                        *   '<S92>/CLd01'
                                        *   '<S92>/CLd02'
                                        *   '<S92>/CLd03'
                                        *   '<S92>/CLd04'
                                        *   '<S92>/CLp'
                                        *   '<S92>/CLq'
                                        *   '<S92>/CLr'
                                        *   '<S92>/CLtot'
                                        *   '<S98>/CYd01'
                                        *   '<S98>/CYd02'
                                        *   '<S98>/CYd03'
                                        *   '<S98>/CYd04'
                                        *   '<S98>/CYp'
                                        *   '<S98>/CYq'
                                        *   '<S98>/CYr'
                                        *   '<S98>/CYtot'
                                        *   '<S99>/Cld01'
                                        *   '<S99>/Cld02'
                                        *   '<S99>/Cld03'
                                        *   '<S99>/Cld04'
                                        *   '<S99>/Clp'
                                        *   '<S99>/Clq'
                                        *   '<S99>/Clr'
                                        *   '<S99>/Cltot'
                                        *   '<S100>/Cmd01'
                                        *   '<S100>/Cmd02'
                                        *   '<S100>/Cmd03'
                                        *   '<S100>/Cmd04'
                                        *   '<S100>/Cmp'
                                        *   '<S100>/Cmq'
                                        *   '<S100>/Cmr'
                                        *   '<S100>/Cmtot'
                                        *   '<S101>/Cnd01'
                                        *   '<S101>/Cnd02'
                                        *   '<S101>/Cnd03'
                                        *   '<S101>/Cnd04'
                                        *   '<S101>/Cnp'
                                        *   '<S101>/Cnq'
                                        *   '<S101>/Cnr'
                                        *   '<S101>/Cntot'
                                        */
  double b;                            /* Variable: b
                                        * Referenced by:
                                        *   '<S7>/Aerodynamic Forces and Moments '
                                        *   '<S7>/Aerodynamic Forces and Moments 1'
                                        *   '<S90>/Multiply'
                                        *   '<S90>/Multiply1'
                                        *   '<S91>/Multiply'
                                        *   '<S91>/Multiply1'
                                        *   '<S92>/Multiply'
                                        *   '<S92>/Multiply1'
                                        *   '<S93>/Multiply3'
                                        *   '<S93>/Multiply4'
                                        *   '<S94>/Multiply3'
                                        *   '<S94>/Multiply4'
                                        *   '<S95>/Multiply3'
                                        *   '<S95>/Multiply4'
                                        *   '<S96>/Multiply3'
                                        *   '<S96>/Multiply4'
                                        *   '<S97>/Multiply3'
                                        *   '<S97>/Multiply4'
                                        *   '<S98>/Multiply'
                                        *   '<S98>/Multiply1'
                                        *   '<S99>/Multiply'
                                        *   '<S99>/Multiply1'
                                        *   '<S100>/Multiply'
                                        *   '<S100>/Multiply1'
                                        *   '<S101>/Multiply'
                                        *   '<S101>/Multiply1'
                                        */
  double beta_avl[5];                  /* Variable: beta_avl
                                        * Referenced by:
                                        *   '<S90>/CDd01'
                                        *   '<S90>/CDd02'
                                        *   '<S90>/CDd03'
                                        *   '<S90>/CDd04'
                                        *   '<S90>/CDp'
                                        *   '<S90>/CDq'
                                        *   '<S90>/CDr'
                                        *   '<S90>/CDtot'
                                        *   '<S92>/CLd01'
                                        *   '<S92>/CLd02'
                                        *   '<S92>/CLd03'
                                        *   '<S92>/CLd04'
                                        *   '<S92>/CLp'
                                        *   '<S92>/CLq'
                                        *   '<S92>/CLr'
                                        *   '<S92>/CLtot'
                                        *   '<S98>/CYd01'
                                        *   '<S98>/CYd02'
                                        *   '<S98>/CYd03'
                                        *   '<S98>/CYd04'
                                        *   '<S98>/CYp'
                                        *   '<S98>/CYq'
                                        *   '<S98>/CYr'
                                        *   '<S98>/CYtot'
                                        *   '<S99>/Cld01'
                                        *   '<S99>/Cld02'
                                        *   '<S99>/Cld03'
                                        *   '<S99>/Cld04'
                                        *   '<S99>/Clp'
                                        *   '<S99>/Clq'
                                        *   '<S99>/Clr'
                                        *   '<S99>/Cltot'
                                        *   '<S100>/Cmd01'
                                        *   '<S100>/Cmd02'
                                        *   '<S100>/Cmd03'
                                        *   '<S100>/Cmd04'
                                        *   '<S100>/Cmp'
                                        *   '<S100>/Cmq'
                                        *   '<S100>/Cmr'
                                        *   '<S100>/Cmtot'
                                        *   '<S101>/Cnd01'
                                        *   '<S101>/Cnd02'
                                        *   '<S101>/Cnd03'
                                        *   '<S101>/Cnd04'
                                        *   '<S101>/Cnp'
                                        *   '<S101>/Cnq'
                                        *   '<S101>/Cnr'
                                        *   '<S101>/Cntot'
                                        */
  double cbar;                         /* Variable: cbar
                                        * Referenced by:
                                        *   '<S7>/Aerodynamic Forces and Moments '
                                        *   '<S7>/Aerodynamic Forces and Moments 1'
                                        *   '<S90>/Multiply2'
                                        *   '<S91>/Multiply2'
                                        *   '<S92>/Multiply2'
                                        *   '<S93>/Multiply5'
                                        *   '<S94>/Multiply5'
                                        *   '<S95>/Multiply5'
                                        *   '<S96>/Multiply5'
                                        *   '<S97>/Multiply5'
                                        *   '<S98>/Multiply2'
                                        *   '<S99>/Multiply2'
                                        *   '<S100>/Multiply2'
                                        *   '<S101>/Multiply2'
                                        */
  double del_z;                        /* Variable: del_z
                                        * Referenced by: '<S12>/Constant1'
                                        */
  double g;                            /* Variable: g
                                        * Referenced by: '<S12>/Gain1'
                                        */
  double mach_avl[2];                  /* Variable: mach_avl
                                        * Referenced by:
                                        *   '<S90>/CDd01'
                                        *   '<S90>/CDd02'
                                        *   '<S90>/CDd03'
                                        *   '<S90>/CDd04'
                                        *   '<S90>/CDp'
                                        *   '<S90>/CDq'
                                        *   '<S90>/CDr'
                                        *   '<S90>/CDtot'
                                        *   '<S92>/CLd01'
                                        *   '<S92>/CLd02'
                                        *   '<S92>/CLd03'
                                        *   '<S92>/CLd04'
                                        *   '<S92>/CLp'
                                        *   '<S92>/CLq'
                                        *   '<S92>/CLr'
                                        *   '<S92>/CLtot'
                                        *   '<S98>/CYd01'
                                        *   '<S98>/CYd02'
                                        *   '<S98>/CYd03'
                                        *   '<S98>/CYd04'
                                        *   '<S98>/CYp'
                                        *   '<S98>/CYq'
                                        *   '<S98>/CYr'
                                        *   '<S98>/CYtot'
                                        *   '<S99>/Cld01'
                                        *   '<S99>/Cld02'
                                        *   '<S99>/Cld03'
                                        *   '<S99>/Cld04'
                                        *   '<S99>/Clp'
                                        *   '<S99>/Clq'
                                        *   '<S99>/Clr'
                                        *   '<S99>/Cltot'
                                        *   '<S100>/Cmd01'
                                        *   '<S100>/Cmd02'
                                        *   '<S100>/Cmd03'
                                        *   '<S100>/Cmd04'
                                        *   '<S100>/Cmp'
                                        *   '<S100>/Cmq'
                                        *   '<S100>/Cmr'
                                        *   '<S100>/Cmtot'
                                        *   '<S101>/Cnd01'
                                        *   '<S101>/Cnd02'
                                        *   '<S101>/Cnd03'
                                        *   '<S101>/Cnd04'
                                        *   '<S101>/Cnp'
                                        *   '<S101>/Cnq'
                                        *   '<S101>/Cnr'
                                        *   '<S101>/Cntot'
                                        */
  double useAVL_VSP;                   /* Variable: useAVL_VSP
                                        * Referenced by:
                                        *   '<S7>/b7'
                                        *   '<S7>/b8'
                                        */
  double DrydenWindTurbulenceModelContinuousqr_L_high;
                 /* Mask Parameter: DrydenWindTurbulenceModelContinuousqr_L_high
                  * Referenced by: '<S186>/Medium//High Altitude'
                  */
  double DrydenWindTurbulenceModelContinuousqr_Seed[4];
                   /* Mask Parameter: DrydenWindTurbulenceModelContinuousqr_Seed
                    * Referenced by: '<S160>/White Noise'
                    */
  double DrydenWindTurbulenceModelContinuousqr_T_on;
                   /* Mask Parameter: DrydenWindTurbulenceModelContinuousqr_T_on
                    * Referenced by:
                    *   '<S150>/Constant1'
                    *   '<S150>/Constant2'
                    *   '<S150>/Constant3'
                    *   '<S151>/Constant'
                    */
  double WhiteNoise_Ts;                /* Mask Parameter: WhiteNoise_Ts
                                        * Referenced by: '<S160>/Constant1'
                                        */
  double DrydenWindTurbulenceModelContinuousqr_TurbProb;
               /* Mask Parameter: DrydenWindTurbulenceModelContinuousqr_TurbProb
                * Referenced by: '<S167>/Probability of  Exceedance'
                */
  double DrydenWindTurbulenceModelContinuousqr_W20;
                    /* Mask Parameter: DrydenWindTurbulenceModelContinuousqr_W20
                     * Referenced by: '<S141>/Windspeed at 20ft (6m)'
                     */
  double WindShearModel_W_20;          /* Mask Parameter: WindShearModel_W_20
                                        * Referenced by: '<S144>/Wind speed at reference height'
                                        */
  double WindShearModel_Wdeg;          /* Mask Parameter: WindShearModel_Wdeg
                                        * Referenced by: '<S144>/Wind Direction'
                                        */
  double DrydenWindTurbulenceModelContinuousqr_Wdeg;
                   /* Mask Parameter: DrydenWindTurbulenceModelContinuousqr_Wdeg
                    * Referenced by: '<S141>/Wind direction'
                    */
  double DrydenWindTurbulenceModelContinuousqr_Wingspan;
               /* Mask Parameter: DrydenWindTurbulenceModelContinuousqr_Wingspan
                * Referenced by: '<S141>/Wingspan'
                */
  double CompareToConstant_const;     /* Mask Parameter: CompareToConstant_const
                                       * Referenced by: '<S8>/Constant'
                                       */
  double Distanceintogustx_d_m;        /* Mask Parameter: Distanceintogustx_d_m
                                        * Referenced by: '<S145>/Distance into Gust (x) (Limited to gust length d)'
                                        */
  double Distanceintogusty_d_m;        /* Mask Parameter: Distanceintogusty_d_m
                                        * Referenced by: '<S140>/Distance into gust (y)'
                                        */
  double Distanceintogustz_d_m;        /* Mask Parameter: Distanceintogustz_d_m
                                        * Referenced by: '<S140>/Distance into gust (z)'
                                        */
  double DiscreteWindGustModelOn_d_m[3];
                                  /* Mask Parameter: DiscreteWindGustModelOn_d_m
                                   * Referenced by: '<S140>/pi//Gust length'
                                   */
  double WhiteNoise_pwr[4];            /* Mask Parameter: WhiteNoise_pwr
                                        * Referenced by: '<S160>/Constant'
                                        */
  double DiscreteWindGustModelOn_t_0;
                                  /* Mask Parameter: DiscreteWindGustModelOn_t_0
                                   * Referenced by: '<S140>/Gust start time'
                                   */
  double DCM2Ang_tolerance;            /* Mask Parameter: DCM2Ang_tolerance
                                        * Referenced by:
                                        *   '<S62>/Constant'
                                        *   '<S64>/Constant'
                                        */
  double DiscreteWindGustModelOn_v_m[3];
                                  /* Mask Parameter: DiscreteWindGustModelOn_v_m
                                   * Referenced by: '<S140>/Gust magnitude//2.0'
                                   */
  bool DiscreteWindGustModelOn_Gx; /* Mask Parameter: DiscreteWindGustModelOn_Gx
                                    * Referenced by: '<S140>/Constant'
                                    */
  bool DiscreteWindGustModelOn_Gy; /* Mask Parameter: DiscreteWindGustModelOn_Gy
                                    * Referenced by: '<S140>/Constant1'
                                    */
  bool DiscreteWindGustModelOn_Gz; /* Mask Parameter: DiscreteWindGustModelOn_Gz
                                    * Referenced by: '<S140>/Constant2'
                                    */
  uint8_t DCM2Ang_action;              /* Mask Parameter: DCM2Ang_action
                                        * Referenced by:
                                        *   '<S41>/Constant'
                                        *   '<S51>/Constant'
                                        *   '<S53>/Constant'
                                        */
  double Constant_Value;               /* Expression: 1
                                        * Referenced by: '<S47>/Constant'
                                        */
  double Constant_Value_i;             /* Expression: -1
                                        * Referenced by: '<S48>/Constant'
                                        */
  double Constant_Value_f;             /* Expression: 1
                                        * Referenced by: '<S43>/Constant'
                                        */
  double Constant_Value_k;             /* Expression: -1
                                        * Referenced by: '<S44>/Constant'
                                        */
  double Constant1_Value;              /* Expression: 0
                                        * Referenced by: '<S53>/Constant1'
                                        */
  double Constant1_Value_a;            /* Expression: 0
                                        * Referenced by: '<S51>/Constant1'
                                        */
  double Bias1_Bias[9];                /* Expression: -eye(3)
                                        * Referenced by: '<S54>/Bias1'
                                        */
  double Bias_Bias;                    /* Expression: -1
                                        * Referenced by: '<S55>/Bias'
                                        */
  double F_aero_Y0;                    /* Computed Parameter: F_aero_Y0
                                        * Referenced by: '<S7>/F_aero'
                                        */
  double M_aero_Y0;                    /* Computed Parameter: M_aero_Y0
                                        * Referenced by: '<S7>/M_aero'
                                        */
  double CD_base_tableData[36];        /* Expression: C_wgrp.CD_wgrp{1}
                                        * Referenced by: '<S91>/CD_base'
                                        */
  double CD_dp_tableData[36];          /* Expression: C_wgrp.CD_wgrp{4}
                                        * Referenced by: '<S91>/CD_dp'
                                        */
  double CD_dq_tableData[36];          /* Expression: C_wgrp.CD_wgrp{5}
                                        * Referenced by: '<S91>/CD_dq'
                                        */
  double CD_dr_tableData[36];          /* Expression: C_wgrp.CD_wgrp{6}
                                        * Referenced by: '<S91>/CD_dr'
                                        */
  double CD_dailR_tableData[36];       /* Expression: C_wgrp.CD_wgrp{9}
                                        * Referenced by: '<S91>/CD_dailR'
                                        */
  double Gain1_Gain;                   /* Expression: pi/180
                                        * Referenced by: '<S104>/Gain1'
                                        */
  double CD_dailL_tableData[36];       /* Expression: C_wgrp.CD_wgrp{10}
                                        * Referenced by: '<S91>/CD_dailL'
                                        */
  double Gain1_Gain_h;                 /* Expression: pi/180
                                        * Referenced by: '<S107>/Gain1'
                                        */
  double CD_dele_tableData[36];        /* Expression: C_wgrp.CD_wgrp{11}
                                        * Referenced by: '<S91>/CD_dele'
                                        */
  double Gain1_Gain_d;                 /* Expression: pi/180
                                        * Referenced by: '<S105>/Gain1'
                                        */
  double CD_drud_tableData[36];        /* Expression: C_wgrp.CD_wgrp{12}
                                        * Referenced by: '<S91>/CD_drud'
                                        */
  double Gain15_Gain;                  /* Expression: -1
                                        * Referenced by: '<S7>/Gain15'
                                        */
  double Gain1_Gain_dv;                /* Expression: pi/180
                                        * Referenced by: '<S106>/Gain1'
                                        */
  double CS_base_tableData[36];        /* Expression: C_wgrp.CS_wgrp{1}
                                        * Referenced by: '<S97>/CS_base'
                                        */
  double CS_dp_tableData[36];          /* Expression: C_wgrp.CS_wgrp{4}
                                        * Referenced by: '<S97>/CS_dp'
                                        */
  double CS_dq_tableData[36];          /* Expression: C_wgrp.CS_wgrp{5}
                                        * Referenced by: '<S97>/CS_dq'
                                        */
  double CS_dr_tableData[36];          /* Expression: C_wgrp.CS_wgrp{6}
                                        * Referenced by: '<S97>/CS_dr'
                                        */
  double CS_dailR_tableData[36];       /* Expression: C_wgrp.CS_wgrp{9}
                                        * Referenced by: '<S97>/CS_dailR'
                                        */
  double Gain1_Gain_o;                 /* Expression: pi/180
                                        * Referenced by: '<S124>/Gain1'
                                        */
  double CS_dailL_tableData[36];       /* Expression: C_wgrp.CS_wgrp{10}
                                        * Referenced by: '<S97>/CS_dailL'
                                        */
  double Gain1_Gain_b;                 /* Expression: pi/180
                                        * Referenced by: '<S127>/Gain1'
                                        */
  double CS_dele_tableData[36];        /* Expression: C_wgrp.CS_wgrp{11}
                                        * Referenced by: '<S97>/CS_dele'
                                        */
  double Gain1_Gain_j;                 /* Expression: pi/180
                                        * Referenced by: '<S125>/Gain1'
                                        */
  double CS_drud_tableData[36];        /* Expression: C_wgrp.CS_wgrp{12}
                                        * Referenced by: '<S97>/CS_drud'
                                        */
  double Gain10_Gain;                  /* Expression: -1
                                        * Referenced by: '<S7>/Gain10'
                                        */
  double Gain1_Gain_ju;                /* Expression: pi/180
                                        * Referenced by: '<S126>/Gain1'
                                        */
  double CL_base_tableData[36];        /* Expression: C_wgrp.CL_wgrp{1}
                                        * Referenced by: '<S93>/CL_base'
                                        */
  double CL_dp_tableData[36];          /* Expression: C_wgrp.CL_wgrp{4}
                                        * Referenced by: '<S93>/CL_dp'
                                        */
  double CL_dq_tableData[36];          /* Expression: C_wgrp.CL_wgrp{5}
                                        * Referenced by: '<S93>/CL_dq'
                                        */
  double CL_dr_tableData[36];          /* Expression: C_wgrp.CL_wgrp{6}
                                        * Referenced by: '<S93>/CL_dr'
                                        */
  double CL_dailR_tableData[36];       /* Expression: C_wgrp.CL_wgrp{9}
                                        * Referenced by: '<S93>/CL_dailR'
                                        */
  double Gain1_Gain_bf;                /* Expression: pi/180
                                        * Referenced by: '<S108>/Gain1'
                                        */
  double CL_dailL_tableData[36];       /* Expression: C_wgrp.CL_wgrp{10}
                                        * Referenced by: '<S93>/CL_dailL'
                                        */
  double Gain1_Gain_g;                 /* Expression: pi/180
                                        * Referenced by: '<S111>/Gain1'
                                        */
  double CL_dele_tableData[36];        /* Expression: C_wgrp.CL_wgrp{11}
                                        * Referenced by: '<S93>/CL_dele'
                                        */
  double Gain1_Gain_n;                 /* Expression: pi/180
                                        * Referenced by: '<S109>/Gain1'
                                        */
  double CL_drud_tableData[36];        /* Expression: C_wgrp.CL_wgrp{12}
                                        * Referenced by: '<S93>/CL_drud'
                                        */
  double Gain11_Gain;                  /* Expression: -1
                                        * Referenced by: '<S7>/Gain11'
                                        */
  double Gain1_Gain_p;                 /* Expression: pi/180
                                        * Referenced by: '<S110>/Gain1'
                                        */
  double CMl_base_tableData[36];       /* Expression: C_wgrp.CMl_wgrp{1}
                                        * Referenced by: '<S94>/CMl_base'
                                        */
  double CMl_dp_tableData[36];         /* Expression: C_wgrp.CMl_wgrp{4}
                                        * Referenced by: '<S94>/CMl_dp'
                                        */
  double CMl_dq_tableData[36];         /* Expression: C_wgrp.CMl_wgrp{5}
                                        * Referenced by: '<S94>/CMl_dq'
                                        */
  double CMl_dr_tableData[36];         /* Expression: C_wgrp.CMl_wgrp{6}
                                        * Referenced by: '<S94>/CMl_dr'
                                        */
  double CMl_dailR_tableData[36];      /* Expression: C_wgrp.CMl_wgrp{9}
                                        * Referenced by: '<S94>/CMl_dailR'
                                        */
  double Gain1_Gain_ox;                /* Expression: pi/180
                                        * Referenced by: '<S112>/Gain1'
                                        */
  double CMl_dailL_tableData[36];      /* Expression: C_wgrp.CMl_wgrp{10}
                                        * Referenced by: '<S94>/CMl_dailL'
                                        */
  double Gain1_Gain_l;                 /* Expression: pi/180
                                        * Referenced by: '<S115>/Gain1'
                                        */
  double CMl_dele_tableData[36];       /* Expression: C_wgrp.CMl_wgrp{11}
                                        * Referenced by: '<S94>/CMl_dele'
                                        */
  double Gain1_Gain_pp;                /* Expression: pi/180
                                        * Referenced by: '<S113>/Gain1'
                                        */
  double CMl_drud_tableData[36];       /* Expression: C_wgrp.CMl_wgrp{12}
                                        * Referenced by: '<S94>/CMl_drud'
                                        */
  double Gain4_Gain;                   /* Expression: -1
                                        * Referenced by: '<S7>/Gain4'
                                        */
  double Gain1_Gain_dh;                /* Expression: pi/180
                                        * Referenced by: '<S114>/Gain1'
                                        */
  double CMm_base_tableData[36];       /* Expression: C_wgrp.CMm_wgrp{1}
                                        * Referenced by: '<S95>/CMm_base'
                                        */
  double CMm_dp_tableData[36];         /* Expression: C_wgrp.CMm_wgrp{4}
                                        * Referenced by: '<S95>/CMm_dp'
                                        */
  double CMm_dq_tableData[36];         /* Expression: C_wgrp.CMm_wgrp{5}
                                        * Referenced by: '<S95>/CMm_dq'
                                        */
  double CMm_dr_tableData[36];         /* Expression: C_wgrp.CMm_wgrp{6}
                                        * Referenced by: '<S95>/CMm_dr'
                                        */
  double CMm_dailR_tableData[36];      /* Expression: C_wgrp.CMm_wgrp{9}
                                        * Referenced by: '<S95>/CMm_dailR'
                                        */
  double Gain1_Gain_db;                /* Expression: pi/180
                                        * Referenced by: '<S116>/Gain1'
                                        */
  double CMm_dailL_tableData[36];      /* Expression: C_wgrp.CMm_wgrp{10}
                                        * Referenced by: '<S95>/CMm_dailL'
                                        */
  double Gain1_Gain_ba;                /* Expression: pi/180
                                        * Referenced by: '<S119>/Gain1'
                                        */
  double CMm_dele_tableData[36];       /* Expression: C_wgrp.CMm_wgrp{11}
                                        * Referenced by: '<S95>/CMm_dele'
                                        */
  double Gain1_Gain_c;                 /* Expression: pi/180
                                        * Referenced by: '<S117>/Gain1'
                                        */
  double CMm_drud_tableData[36];       /* Expression: C_wgrp.CMm_wgrp{12}
                                        * Referenced by: '<S95>/CMm_drud'
                                        */
  double Gain9_Gain;                   /* Expression: -1
                                        * Referenced by: '<S7>/Gain9'
                                        */
  double Gain1_Gain_f;                 /* Expression: pi/180
                                        * Referenced by: '<S118>/Gain1'
                                        */
  double CMn_base_tableData[36];       /* Expression: C_wgrp.CMn_wgrp{1}
                                        * Referenced by: '<S96>/CMn_base'
                                        */
  double CMn_dp_tableData[36];         /* Expression: C_wgrp.CMn_wgrp{4}
                                        * Referenced by: '<S96>/CMn_dp'
                                        */
  double CMn_dq_tableData[36];         /* Expression: C_wgrp.CMn_wgrp{5}
                                        * Referenced by: '<S96>/CMn_dq'
                                        */
  double CMn_dr_tableData[36];         /* Expression: C_wgrp.CMn_wgrp{6}
                                        * Referenced by: '<S96>/CMn_dr'
                                        */
  double CMn_dailR_tableData[36];      /* Expression: C_wgrp.CMn_wgrp{9}
                                        * Referenced by: '<S96>/CMn_dailR'
                                        */
  double Gain1_Gain_e;                 /* Expression: pi/180
                                        * Referenced by: '<S120>/Gain1'
                                        */
  double CMn_dailL_tableData[36];      /* Expression: C_wgrp.CMn_wgrp{10}
                                        * Referenced by: '<S96>/CMn_dailL'
                                        */
  double Gain1_Gain_ps;                /* Expression: pi/180
                                        * Referenced by: '<S123>/Gain1'
                                        */
  double CMn_dele_tableData[36];       /* Expression: C_wgrp.CMn_wgrp{11}
                                        * Referenced by: '<S96>/CMn_dele'
                                        */
  double Gain1_Gain_os;                /* Expression: pi/180
                                        * Referenced by: '<S121>/Gain1'
                                        */
  double CMn_drud_tableData[36];       /* Expression: C_wgrp.CMn_wgrp{12}
                                        * Referenced by: '<S96>/CMn_drud'
                                        */
  double Gain12_Gain;                  /* Expression: -1
                                        * Referenced by: '<S7>/Gain12'
                                        */
  double Gain1_Gain_dq;                /* Expression: pi/180
                                        * Referenced by: '<S122>/Gain1'
                                        */
  double Gain1_Gain_i;                 /* Expression: pi/180
                                        * Referenced by: '<S102>/Gain1'
                                        */
  double Gain_Gain;                    /* Expression: 1
                                        * Referenced by: '<S99>/Gain'
                                        */
  double u2rhoV2_Gain;                 /* Expression: 1/2
                                        * Referenced by: '<S103>/1//2rhoV^2'
                                        */
  double Switch_Threshold;             /* Expression: 0.5
                                        * Referenced by: '<S7>/Switch'
                                        */
  double Switch1_Threshold;            /* Expression: 0.5
                                        * Referenced by: '<S7>/Switch1'
                                        */
  double x_Y0;                         /* Expression: [0]
                                        * Referenced by: '<S145>/x'
                                        */
  double DistanceintoGustxLimitedtogustlengthd_IC;/* Expression: 0
                                                   * Referenced by: '<S145>/Distance into Gust (x) (Limited to gust length d)'
                                                   */
  double DistanceintoGustxLimitedtogustlengthd_LowerSat;/* Expression: 0
                                                         * Referenced by: '<S145>/Distance into Gust (x) (Limited to gust length d)'
                                                         */
  double pgw_Y0;                       /* Expression: 0
                                        * Referenced by: '<S161>/pgw'
                                        */
  double pgw_p_IC;                     /* Expression: 0
                                        * Referenced by: '<S161>/pgw_p'
                                        */
  double Constant2_Value;              /* Expression: 1/6
                                        * Referenced by: '<S161>/Constant2'
                                        */
  double Constant3_Value;              /* Expression: pi/4
                                        * Referenced by: '<S161>/Constant3'
                                        */
  double Constant1_Value_m;            /* Expression: 1/3
                                        * Referenced by: '<S161>/Constant1'
                                        */
  double qgw_Y0;                       /* Expression: 0
                                        * Referenced by: '<S162>/qgw'
                                        */
  double qgw_p_IC;                     /* Expression: 0
                                        * Referenced by: '<S162>/qgw_p'
                                        */
  double pi4_Gain;                     /* Expression: pi/4
                                        * Referenced by: '<S162>/pi//4'
                                        */
  double rgw_Y0;                       /* Expression: 0
                                        * Referenced by: '<S163>/rgw'
                                        */
  double rgw_p_IC;                     /* Expression: 0
                                        * Referenced by: '<S163>/rgw_p'
                                        */
  double pi3_Gain;                     /* Expression: pi/3
                                        * Referenced by: '<S163>/pi//3'
                                        */
  double ugw_Y0;                       /* Expression: 0
                                        * Referenced by: '<S164>/ugw'
                                        */
  double upi_Gain;                     /* Expression: 2/pi
                                        * Referenced by: '<S164>/(2//pi)'
                                        */
  double ug_p_IC;                      /* Expression: 0
                                        * Referenced by: '<S164>/ug_p'
                                        */
  double vgw_Y0;                       /* Expression: 0
                                        * Referenced by: '<S165>/vgw'
                                        */
  double upi_Gain_c;                   /* Expression: 1/pi
                                        * Referenced by: '<S165>/(1//pi)'
                                        */
  double vg_p1_IC;                     /* Expression: 0
                                        * Referenced by: '<S165>/vg_p1'
                                        */
  double sqrt3_Gain;                   /* Expression: sqrt(3)
                                        * Referenced by: '<S165>/sqrt(3)'
                                        */
  double vgw_p2_IC;                    /* Expression: 0
                                        * Referenced by: '<S165>/vgw_p2'
                                        */
  double wgw_Y0;                       /* Expression: 0
                                        * Referenced by: '<S166>/wgw'
                                        */
  double upi_Gain_o;                   /* Expression: 1/pi
                                        * Referenced by: '<S166>/1//pi'
                                        */
  double wg_p1_IC;                     /* Expression: 0
                                        * Referenced by: '<S166>/wg_p1'
                                        */
  double Constant_Value_d;             /* Expression: 3
                                        * Referenced by: '<S166>/Constant'
                                        */
  double wg_p2_IC;                     /* Expression: 0
                                        * Referenced by: '<S166>/wg_p2'
                                        */
  double Gain_Gain_a;                  /* Expression: 1
                                        * Referenced by: '<S171>/Gain'
                                        */
  double max_height_low_Value;         /* Expression: max_height_low
                                        * Referenced by: '<S169>/max_height_low'
                                        */
  double min_height_high_Value;        /* Expression: min_height_high
                                        * Referenced by: '<S169>/min_height_high'
                                        */
  double Gain_Gain_f;                  /* Expression: 1
                                        * Referenced by: '<S179>/Gain'
                                        */
  double max_height_low_Value_b;       /* Expression: max_height_low
                                        * Referenced by: '<S177>/max_height_low'
                                        */
  double min_height_high_Value_a;      /* Expression: min_height_high
                                        * Referenced by: '<S177>/min_height_high'
                                        */
  double uftinf_UpperSat;              /* Expression: inf
                                        * Referenced by: '<S144>/3ft-->inf'
                                        */
  double uftinf_LowerSat;              /* Expression: 3
                                        * Referenced by: '<S144>/3ft-->inf'
                                        */
  double hz0_Gain;                     /* Expression: 1/z0
                                        * Referenced by: '<S144>/h//z0'
                                        */
  double rho_sealevelslugft32_Value;   /* Expression: 0
                                        * Referenced by: '<S13>/rho_sealevel (slug//ft^3)2'
                                        */
  double Gain_Gain_fa;                 /* Expression: -1
                                        * Referenced by: '<S13>/Gain'
                                        */
  double Gain1_Gain_m;                 /* Expression: pi/180
                                        * Referenced by: '<S202>/Gain1'
                                        */
  double u2_Gain;                      /* Expression: 0.5
                                        * Referenced by: '<S21>/1//2'
                                        */
  double PQR_IC;                       /* Expression: 0
                                        * Referenced by: '<S6>/PQR'
                                        */
  double Gain_Gain_e;                  /* Expression: 2
                                        * Referenced by: '<S26>/Gain'
                                        */
  double Gain_Gain_l;                  /* Expression: 2
                                        * Referenced by: '<S29>/Gain'
                                        */
  double Gain_Gain_c;                  /* Expression: 2
                                        * Referenced by: '<S24>/Gain'
                                        */
  double Gain_Gain_g;                  /* Expression: 2
                                        * Referenced by: '<S30>/Gain'
                                        */
  double Gain_Gain_j;                  /* Expression: 2
                                        * Referenced by: '<S25>/Gain'
                                        */
  double Gain_Gain_n;                  /* Expression: 2
                                        * Referenced by: '<S28>/Gain'
                                        */
  double Gain_Gain_js;                 /* Expression: 2
                                        * Referenced by: '<S68>/Gain'
                                        */
  double Gain_Gain_b;                  /* Expression: 2
                                        * Referenced by: '<S71>/Gain'
                                        */
  double Gain_Gain_la;                 /* Expression: 2
                                        * Referenced by: '<S66>/Gain'
                                        */
  double Gain_Gain_ah;                 /* Expression: 2
                                        * Referenced by: '<S72>/Gain'
                                        */
  double Gain_Gain_eu;                 /* Expression: 2
                                        * Referenced by: '<S67>/Gain'
                                        */
  double Gain_Gain_k;                  /* Expression: 2
                                        * Referenced by: '<S70>/Gain'
                                        */
  double Gain1_Gain_cp[3];             /* Expression: [1 1 -1]
                                        * Referenced by: '<S40>/Gain1'
                                        */
  double Gain2_Gain[2];                /* Expression: [1 1]
                                        * Referenced by: '<S40>/Gain2'
                                        */
  double Gain3_Gain[2];                /* Expression: [-1 1]
                                        * Referenced by: '<S40>/Gain3'
                                        */
  double Constant2_Value_k[9];         /* Expression: zeros(3)
                                        * Referenced by: '<S13>/Constant2'
                                        */
  double Constant4_Value;              /* Expression: 0
                                        * Referenced by: '<S12>/Constant4'
                                        */
  double TransferFcn3_A;               /* Computed Parameter: TransferFcn3_A
                                        * Referenced by: '<S3>/Transfer Fcn3'
                                        */
  double TransferFcn3_C;               /* Computed Parameter: TransferFcn3_C
                                        * Referenced by: '<S3>/Transfer Fcn3'
                                        */
  double kgf_Gain;                     /* Expression: 2.45
                                        * Referenced by: '<S12>/kgf'
                                        */
  double Gain_Gain_lj;                 /* Expression: -1
                                        * Referenced by: '<S12>/Gain'
                                        */
  double Constant_Value_k5;            /* Expression: 0
                                        * Referenced by: '<S12>/Constant'
                                        */
  double Wdeg1_Value;                  /* Expression: 0
                                        * Referenced by: '<S142>/Wdeg1'
                                        */
  double _Gain;                        /* Expression: -1
                                        * Referenced by: '<S142>/ '
                                        */
  double u_Value;                      /* Expression: 1.0
                                        * Referenced by: '<S140>/2'
                                        */
  double Negate_D_to_Alt_Gain;         /* Expression: -1
                                        * Referenced by: '<S11>/Negate_D_to_Alt'
                                        */
  double ref_heightz0_Value;           /* Expression: 20/z0
                                        * Referenced by: '<S144>/ref_height//z0'
                                        */
  double Wdeg1_Value_m;                /* Expression: 0
                                        * Referenced by: '<S144>/Wdeg1'
                                        */
  double Drydenairspeedfloor_UpperSat; /* Expression: inf
                                        * Referenced by: '<S131>/Dryden airspeed floor'
                                        */
  double Drydenairspeedfloor_LowerSat; /* Expression: 5
                                        * Referenced by: '<S131>/Dryden airspeed floor'
                                        */
  double LimitFunction10ftto1000ft_UpperSat;/* Expression: max_height_low
                                             * Referenced by: '<S185>/Limit Function 10ft to 1000ft'
                                             */
  double LimitFunction10ftto1000ft_LowerSat;/* Expression: 10
                                             * Referenced by: '<S185>/Limit Function 10ft to 1000ft'
                                             */
  double LimitHeighth1000ft_UpperSat;  /* Expression: max_height_low
                                        * Referenced by: '<S168>/Limit Height h<1000ft'
                                        */
  double LimitHeighth1000ft_LowerSat;  /* Expression: 0
                                        * Referenced by: '<S168>/Limit Height h<1000ft'
                                        */
  double sigma_wg_Gain;                /* Expression: 0.1
                                        * Referenced by: '<S168>/sigma_wg '
                                        */
  double PreLookUpIndexSearchaltitude_BreakpointsData[12];/* Expression: h_vec
                                                           * Referenced by: '<S167>/PreLook-Up Index Search  (altitude)'
                                                           */
  double PreLookUpIndexSearchprobofexceed_BreakpointsData[7];/* Expression: [1:7]
                                                              * Referenced by: '<S167>/PreLook-Up Index Search  (prob of exceed)'
                                                              */
  double MediumHighAltitudeIntensity_Table[84];/* Expression: sigma_vec'
                                                * Referenced by: '<S167>/Medium//High Altitude Intensity'
                                                */
  double WhiteNoise_Mean;              /* Expression: 0
                                        * Referenced by: '<S160>/White Noise'
                                        */
  double WhiteNoise_StdDev;            /* Computed Parameter: WhiteNoise_StdDev
                                        * Referenced by: '<S160>/White Noise'
                                        */
  double Lv_Gain;                      /* Expression: 1
                                        * Referenced by: '<S157>/Lv'
                                        */
  double Lw_Gain;                      /* Expression: 1
                                        * Referenced by: '<S157>/Lw'
                                        */
  double SeaLevelTemperature_Value;    /* Expression: T0
                                        * Referenced by: '<S136>/Sea Level  Temperature'
                                        */
  double Limitaltitudetotroposhere_UpperSat;/* Expression: h_trop
                                             * Referenced by: '<S136>/Limit  altitude  to troposhere'
                                             */
  double Limitaltitudetotroposhere_LowerSat;/* Expression: h0
                                             * Referenced by: '<S136>/Limit  altitude  to troposhere'
                                             */
  double LapseRate_Gain;               /* Expression: L
                                        * Referenced by: '<S136>/Lapse Rate'
                                        */
  double uT0_Gain;                     /* Expression: 1/T0
                                        * Referenced by: '<S136>/1//T0'
                                        */
  double Constant_Value_c;             /* Expression: g/(L*R)
                                        * Referenced by: '<S136>/Constant'
                                        */
  double rho0_Gain;                    /* Expression: rho0
                                        * Referenced by: '<S136>/rho0'
                                        */
  double AltitudeofTroposphere_Value;  /* Expression: h_trop
                                        * Referenced by: '<S136>/Altitude of Troposphere'
                                        */
  double LimitaltitudetoStratosphere_UpperSat;/* Expression: 0
                                               * Referenced by: '<S136>/Limit  altitude  to Stratosphere'
                                               */
  double LimitaltitudetoStratosphere_LowerSat;/* Expression: h_trop-h_strat
                                               * Referenced by: '<S136>/Limit  altitude  to Stratosphere'
                                               */
  double gR_Gain;                      /* Expression: g/R
                                        * Referenced by: '<S136>/g//R'
                                        */
  double gammaR_Gain;                  /* Expression: gamma*R
                                        * Referenced by: '<S136>/gamma*R'
                                        */
  double Gain_Gain_k3;                 /* Expression: 180/pi
                                        * Referenced by: '<S195>/Gain'
                                        */
  double Constant2_Value_h;            /* Expression: 0
                                        * Referenced by: '<S197>/Constant2'
                                        */
  double Switch_Threshold_j;           /* Expression: 0
                                        * Referenced by: '<S197>/Switch'
                                        */
  double Gain_Gain_d;                  /* Expression: 180/pi
                                        * Referenced by: '<S196>/Gain'
                                        */
  double Constant2_Value_m[3];         /* Expression: [0; 0; 0]
                                        * Referenced by: '<S131>/Constant2'
                                        */
  double TransferFcn_A;                /* Computed Parameter: TransferFcn_A
                                        * Referenced by: '<S3>/Transfer Fcn'
                                        */
  double TransferFcn_C;                /* Computed Parameter: TransferFcn_C
                                        * Referenced by: '<S3>/Transfer Fcn'
                                        */
  double RateLimiter_RisingLim;        /* Expression: 500
                                        * Referenced by: '<S3>/Rate Limiter'
                                        */
  double RateLimiter_FallingLim;       /* Expression: -500
                                        * Referenced by: '<S3>/Rate Limiter'
                                        */
  double Gain5_Gain;                   /* Expression: 1
                                        * Referenced by: '<S3>/Gain5'
                                        */
  double TransferFcn4_A;               /* Computed Parameter: TransferFcn4_A
                                        * Referenced by: '<S3>/Transfer Fcn4'
                                        */
  double TransferFcn4_C;               /* Computed Parameter: TransferFcn4_C
                                        * Referenced by: '<S3>/Transfer Fcn4'
                                        */
  double RateLimiter3_RisingLim;       /* Expression: 500
                                        * Referenced by: '<S3>/Rate Limiter3'
                                        */
  double RateLimiter3_FallingLim;      /* Expression: -500
                                        * Referenced by: '<S3>/Rate Limiter3'
                                        */
  double Gain3_Gain_m;                 /* Expression: -1
                                        * Referenced by: '<S3>/Gain3'
                                        */
  double TransferFcn1_A;               /* Computed Parameter: TransferFcn1_A
                                        * Referenced by: '<S3>/Transfer Fcn1'
                                        */
  double TransferFcn1_C;               /* Computed Parameter: TransferFcn1_C
                                        * Referenced by: '<S3>/Transfer Fcn1'
                                        */
  double RateLimiter1_RisingLim;       /* Expression: 500
                                        * Referenced by: '<S3>/Rate Limiter1'
                                        */
  double RateLimiter1_FallingLim;      /* Expression: -500
                                        * Referenced by: '<S3>/Rate Limiter1'
                                        */
  double Gain4_Gain_a;                 /* Expression: -1
                                        * Referenced by: '<S3>/Gain4'
                                        */
  double TransferFcn2_A;               /* Computed Parameter: TransferFcn2_A
                                        * Referenced by: '<S3>/Transfer Fcn2'
                                        */
  double TransferFcn2_C;               /* Computed Parameter: TransferFcn2_C
                                        * Referenced by: '<S3>/Transfer Fcn2'
                                        */
  double RateLimiter2_RisingLim;       /* Expression: 500
                                        * Referenced by: '<S3>/Rate Limiter2'
                                        */
  double RateLimiter2_FallingLim;      /* Expression: -500
                                        * Referenced by: '<S3>/Rate Limiter2'
                                        */
  double Gain8_Gain;                   /* Expression: 1
                                        * Referenced by: '<S3>/Gain8'
                                        */
  double Constant6_Value[3];           /* Expression: [0 0 0]
                                        * Referenced by: '<S5>/Constant6'
                                        */
  double Switch2_Threshold;            /* Expression: 5
                                        * Referenced by: '<S5>/Switch2'
                                        */
  double Constant5_Value;              /* Expression: 0
                                        * Referenced by: '<S12>/Constant5'
                                        */
  double Constant6_Value_o;            /* Expression: 0
                                        * Referenced by: '<S12>/Constant6'
                                        */
  double Constant5_Value_d[3];         /* Expression: [0 0 0]
                                        * Referenced by: '<S5>/Constant5'
                                        */
  double Switch1_Threshold_n;          /* Expression: 5
                                        * Referenced by: '<S5>/Switch1'
                                        */
  double Constant_Value_f0[3];         /* Expression: [0; 0; g]
                                        * Referenced by: '<S129>/Constant'
                                        */
  double Constant_Value_dw;            /* Expression: 0
                                        * Referenced by: '<S192>/Constant'
                                        */
  double Switch_Threshold_n;           /* Expression: 0
                                        * Referenced by: '<S192>/Switch'
                                        */
  double Saturation_UpperSat;          /* Expression: inf
                                        * Referenced by: '<S192>/Saturation'
                                        */
  double Saturation_LowerSat;          /* Expression: 0
                                        * Referenced by: '<S192>/Saturation'
                                        */
  double P0_Gain;                      /* Expression: P0
                                        * Referenced by: '<S136>/P0'
                                        */
  double Constant1_Value_f;            /* Expression: 0
                                        * Referenced by: '<S13>/Constant1'
                                        */
  double Limit_ELE_UpperSat;           /* Expression: 1
                                        * Referenced by: '<S3>/Limit_ELE'
                                        */
  double Limit_ELE_LowerSat;           /* Expression: -1
                                        * Referenced by: '<S3>/Limit_ELE'
                                        */
  double Gain_Gain_h;                  /* Expression: 27
                                        * Referenced by: '<S3>/Gain'
                                        */
  double Limit_RUD_UpperSat;           /* Expression: 1
                                        * Referenced by: '<S3>/Limit_RUD'
                                        */
  double Limit_RUD_LowerSat;           /* Expression: -1
                                        * Referenced by: '<S3>/Limit_RUD'
                                        */
  double Gain1_Gain_fv;                /* Expression: 35
                                        * Referenced by: '<S3>/Gain1'
                                        */
  double Limit_AIL_L_UpperSat;         /* Expression: 1
                                        * Referenced by: '<S3>/Limit_AIL_L'
                                        */
  double Limit_AIL_L_LowerSat;         /* Expression: -1
                                        * Referenced by: '<S3>/Limit_AIL_L'
                                        */
  double Gain2_Gain_f;                 /* Expression: 30
                                        * Referenced by: '<S3>/Gain2'
                                        */
  double Limit_AIL_R_UpperSat;         /* Expression: 1
                                        * Referenced by: '<S3>/Limit_AIL_R'
                                        */
  double Limit_AIL_R_LowerSat;         /* Expression: -1
                                        * Referenced by: '<S3>/Limit_AIL_R'
                                        */
  double Gain6_Gain;                   /* Expression: 30
                                        * Referenced by: '<S3>/Gain6'
                                        */
  double Limit_THR_UpperSat;           /* Expression: 1
                                        * Referenced by: '<S3>/Limit_THR'
                                        */
  double Limit_THR_LowerSat;           /* Expression: 0
                                        * Referenced by: '<S3>/Limit_THR'
                                        */
  double
    constBlockForifHeightMaxlowaltitudeelseifHeightMinisotropicaltitude_max_height_low_Value;/* Expression: max_height_low
                                                                      * Referenced by:
                                                                      */
  double
    constBlockForifHeightMaxlowaltitudeelseifHeightMinisotropicaltitude_min_height_high_Value;/* Expression: min_height_high
                                                                      * Referenced by:
                                                                      */
  double
    constBlockForifHeightMaxlowaltitudeelseifHeightMinisotropicaltitude_max_height_low_Value_a;/* Expression: max_height_low
                                                                      * Referenced by:
                                                                      */
  double
    constBlockForifHeightMaxlowaltitudeelseifHeightMinisotropicaltitude_min_height_high_Value_i;/* Expression: min_height_high
                                                                      * Referenced by:
                                                                      */
  uint32_t CD_base_maxIndex[3];        /* Computed Parameter: CD_base_maxIndex
                                        * Referenced by: '<S91>/CD_base'
                                        */
  uint32_t CD_base_dimSizes[3];        /* Computed Parameter: CD_base_dimSizes
                                        * Referenced by: '<S91>/CD_base'
                                        */
  uint32_t CD_dp_maxIndex[3];          /* Computed Parameter: CD_dp_maxIndex
                                        * Referenced by: '<S91>/CD_dp'
                                        */
  uint32_t CD_dp_dimSizes[3];          /* Computed Parameter: CD_dp_dimSizes
                                        * Referenced by: '<S91>/CD_dp'
                                        */
  uint32_t CD_dq_maxIndex[3];          /* Computed Parameter: CD_dq_maxIndex
                                        * Referenced by: '<S91>/CD_dq'
                                        */
  uint32_t CD_dq_dimSizes[3];          /* Computed Parameter: CD_dq_dimSizes
                                        * Referenced by: '<S91>/CD_dq'
                                        */
  uint32_t CD_dr_maxIndex[3];          /* Computed Parameter: CD_dr_maxIndex
                                        * Referenced by: '<S91>/CD_dr'
                                        */
  uint32_t CD_dr_dimSizes[3];          /* Computed Parameter: CD_dr_dimSizes
                                        * Referenced by: '<S91>/CD_dr'
                                        */
  uint32_t CD_dailR_maxIndex[3];       /* Computed Parameter: CD_dailR_maxIndex
                                        * Referenced by: '<S91>/CD_dailR'
                                        */
  uint32_t CD_dailR_dimSizes[3];       /* Computed Parameter: CD_dailR_dimSizes
                                        * Referenced by: '<S91>/CD_dailR'
                                        */
  uint32_t CD_dailL_maxIndex[3];       /* Computed Parameter: CD_dailL_maxIndex
                                        * Referenced by: '<S91>/CD_dailL'
                                        */
  uint32_t CD_dailL_dimSizes[3];       /* Computed Parameter: CD_dailL_dimSizes
                                        * Referenced by: '<S91>/CD_dailL'
                                        */
  uint32_t CD_dele_maxIndex[3];        /* Computed Parameter: CD_dele_maxIndex
                                        * Referenced by: '<S91>/CD_dele'
                                        */
  uint32_t CD_dele_dimSizes[3];        /* Computed Parameter: CD_dele_dimSizes
                                        * Referenced by: '<S91>/CD_dele'
                                        */
  uint32_t CD_drud_maxIndex[3];        /* Computed Parameter: CD_drud_maxIndex
                                        * Referenced by: '<S91>/CD_drud'
                                        */
  uint32_t CD_drud_dimSizes[3];        /* Computed Parameter: CD_drud_dimSizes
                                        * Referenced by: '<S91>/CD_drud'
                                        */
  uint32_t CS_base_maxIndex[3];        /* Computed Parameter: CS_base_maxIndex
                                        * Referenced by: '<S97>/CS_base'
                                        */
  uint32_t CS_base_dimSizes[3];        /* Computed Parameter: CS_base_dimSizes
                                        * Referenced by: '<S97>/CS_base'
                                        */
  uint32_t CS_dp_maxIndex[3];          /* Computed Parameter: CS_dp_maxIndex
                                        * Referenced by: '<S97>/CS_dp'
                                        */
  uint32_t CS_dp_dimSizes[3];          /* Computed Parameter: CS_dp_dimSizes
                                        * Referenced by: '<S97>/CS_dp'
                                        */
  uint32_t CS_dq_maxIndex[3];          /* Computed Parameter: CS_dq_maxIndex
                                        * Referenced by: '<S97>/CS_dq'
                                        */
  uint32_t CS_dq_dimSizes[3];          /* Computed Parameter: CS_dq_dimSizes
                                        * Referenced by: '<S97>/CS_dq'
                                        */
  uint32_t CS_dr_maxIndex[3];          /* Computed Parameter: CS_dr_maxIndex
                                        * Referenced by: '<S97>/CS_dr'
                                        */
  uint32_t CS_dr_dimSizes[3];          /* Computed Parameter: CS_dr_dimSizes
                                        * Referenced by: '<S97>/CS_dr'
                                        */
  uint32_t CS_dailR_maxIndex[3];       /* Computed Parameter: CS_dailR_maxIndex
                                        * Referenced by: '<S97>/CS_dailR'
                                        */
  uint32_t CS_dailR_dimSizes[3];       /* Computed Parameter: CS_dailR_dimSizes
                                        * Referenced by: '<S97>/CS_dailR'
                                        */
  uint32_t CS_dailL_maxIndex[3];       /* Computed Parameter: CS_dailL_maxIndex
                                        * Referenced by: '<S97>/CS_dailL'
                                        */
  uint32_t CS_dailL_dimSizes[3];       /* Computed Parameter: CS_dailL_dimSizes
                                        * Referenced by: '<S97>/CS_dailL'
                                        */
  uint32_t CS_dele_maxIndex[3];        /* Computed Parameter: CS_dele_maxIndex
                                        * Referenced by: '<S97>/CS_dele'
                                        */
  uint32_t CS_dele_dimSizes[3];        /* Computed Parameter: CS_dele_dimSizes
                                        * Referenced by: '<S97>/CS_dele'
                                        */
  uint32_t CS_drud_maxIndex[3];        /* Computed Parameter: CS_drud_maxIndex
                                        * Referenced by: '<S97>/CS_drud'
                                        */
  uint32_t CS_drud_dimSizes[3];        /* Computed Parameter: CS_drud_dimSizes
                                        * Referenced by: '<S97>/CS_drud'
                                        */
  uint32_t CL_base_maxIndex[3];        /* Computed Parameter: CL_base_maxIndex
                                        * Referenced by: '<S93>/CL_base'
                                        */
  uint32_t CL_base_dimSizes[3];        /* Computed Parameter: CL_base_dimSizes
                                        * Referenced by: '<S93>/CL_base'
                                        */
  uint32_t CL_dp_maxIndex[3];          /* Computed Parameter: CL_dp_maxIndex
                                        * Referenced by: '<S93>/CL_dp'
                                        */
  uint32_t CL_dp_dimSizes[3];          /* Computed Parameter: CL_dp_dimSizes
                                        * Referenced by: '<S93>/CL_dp'
                                        */
  uint32_t CL_dq_maxIndex[3];          /* Computed Parameter: CL_dq_maxIndex
                                        * Referenced by: '<S93>/CL_dq'
                                        */
  uint32_t CL_dq_dimSizes[3];          /* Computed Parameter: CL_dq_dimSizes
                                        * Referenced by: '<S93>/CL_dq'
                                        */
  uint32_t CL_dr_maxIndex[3];          /* Computed Parameter: CL_dr_maxIndex
                                        * Referenced by: '<S93>/CL_dr'
                                        */
  uint32_t CL_dr_dimSizes[3];          /* Computed Parameter: CL_dr_dimSizes
                                        * Referenced by: '<S93>/CL_dr'
                                        */
  uint32_t CL_dailR_maxIndex[3];       /* Computed Parameter: CL_dailR_maxIndex
                                        * Referenced by: '<S93>/CL_dailR'
                                        */
  uint32_t CL_dailR_dimSizes[3];       /* Computed Parameter: CL_dailR_dimSizes
                                        * Referenced by: '<S93>/CL_dailR'
                                        */
  uint32_t CL_dailL_maxIndex[3];       /* Computed Parameter: CL_dailL_maxIndex
                                        * Referenced by: '<S93>/CL_dailL'
                                        */
  uint32_t CL_dailL_dimSizes[3];       /* Computed Parameter: CL_dailL_dimSizes
                                        * Referenced by: '<S93>/CL_dailL'
                                        */
  uint32_t CL_dele_maxIndex[3];        /* Computed Parameter: CL_dele_maxIndex
                                        * Referenced by: '<S93>/CL_dele'
                                        */
  uint32_t CL_dele_dimSizes[3];        /* Computed Parameter: CL_dele_dimSizes
                                        * Referenced by: '<S93>/CL_dele'
                                        */
  uint32_t CL_drud_maxIndex[3];        /* Computed Parameter: CL_drud_maxIndex
                                        * Referenced by: '<S93>/CL_drud'
                                        */
  uint32_t CL_drud_dimSizes[3];        /* Computed Parameter: CL_drud_dimSizes
                                        * Referenced by: '<S93>/CL_drud'
                                        */
  uint32_t CMl_base_maxIndex[3];       /* Computed Parameter: CMl_base_maxIndex
                                        * Referenced by: '<S94>/CMl_base'
                                        */
  uint32_t CMl_base_dimSizes[3];       /* Computed Parameter: CMl_base_dimSizes
                                        * Referenced by: '<S94>/CMl_base'
                                        */
  uint32_t CMl_dp_maxIndex[3];         /* Computed Parameter: CMl_dp_maxIndex
                                        * Referenced by: '<S94>/CMl_dp'
                                        */
  uint32_t CMl_dp_dimSizes[3];         /* Computed Parameter: CMl_dp_dimSizes
                                        * Referenced by: '<S94>/CMl_dp'
                                        */
  uint32_t CMl_dq_maxIndex[3];         /* Computed Parameter: CMl_dq_maxIndex
                                        * Referenced by: '<S94>/CMl_dq'
                                        */
  uint32_t CMl_dq_dimSizes[3];         /* Computed Parameter: CMl_dq_dimSizes
                                        * Referenced by: '<S94>/CMl_dq'
                                        */
  uint32_t CMl_dr_maxIndex[3];         /* Computed Parameter: CMl_dr_maxIndex
                                        * Referenced by: '<S94>/CMl_dr'
                                        */
  uint32_t CMl_dr_dimSizes[3];         /* Computed Parameter: CMl_dr_dimSizes
                                        * Referenced by: '<S94>/CMl_dr'
                                        */
  uint32_t CMl_dailR_maxIndex[3];      /* Computed Parameter: CMl_dailR_maxIndex
                                        * Referenced by: '<S94>/CMl_dailR'
                                        */
  uint32_t CMl_dailR_dimSizes[3];      /* Computed Parameter: CMl_dailR_dimSizes
                                        * Referenced by: '<S94>/CMl_dailR'
                                        */
  uint32_t CMl_dailL_maxIndex[3];      /* Computed Parameter: CMl_dailL_maxIndex
                                        * Referenced by: '<S94>/CMl_dailL'
                                        */
  uint32_t CMl_dailL_dimSizes[3];      /* Computed Parameter: CMl_dailL_dimSizes
                                        * Referenced by: '<S94>/CMl_dailL'
                                        */
  uint32_t CMl_dele_maxIndex[3];       /* Computed Parameter: CMl_dele_maxIndex
                                        * Referenced by: '<S94>/CMl_dele'
                                        */
  uint32_t CMl_dele_dimSizes[3];       /* Computed Parameter: CMl_dele_dimSizes
                                        * Referenced by: '<S94>/CMl_dele'
                                        */
  uint32_t CMl_drud_maxIndex[3];       /* Computed Parameter: CMl_drud_maxIndex
                                        * Referenced by: '<S94>/CMl_drud'
                                        */
  uint32_t CMl_drud_dimSizes[3];       /* Computed Parameter: CMl_drud_dimSizes
                                        * Referenced by: '<S94>/CMl_drud'
                                        */
  uint32_t CMm_base_maxIndex[3];       /* Computed Parameter: CMm_base_maxIndex
                                        * Referenced by: '<S95>/CMm_base'
                                        */
  uint32_t CMm_base_dimSizes[3];       /* Computed Parameter: CMm_base_dimSizes
                                        * Referenced by: '<S95>/CMm_base'
                                        */
  uint32_t CMm_dp_maxIndex[3];         /* Computed Parameter: CMm_dp_maxIndex
                                        * Referenced by: '<S95>/CMm_dp'
                                        */
  uint32_t CMm_dp_dimSizes[3];         /* Computed Parameter: CMm_dp_dimSizes
                                        * Referenced by: '<S95>/CMm_dp'
                                        */
  uint32_t CMm_dq_maxIndex[3];         /* Computed Parameter: CMm_dq_maxIndex
                                        * Referenced by: '<S95>/CMm_dq'
                                        */
  uint32_t CMm_dq_dimSizes[3];         /* Computed Parameter: CMm_dq_dimSizes
                                        * Referenced by: '<S95>/CMm_dq'
                                        */
  uint32_t CMm_dr_maxIndex[3];         /* Computed Parameter: CMm_dr_maxIndex
                                        * Referenced by: '<S95>/CMm_dr'
                                        */
  uint32_t CMm_dr_dimSizes[3];         /* Computed Parameter: CMm_dr_dimSizes
                                        * Referenced by: '<S95>/CMm_dr'
                                        */
  uint32_t CMm_dailR_maxIndex[3];      /* Computed Parameter: CMm_dailR_maxIndex
                                        * Referenced by: '<S95>/CMm_dailR'
                                        */
  uint32_t CMm_dailR_dimSizes[3];      /* Computed Parameter: CMm_dailR_dimSizes
                                        * Referenced by: '<S95>/CMm_dailR'
                                        */
  uint32_t CMm_dailL_maxIndex[3];      /* Computed Parameter: CMm_dailL_maxIndex
                                        * Referenced by: '<S95>/CMm_dailL'
                                        */
  uint32_t CMm_dailL_dimSizes[3];      /* Computed Parameter: CMm_dailL_dimSizes
                                        * Referenced by: '<S95>/CMm_dailL'
                                        */
  uint32_t CMm_dele_maxIndex[3];       /* Computed Parameter: CMm_dele_maxIndex
                                        * Referenced by: '<S95>/CMm_dele'
                                        */
  uint32_t CMm_dele_dimSizes[3];       /* Computed Parameter: CMm_dele_dimSizes
                                        * Referenced by: '<S95>/CMm_dele'
                                        */
  uint32_t CMm_drud_maxIndex[3];       /* Computed Parameter: CMm_drud_maxIndex
                                        * Referenced by: '<S95>/CMm_drud'
                                        */
  uint32_t CMm_drud_dimSizes[3];       /* Computed Parameter: CMm_drud_dimSizes
                                        * Referenced by: '<S95>/CMm_drud'
                                        */
  uint32_t CMn_base_maxIndex[3];       /* Computed Parameter: CMn_base_maxIndex
                                        * Referenced by: '<S96>/CMn_base'
                                        */
  uint32_t CMn_base_dimSizes[3];       /* Computed Parameter: CMn_base_dimSizes
                                        * Referenced by: '<S96>/CMn_base'
                                        */
  uint32_t CMn_dp_maxIndex[3];         /* Computed Parameter: CMn_dp_maxIndex
                                        * Referenced by: '<S96>/CMn_dp'
                                        */
  uint32_t CMn_dp_dimSizes[3];         /* Computed Parameter: CMn_dp_dimSizes
                                        * Referenced by: '<S96>/CMn_dp'
                                        */
  uint32_t CMn_dq_maxIndex[3];         /* Computed Parameter: CMn_dq_maxIndex
                                        * Referenced by: '<S96>/CMn_dq'
                                        */
  uint32_t CMn_dq_dimSizes[3];         /* Computed Parameter: CMn_dq_dimSizes
                                        * Referenced by: '<S96>/CMn_dq'
                                        */
  uint32_t CMn_dr_maxIndex[3];         /* Computed Parameter: CMn_dr_maxIndex
                                        * Referenced by: '<S96>/CMn_dr'
                                        */
  uint32_t CMn_dr_dimSizes[3];         /* Computed Parameter: CMn_dr_dimSizes
                                        * Referenced by: '<S96>/CMn_dr'
                                        */
  uint32_t CMn_dailR_maxIndex[3];      /* Computed Parameter: CMn_dailR_maxIndex
                                        * Referenced by: '<S96>/CMn_dailR'
                                        */
  uint32_t CMn_dailR_dimSizes[3];      /* Computed Parameter: CMn_dailR_dimSizes
                                        * Referenced by: '<S96>/CMn_dailR'
                                        */
  uint32_t CMn_dailL_maxIndex[3];      /* Computed Parameter: CMn_dailL_maxIndex
                                        * Referenced by: '<S96>/CMn_dailL'
                                        */
  uint32_t CMn_dailL_dimSizes[3];      /* Computed Parameter: CMn_dailL_dimSizes
                                        * Referenced by: '<S96>/CMn_dailL'
                                        */
  uint32_t CMn_dele_maxIndex[3];       /* Computed Parameter: CMn_dele_maxIndex
                                        * Referenced by: '<S96>/CMn_dele'
                                        */
  uint32_t CMn_dele_dimSizes[3];       /* Computed Parameter: CMn_dele_dimSizes
                                        * Referenced by: '<S96>/CMn_dele'
                                        */
  uint32_t CMn_drud_maxIndex[3];       /* Computed Parameter: CMn_drud_maxIndex
                                        * Referenced by: '<S96>/CMn_drud'
                                        */
  uint32_t CMn_drud_dimSizes[3];       /* Computed Parameter: CMn_drud_dimSizes
                                        * Referenced by: '<S96>/CMn_drud'
                                        */
  uint32_t CDtot_maxIndex[3];          /* Computed Parameter: CDtot_maxIndex
                                        * Referenced by: '<S90>/CDtot'
                                        */
  uint32_t CDtot_dimSizes[3];          /* Computed Parameter: CDtot_dimSizes
                                        * Referenced by: '<S90>/CDtot'
                                        */
  uint32_t CDp_maxIndex[3];            /* Computed Parameter: CDp_maxIndex
                                        * Referenced by: '<S90>/CDp'
                                        */
  uint32_t CDp_dimSizes[3];            /* Computed Parameter: CDp_dimSizes
                                        * Referenced by: '<S90>/CDp'
                                        */
  uint32_t CDq_maxIndex[3];            /* Computed Parameter: CDq_maxIndex
                                        * Referenced by: '<S90>/CDq'
                                        */
  uint32_t CDq_dimSizes[3];            /* Computed Parameter: CDq_dimSizes
                                        * Referenced by: '<S90>/CDq'
                                        */
  uint32_t CDr_maxIndex[3];            /* Computed Parameter: CDr_maxIndex
                                        * Referenced by: '<S90>/CDr'
                                        */
  uint32_t CDr_dimSizes[3];            /* Computed Parameter: CDr_dimSizes
                                        * Referenced by: '<S90>/CDr'
                                        */
  uint32_t CDd01_maxIndex[3];          /* Computed Parameter: CDd01_maxIndex
                                        * Referenced by: '<S90>/CDd01'
                                        */
  uint32_t CDd01_dimSizes[3];          /* Computed Parameter: CDd01_dimSizes
                                        * Referenced by: '<S90>/CDd01'
                                        */
  uint32_t CDd02_maxIndex[3];          /* Computed Parameter: CDd02_maxIndex
                                        * Referenced by: '<S90>/CDd02'
                                        */
  uint32_t CDd02_dimSizes[3];          /* Computed Parameter: CDd02_dimSizes
                                        * Referenced by: '<S90>/CDd02'
                                        */
  uint32_t CDd03_maxIndex[3];          /* Computed Parameter: CDd03_maxIndex
                                        * Referenced by: '<S90>/CDd03'
                                        */
  uint32_t CDd03_dimSizes[3];          /* Computed Parameter: CDd03_dimSizes
                                        * Referenced by: '<S90>/CDd03'
                                        */
  uint32_t CDd04_maxIndex[3];          /* Computed Parameter: CDd04_maxIndex
                                        * Referenced by: '<S90>/CDd04'
                                        */
  uint32_t CDd04_dimSizes[3];          /* Computed Parameter: CDd04_dimSizes
                                        * Referenced by: '<S90>/CDd04'
                                        */
  uint32_t CYtot_maxIndex[3];          /* Computed Parameter: CYtot_maxIndex
                                        * Referenced by: '<S98>/CYtot'
                                        */
  uint32_t CYtot_dimSizes[3];          /* Computed Parameter: CYtot_dimSizes
                                        * Referenced by: '<S98>/CYtot'
                                        */
  uint32_t CYp_maxIndex[3];            /* Computed Parameter: CYp_maxIndex
                                        * Referenced by: '<S98>/CYp'
                                        */
  uint32_t CYp_dimSizes[3];            /* Computed Parameter: CYp_dimSizes
                                        * Referenced by: '<S98>/CYp'
                                        */
  uint32_t CYq_maxIndex[3];            /* Computed Parameter: CYq_maxIndex
                                        * Referenced by: '<S98>/CYq'
                                        */
  uint32_t CYq_dimSizes[3];            /* Computed Parameter: CYq_dimSizes
                                        * Referenced by: '<S98>/CYq'
                                        */
  uint32_t CYr_maxIndex[3];            /* Computed Parameter: CYr_maxIndex
                                        * Referenced by: '<S98>/CYr'
                                        */
  uint32_t CYr_dimSizes[3];            /* Computed Parameter: CYr_dimSizes
                                        * Referenced by: '<S98>/CYr'
                                        */
  uint32_t CYd01_maxIndex[3];          /* Computed Parameter: CYd01_maxIndex
                                        * Referenced by: '<S98>/CYd01'
                                        */
  uint32_t CYd01_dimSizes[3];          /* Computed Parameter: CYd01_dimSizes
                                        * Referenced by: '<S98>/CYd01'
                                        */
  uint32_t CYd02_maxIndex[3];          /* Computed Parameter: CYd02_maxIndex
                                        * Referenced by: '<S98>/CYd02'
                                        */
  uint32_t CYd02_dimSizes[3];          /* Computed Parameter: CYd02_dimSizes
                                        * Referenced by: '<S98>/CYd02'
                                        */
  uint32_t CYd03_maxIndex[3];          /* Computed Parameter: CYd03_maxIndex
                                        * Referenced by: '<S98>/CYd03'
                                        */
  uint32_t CYd03_dimSizes[3];          /* Computed Parameter: CYd03_dimSizes
                                        * Referenced by: '<S98>/CYd03'
                                        */
  uint32_t CYd04_maxIndex[3];          /* Computed Parameter: CYd04_maxIndex
                                        * Referenced by: '<S98>/CYd04'
                                        */
  uint32_t CYd04_dimSizes[3];          /* Computed Parameter: CYd04_dimSizes
                                        * Referenced by: '<S98>/CYd04'
                                        */
  uint32_t CLtot_maxIndex[3];          /* Computed Parameter: CLtot_maxIndex
                                        * Referenced by: '<S92>/CLtot'
                                        */
  uint32_t CLtot_dimSizes[3];          /* Computed Parameter: CLtot_dimSizes
                                        * Referenced by: '<S92>/CLtot'
                                        */
  uint32_t CLp_maxIndex[3];            /* Computed Parameter: CLp_maxIndex
                                        * Referenced by: '<S92>/CLp'
                                        */
  uint32_t CLp_dimSizes[3];            /* Computed Parameter: CLp_dimSizes
                                        * Referenced by: '<S92>/CLp'
                                        */
  uint32_t CLq_maxIndex[3];            /* Computed Parameter: CLq_maxIndex
                                        * Referenced by: '<S92>/CLq'
                                        */
  uint32_t CLq_dimSizes[3];            /* Computed Parameter: CLq_dimSizes
                                        * Referenced by: '<S92>/CLq'
                                        */
  uint32_t CLr_maxIndex[3];            /* Computed Parameter: CLr_maxIndex
                                        * Referenced by: '<S92>/CLr'
                                        */
  uint32_t CLr_dimSizes[3];            /* Computed Parameter: CLr_dimSizes
                                        * Referenced by: '<S92>/CLr'
                                        */
  uint32_t CLd01_maxIndex[3];          /* Computed Parameter: CLd01_maxIndex
                                        * Referenced by: '<S92>/CLd01'
                                        */
  uint32_t CLd01_dimSizes[3];          /* Computed Parameter: CLd01_dimSizes
                                        * Referenced by: '<S92>/CLd01'
                                        */
  uint32_t CLd02_maxIndex[3];          /* Computed Parameter: CLd02_maxIndex
                                        * Referenced by: '<S92>/CLd02'
                                        */
  uint32_t CLd02_dimSizes[3];          /* Computed Parameter: CLd02_dimSizes
                                        * Referenced by: '<S92>/CLd02'
                                        */
  uint32_t CLd03_maxIndex[3];          /* Computed Parameter: CLd03_maxIndex
                                        * Referenced by: '<S92>/CLd03'
                                        */
  uint32_t CLd03_dimSizes[3];          /* Computed Parameter: CLd03_dimSizes
                                        * Referenced by: '<S92>/CLd03'
                                        */
  uint32_t CLd04_maxIndex[3];          /* Computed Parameter: CLd04_maxIndex
                                        * Referenced by: '<S92>/CLd04'
                                        */
  uint32_t CLd04_dimSizes[3];          /* Computed Parameter: CLd04_dimSizes
                                        * Referenced by: '<S92>/CLd04'
                                        */
  uint32_t Cltot_maxIndex[3];          /* Computed Parameter: Cltot_maxIndex
                                        * Referenced by: '<S99>/Cltot'
                                        */
  uint32_t Cltot_dimSizes[3];          /* Computed Parameter: Cltot_dimSizes
                                        * Referenced by: '<S99>/Cltot'
                                        */
  uint32_t Clp_maxIndex[3];            /* Computed Parameter: Clp_maxIndex
                                        * Referenced by: '<S99>/Clp'
                                        */
  uint32_t Clp_dimSizes[3];            /* Computed Parameter: Clp_dimSizes
                                        * Referenced by: '<S99>/Clp'
                                        */
  uint32_t Clq_maxIndex[3];            /* Computed Parameter: Clq_maxIndex
                                        * Referenced by: '<S99>/Clq'
                                        */
  uint32_t Clq_dimSizes[3];            /* Computed Parameter: Clq_dimSizes
                                        * Referenced by: '<S99>/Clq'
                                        */
  uint32_t Clr_maxIndex[3];            /* Computed Parameter: Clr_maxIndex
                                        * Referenced by: '<S99>/Clr'
                                        */
  uint32_t Clr_dimSizes[3];            /* Computed Parameter: Clr_dimSizes
                                        * Referenced by: '<S99>/Clr'
                                        */
  uint32_t Cld01_maxIndex[3];          /* Computed Parameter: Cld01_maxIndex
                                        * Referenced by: '<S99>/Cld01'
                                        */
  uint32_t Cld01_dimSizes[3];          /* Computed Parameter: Cld01_dimSizes
                                        * Referenced by: '<S99>/Cld01'
                                        */
  uint32_t Cld02_maxIndex[3];          /* Computed Parameter: Cld02_maxIndex
                                        * Referenced by: '<S99>/Cld02'
                                        */
  uint32_t Cld02_dimSizes[3];          /* Computed Parameter: Cld02_dimSizes
                                        * Referenced by: '<S99>/Cld02'
                                        */
  uint32_t Cld03_maxIndex[3];          /* Computed Parameter: Cld03_maxIndex
                                        * Referenced by: '<S99>/Cld03'
                                        */
  uint32_t Cld03_dimSizes[3];          /* Computed Parameter: Cld03_dimSizes
                                        * Referenced by: '<S99>/Cld03'
                                        */
  uint32_t Cld04_maxIndex[3];          /* Computed Parameter: Cld04_maxIndex
                                        * Referenced by: '<S99>/Cld04'
                                        */
  uint32_t Cld04_dimSizes[3];          /* Computed Parameter: Cld04_dimSizes
                                        * Referenced by: '<S99>/Cld04'
                                        */
  uint32_t Cmtot_maxIndex[3];          /* Computed Parameter: Cmtot_maxIndex
                                        * Referenced by: '<S100>/Cmtot'
                                        */
  uint32_t Cmtot_dimSizes[3];          /* Computed Parameter: Cmtot_dimSizes
                                        * Referenced by: '<S100>/Cmtot'
                                        */
  uint32_t Cmp_maxIndex[3];            /* Computed Parameter: Cmp_maxIndex
                                        * Referenced by: '<S100>/Cmp'
                                        */
  uint32_t Cmp_dimSizes[3];            /* Computed Parameter: Cmp_dimSizes
                                        * Referenced by: '<S100>/Cmp'
                                        */
  uint32_t Cmq_maxIndex[3];            /* Computed Parameter: Cmq_maxIndex
                                        * Referenced by: '<S100>/Cmq'
                                        */
  uint32_t Cmq_dimSizes[3];            /* Computed Parameter: Cmq_dimSizes
                                        * Referenced by: '<S100>/Cmq'
                                        */
  uint32_t Cmr_maxIndex[3];            /* Computed Parameter: Cmr_maxIndex
                                        * Referenced by: '<S100>/Cmr'
                                        */
  uint32_t Cmr_dimSizes[3];            /* Computed Parameter: Cmr_dimSizes
                                        * Referenced by: '<S100>/Cmr'
                                        */
  uint32_t Cmd01_maxIndex[3];          /* Computed Parameter: Cmd01_maxIndex
                                        * Referenced by: '<S100>/Cmd01'
                                        */
  uint32_t Cmd01_dimSizes[3];          /* Computed Parameter: Cmd01_dimSizes
                                        * Referenced by: '<S100>/Cmd01'
                                        */
  uint32_t Cmd02_maxIndex[3];          /* Computed Parameter: Cmd02_maxIndex
                                        * Referenced by: '<S100>/Cmd02'
                                        */
  uint32_t Cmd02_dimSizes[3];          /* Computed Parameter: Cmd02_dimSizes
                                        * Referenced by: '<S100>/Cmd02'
                                        */
  uint32_t Cmd03_maxIndex[3];          /* Computed Parameter: Cmd03_maxIndex
                                        * Referenced by: '<S100>/Cmd03'
                                        */
  uint32_t Cmd03_dimSizes[3];          /* Computed Parameter: Cmd03_dimSizes
                                        * Referenced by: '<S100>/Cmd03'
                                        */
  uint32_t Cmd04_maxIndex[3];          /* Computed Parameter: Cmd04_maxIndex
                                        * Referenced by: '<S100>/Cmd04'
                                        */
  uint32_t Cmd04_dimSizes[3];          /* Computed Parameter: Cmd04_dimSizes
                                        * Referenced by: '<S100>/Cmd04'
                                        */
  uint32_t Cntot_maxIndex[3];          /* Computed Parameter: Cntot_maxIndex
                                        * Referenced by: '<S101>/Cntot'
                                        */
  uint32_t Cntot_dimSizes[3];          /* Computed Parameter: Cntot_dimSizes
                                        * Referenced by: '<S101>/Cntot'
                                        */
  uint32_t Cnp_maxIndex[3];            /* Computed Parameter: Cnp_maxIndex
                                        * Referenced by: '<S101>/Cnp'
                                        */
  uint32_t Cnp_dimSizes[3];            /* Computed Parameter: Cnp_dimSizes
                                        * Referenced by: '<S101>/Cnp'
                                        */
  uint32_t Cnq_maxIndex[3];            /* Computed Parameter: Cnq_maxIndex
                                        * Referenced by: '<S101>/Cnq'
                                        */
  uint32_t Cnq_dimSizes[3];            /* Computed Parameter: Cnq_dimSizes
                                        * Referenced by: '<S101>/Cnq'
                                        */
  uint32_t Cnr_maxIndex[3];            /* Computed Parameter: Cnr_maxIndex
                                        * Referenced by: '<S101>/Cnr'
                                        */
  uint32_t Cnr_dimSizes[3];            /* Computed Parameter: Cnr_dimSizes
                                        * Referenced by: '<S101>/Cnr'
                                        */
  uint32_t Cnd01_maxIndex[3];          /* Computed Parameter: Cnd01_maxIndex
                                        * Referenced by: '<S101>/Cnd01'
                                        */
  uint32_t Cnd01_dimSizes[3];          /* Computed Parameter: Cnd01_dimSizes
                                        * Referenced by: '<S101>/Cnd01'
                                        */
  uint32_t Cnd02_maxIndex[3];          /* Computed Parameter: Cnd02_maxIndex
                                        * Referenced by: '<S101>/Cnd02'
                                        */
  uint32_t Cnd02_dimSizes[3];          /* Computed Parameter: Cnd02_dimSizes
                                        * Referenced by: '<S101>/Cnd02'
                                        */
  uint32_t Cnd03_maxIndex[3];          /* Computed Parameter: Cnd03_maxIndex
                                        * Referenced by: '<S101>/Cnd03'
                                        */
  uint32_t Cnd03_dimSizes[3];          /* Computed Parameter: Cnd03_dimSizes
                                        * Referenced by: '<S101>/Cnd03'
                                        */
  uint32_t Cnd04_maxIndex[3];          /* Computed Parameter: Cnd04_maxIndex
                                        * Referenced by: '<S101>/Cnd04'
                                        */
  uint32_t Cnd04_dimSizes[3];          /* Computed Parameter: Cnd04_dimSizes
                                        * Referenced by: '<S101>/Cnd04'
                                        */
  uint32_t MediumHighAltitudeIntensity_maxIndex[2];
                     /* Computed Parameter: MediumHighAltitudeIntensity_maxIndex
                      * Referenced by: '<S167>/Medium//High Altitude Intensity'
                      */
  bool Assertion_Enabled;              /* Computed Parameter: Assertion_Enabled
                                        * Referenced by: '<S61>/Assertion'
                                        */
  bool Assertion_Enabled_h;           /* Computed Parameter: Assertion_Enabled_h
                                       * Referenced by: '<S59>/Assertion'
                                       */
  bool Assertion_Enabled_d;           /* Computed Parameter: Assertion_Enabled_d
                                       * Referenced by: '<S58>/Assertion'
                                       */
  bool Assertion_Enabled_p;           /* Computed Parameter: Assertion_Enabled_p
                                       * Referenced by: '<S56>/Assertion'
                                       */
  P_Distanceintogusty_SkySurfer_Core_T Distanceintogustz;/* '<S140>/Distance into gust (z)' */
  P_Distanceintogusty_SkySurfer_Core_T Distanceintogusty;/* '<S140>/Distance into gust (y)' */
};

/* Real-time Model Data Structure */
struct tag_RTM_SkySurfer_Core_T {
  const char *errorStatus;
  RTWSolverInfo solverInfo;
  X_SkySurfer_Core_T *contStates;
  int *periodicContStateIndices;
  double *periodicContStateRanges;
  double *derivs;
  XDis_SkySurfer_Core_T *contStateDisabled;
  bool zCCacheNeedsReset;
  bool derivCacheNeedsReset;
  bool CTOutputIncnstWithState;
  double odeY[37];
  double odeF[4][37];
  ODE4_IntgData intgData;
  DW_SkySurfer_Core_T *dwork;

  /*
   * Sizes:
   * The following substructure contains sizes information
   * for many of the model attributes such as inputs, outputs,
   * dwork, sample times, etc.
   */
  struct {
    int numContStates;
    int numPeriodicContStates;
    int numSampTimes;
  } Sizes;

  /*
   * Timing:
   * The following substructure contains information regarding
   * the timing information for the model.
   */
  struct {
    uint32_t clockTick0;
    double stepSize0;
    uint32_t clockTick1;
    bool firstInitCondFlag;
    struct {
      uint8_t TID[2];
    } TaskCounters;

    double tStart;
    SimTimeStep simTimeStep;
    bool stopRequestedFlag;
    double *t;
    double tArray[2];
  } Timing;
};

/* Block parameters (default storage) */
extern P_SkySurfer_Core_T SkySurfer_Core_P;
extern const ConstB_SkySurfer_Core_T SkySurfer_Core_ConstB;/* constant block i/o */

/* Model entry point functions */
extern void SkySurfer_Core_initialize(RT_MODEL_SkySurfer_Core_T *const
  SkySurfer_Core_M, ExtU_SkySurfer_Core_T *SkySurfer_Core_U,
  ExtY_SkySurfer_Core_T *SkySurfer_Core_Y);
extern void SkySurfer_Core_step(RT_MODEL_SkySurfer_Core_T *const
  SkySurfer_Core_M, ExtU_SkySurfer_Core_T *SkySurfer_Core_U,
  ExtY_SkySurfer_Core_T *SkySurfer_Core_Y);
extern void SkySurfer_Core_terminate(RT_MODEL_SkySurfer_Core_T *const
  SkySurfer_Core_M);

/*-
 * These blocks were eliminated from the model due to optimizations:
 *
 * Block '<S1>/Constant' : Unused code path elimination
 * Block '<S4>/const11' : Unused code path elimination
 * Block '<S4>/const12' : Unused code path elimination
 * Block '<S4>/const18' : Unused code path elimination
 * Block '<S4>/const4' : Unused code path elimination
 * Block '<S81>/Sum of Elements' : Unused code path elimination
 * Block '<S15>/Reshape' : Unused code path elimination
 * Block '<S96>/Scope' : Unused code path elimination
 * Block '<S101>/Scope' : Unused code path elimination
 * Block '<S130>/Add' : Unused code path elimination
 * Block '<S130>/Constant' : Unused code path elimination
 * Block '<S130>/Constant1' : Unused code path elimination
 * Block '<S130>/Divide' : Unused code path elimination
 * Block '<S130>/Divide1' : Unused code path elimination
 * Block '<S133>/DynVisc Conversion' : Unused code path elimination
 * Block '<S130>/Gain' : Unused code path elimination
 * Block '<S135>/KineVisc Conversion' : Unused code path elimination
 * Block '<S130>/Power' : Unused code path elimination
 * Block '<S134>/Height Conversion' : Eliminated nontunable gain of 1
 * Block '<S140>/Cast' : Eliminate redundant data type conversion
 * Block '<S140>/Cast To Double' : Eliminate redundant data type conversion
 * Block '<S148>/Unit Conversion' : Eliminated nontunable gain of 1
 * Block '<S141>/Cast' : Eliminate redundant data type conversion
 * Block '<S141>/Cast To Double' : Eliminate redundant data type conversion
 * Block '<S141>/Cast To Double1' : Eliminate redundant data type conversion
 * Block '<S141>/Cast To Double2' : Eliminate redundant data type conversion
 * Block '<S141>/Cast To Double3' : Eliminate redundant data type conversion
 * Block '<S141>/Cast To Double4' : Eliminate redundant data type conversion
 * Block '<S144>/Cast To Double' : Eliminate redundant data type conversion
 */

/*-
 * The generated code includes comments that allow you to trace directly
 * back to the appropriate location in the model.  The basic format
 * is <system>/block_name, where system is the system number (uniquely
 * assigned by Simulink) and block_name is the name of the block.
 *
 * Use the MATLAB hilite_system command to trace the generated code back
 * to the model.  For example,
 *
 * hilite_system('<S3>')    - opens system 3
 * hilite_system('<S3>/Kp') - opens and selects block Kp which resides in S3
 *
 * Here is the system hierarchy for this model
 *
 * '<Root>' : 'SkySurfer_Core'
 * '<S1>'   : 'SkySurfer_Core/Actuator_Mapping'
 * '<S2>'   : 'SkySurfer_Core/UAV'
 * '<S3>'   : 'SkySurfer_Core/UAV/ACTUATOR'
 * '<S4>'   : 'SkySurfer_Core/UAV/SETTING1'
 * '<S5>'   : 'SkySurfer_Core/UAV/UAV'
 * '<S6>'   : 'SkySurfer_Core/UAV/UAV/6DoF'
 * '<S7>'   : 'SkySurfer_Core/UAV/UAV/Aerodynamic'
 * '<S8>'   : 'SkySurfer_Core/UAV/UAV/Compare To Constant'
 * '<S9>'   : 'SkySurfer_Core/UAV/UAV/Environment'
 * '<S10>'  : 'SkySurfer_Core/UAV/UAV/Ground Model'
 * '<S11>'  : 'SkySurfer_Core/UAV/UAV/Measurement'
 * '<S12>'  : 'SkySurfer_Core/UAV/UAV/Propulsion'
 * '<S13>'  : 'SkySurfer_Core/UAV/UAV/Subsystem'
 * '<S14>'  : 'SkySurfer_Core/UAV/UAV/6DoF/Subsystem'
 * '<S15>'  : 'SkySurfer_Core/UAV/UAV/6DoF/Subsystem1'
 * '<S16>'  : 'SkySurfer_Core/UAV/UAV/6DoF/Subsystem2'
 * '<S17>'  : 'SkySurfer_Core/UAV/UAV/6DoF/Vbxw'
 * '<S18>'  : 'SkySurfer_Core/UAV/UAV/6DoF/transform to Inertial axes '
 * '<S19>'  : 'SkySurfer_Core/UAV/UAV/6DoF/Subsystem/Quaternions to  Direction Cosine Matrix'
 * '<S20>'  : 'SkySurfer_Core/UAV/UAV/6DoF/Subsystem/Quaternions to Rotation Angles'
 * '<S21>'  : 'SkySurfer_Core/UAV/UAV/6DoF/Subsystem/Rotation Angles to Quaternions'
 * '<S22>'  : 'SkySurfer_Core/UAV/UAV/6DoF/Subsystem/qdot'
 * '<S23>'  : 'SkySurfer_Core/UAV/UAV/6DoF/Subsystem/Quaternions to  Direction Cosine Matrix/A11'
 * '<S24>'  : 'SkySurfer_Core/UAV/UAV/6DoF/Subsystem/Quaternions to  Direction Cosine Matrix/A12'
 * '<S25>'  : 'SkySurfer_Core/UAV/UAV/6DoF/Subsystem/Quaternions to  Direction Cosine Matrix/A13'
 * '<S26>'  : 'SkySurfer_Core/UAV/UAV/6DoF/Subsystem/Quaternions to  Direction Cosine Matrix/A21'
 * '<S27>'  : 'SkySurfer_Core/UAV/UAV/6DoF/Subsystem/Quaternions to  Direction Cosine Matrix/A22'
 * '<S28>'  : 'SkySurfer_Core/UAV/UAV/6DoF/Subsystem/Quaternions to  Direction Cosine Matrix/A23'
 * '<S29>'  : 'SkySurfer_Core/UAV/UAV/6DoF/Subsystem/Quaternions to  Direction Cosine Matrix/A31'
 * '<S30>'  : 'SkySurfer_Core/UAV/UAV/6DoF/Subsystem/Quaternions to  Direction Cosine Matrix/A32'
 * '<S31>'  : 'SkySurfer_Core/UAV/UAV/6DoF/Subsystem/Quaternions to  Direction Cosine Matrix/A33'
 * '<S32>'  : 'SkySurfer_Core/UAV/UAV/6DoF/Subsystem/Quaternions to  Direction Cosine Matrix/Create 3x3 Matrix'
 * '<S33>'  : 'SkySurfer_Core/UAV/UAV/6DoF/Subsystem/Quaternions to  Direction Cosine Matrix/Quaternion Normalize'
 * '<S34>'  : 'SkySurfer_Core/UAV/UAV/6DoF/Subsystem/Quaternions to  Direction Cosine Matrix/Quaternion Normalize/Quaternion Modulus'
 * '<S35>'  : 'SkySurfer_Core/UAV/UAV/6DoF/Subsystem/Quaternions to  Direction Cosine Matrix/Quaternion Normalize/Quaternion Modulus/Quaternion Norm'
 * '<S36>'  : 'SkySurfer_Core/UAV/UAV/6DoF/Subsystem/Quaternions to Rotation Angles/DCM2Ang'
 * '<S37>'  : 'SkySurfer_Core/UAV/UAV/6DoF/Subsystem/Quaternions to Rotation Angles/Quat2DCM'
 * '<S38>'  : 'SkySurfer_Core/UAV/UAV/6DoF/Subsystem/Quaternions to Rotation Angles/DCM2Ang/AxisRotDefault'
 * '<S39>'  : 'SkySurfer_Core/UAV/UAV/6DoF/Subsystem/Quaternions to Rotation Angles/DCM2Ang/AxisRotZeroR3'
 * '<S40>'  : 'SkySurfer_Core/UAV/UAV/6DoF/Subsystem/Quaternions to Rotation Angles/DCM2Ang/Get DCM Values'
 * '<S41>'  : 'SkySurfer_Core/UAV/UAV/6DoF/Subsystem/Quaternions to Rotation Angles/DCM2Ang/Validate DCM'
 * '<S42>'  : 'SkySurfer_Core/UAV/UAV/6DoF/Subsystem/Quaternions to Rotation Angles/DCM2Ang/AxisRotDefault/Protect asincos input'
 * '<S43>'  : 'SkySurfer_Core/UAV/UAV/6DoF/Subsystem/Quaternions to Rotation Angles/DCM2Ang/AxisRotDefault/Protect asincos input/If Action Subsystem'
 * '<S44>'  : 'SkySurfer_Core/UAV/UAV/6DoF/Subsystem/Quaternions to Rotation Angles/DCM2Ang/AxisRotDefault/Protect asincos input/If Action Subsystem1'
 * '<S45>'  : 'SkySurfer_Core/UAV/UAV/6DoF/Subsystem/Quaternions to Rotation Angles/DCM2Ang/AxisRotDefault/Protect asincos input/If Action Subsystem2'
 * '<S46>'  : 'SkySurfer_Core/UAV/UAV/6DoF/Subsystem/Quaternions to Rotation Angles/DCM2Ang/AxisRotZeroR3/Protect asincos input'
 * '<S47>'  : 'SkySurfer_Core/UAV/UAV/6DoF/Subsystem/Quaternions to Rotation Angles/DCM2Ang/AxisRotZeroR3/Protect asincos input/If Action Subsystem'
 * '<S48>'  : 'SkySurfer_Core/UAV/UAV/6DoF/Subsystem/Quaternions to Rotation Angles/DCM2Ang/AxisRotZeroR3/Protect asincos input/If Action Subsystem1'
 * '<S49>'  : 'SkySurfer_Core/UAV/UAV/6DoF/Subsystem/Quaternions to Rotation Angles/DCM2Ang/AxisRotZeroR3/Protect asincos input/If Action Subsystem2'
 * '<S50>'  : 'SkySurfer_Core/UAV/UAV/6DoF/Subsystem/Quaternions to Rotation Angles/DCM2Ang/Validate DCM/If Warning//Error'
 * '<S51>'  : 'SkySurfer_Core/UAV/UAV/6DoF/Subsystem/Quaternions to Rotation Angles/DCM2Ang/Validate DCM/If Warning//Error/Else If Not Orthogonal'
 * '<S52>'  : 'SkySurfer_Core/UAV/UAV/6DoF/Subsystem/Quaternions to Rotation Angles/DCM2Ang/Validate DCM/If Warning//Error/Else No Action'
 * '<S53>'  : 'SkySurfer_Core/UAV/UAV/6DoF/Subsystem/Quaternions to Rotation Angles/DCM2Ang/Validate DCM/If Warning//Error/If Not Proper'
 * '<S54>'  : 'SkySurfer_Core/UAV/UAV/6DoF/Subsystem/Quaternions to Rotation Angles/DCM2Ang/Validate DCM/If Warning//Error/isNotOrthogonal'
 * '<S55>'  : 'SkySurfer_Core/UAV/UAV/6DoF/Subsystem/Quaternions to Rotation Angles/DCM2Ang/Validate DCM/If Warning//Error/isNotProper'
 * '<S56>'  : 'SkySurfer_Core/UAV/UAV/6DoF/Subsystem/Quaternions to Rotation Angles/DCM2Ang/Validate DCM/If Warning//Error/Else If Not Orthogonal/Error'
 * '<S57>'  : 'SkySurfer_Core/UAV/UAV/6DoF/Subsystem/Quaternions to Rotation Angles/DCM2Ang/Validate DCM/If Warning//Error/Else If Not Orthogonal/None'
 * '<S58>'  : 'SkySurfer_Core/UAV/UAV/6DoF/Subsystem/Quaternions to Rotation Angles/DCM2Ang/Validate DCM/If Warning//Error/Else If Not Orthogonal/Warning'
 * '<S59>'  : 'SkySurfer_Core/UAV/UAV/6DoF/Subsystem/Quaternions to Rotation Angles/DCM2Ang/Validate DCM/If Warning//Error/If Not Proper/Error'
 * '<S60>'  : 'SkySurfer_Core/UAV/UAV/6DoF/Subsystem/Quaternions to Rotation Angles/DCM2Ang/Validate DCM/If Warning//Error/If Not Proper/None'
 * '<S61>'  : 'SkySurfer_Core/UAV/UAV/6DoF/Subsystem/Quaternions to Rotation Angles/DCM2Ang/Validate DCM/If Warning//Error/If Not Proper/Warning'
 * '<S62>'  : 'SkySurfer_Core/UAV/UAV/6DoF/Subsystem/Quaternions to Rotation Angles/DCM2Ang/Validate DCM/If Warning//Error/isNotOrthogonal/transpose*dcm ~= eye(3)'
 * '<S63>'  : 'SkySurfer_Core/UAV/UAV/6DoF/Subsystem/Quaternions to Rotation Angles/DCM2Ang/Validate DCM/If Warning//Error/isNotProper/Determinant of 3x3 Matrix'
 * '<S64>'  : 'SkySurfer_Core/UAV/UAV/6DoF/Subsystem/Quaternions to Rotation Angles/DCM2Ang/Validate DCM/If Warning//Error/isNotProper/determinant does not equal 1'
 * '<S65>'  : 'SkySurfer_Core/UAV/UAV/6DoF/Subsystem/Quaternions to Rotation Angles/Quat2DCM/A11'
 * '<S66>'  : 'SkySurfer_Core/UAV/UAV/6DoF/Subsystem/Quaternions to Rotation Angles/Quat2DCM/A12'
 * '<S67>'  : 'SkySurfer_Core/UAV/UAV/6DoF/Subsystem/Quaternions to Rotation Angles/Quat2DCM/A13'
 * '<S68>'  : 'SkySurfer_Core/UAV/UAV/6DoF/Subsystem/Quaternions to Rotation Angles/Quat2DCM/A21'
 * '<S69>'  : 'SkySurfer_Core/UAV/UAV/6DoF/Subsystem/Quaternions to Rotation Angles/Quat2DCM/A22'
 * '<S70>'  : 'SkySurfer_Core/UAV/UAV/6DoF/Subsystem/Quaternions to Rotation Angles/Quat2DCM/A23'
 * '<S71>'  : 'SkySurfer_Core/UAV/UAV/6DoF/Subsystem/Quaternions to Rotation Angles/Quat2DCM/A31'
 * '<S72>'  : 'SkySurfer_Core/UAV/UAV/6DoF/Subsystem/Quaternions to Rotation Angles/Quat2DCM/A32'
 * '<S73>'  : 'SkySurfer_Core/UAV/UAV/6DoF/Subsystem/Quaternions to Rotation Angles/Quat2DCM/A33'
 * '<S74>'  : 'SkySurfer_Core/UAV/UAV/6DoF/Subsystem/Quaternions to Rotation Angles/Quat2DCM/Create 3x3 Matrix'
 * '<S75>'  : 'SkySurfer_Core/UAV/UAV/6DoF/Subsystem/Quaternions to Rotation Angles/Quat2DCM/Quaternion Normalize'
 * '<S76>'  : 'SkySurfer_Core/UAV/UAV/6DoF/Subsystem/Quaternions to Rotation Angles/Quat2DCM/Quaternion Normalize/Quaternion Modulus'
 * '<S77>'  : 'SkySurfer_Core/UAV/UAV/6DoF/Subsystem/Quaternions to Rotation Angles/Quat2DCM/Quaternion Normalize/Quaternion Modulus/Quaternion Norm'
 * '<S78>'  : 'SkySurfer_Core/UAV/UAV/6DoF/Subsystem/qdot/Quaternion Normalize'
 * '<S79>'  : 'SkySurfer_Core/UAV/UAV/6DoF/Subsystem/qdot/Quaternion Normalize/Quaternion Modulus'
 * '<S80>'  : 'SkySurfer_Core/UAV/UAV/6DoF/Subsystem/qdot/Quaternion Normalize/Quaternion Modulus/Quaternion Norm'
 * '<S81>'  : 'SkySurfer_Core/UAV/UAV/6DoF/Subsystem1/Mass input//output  momentum'
 * '<S82>'  : 'SkySurfer_Core/UAV/UAV/6DoF/Subsystem1/Mass input//output  momentum/For Each Subsystem'
 * '<S83>'  : 'SkySurfer_Core/UAV/UAV/6DoF/Subsystem2/3x3 Cross Product'
 * '<S84>'  : 'SkySurfer_Core/UAV/UAV/6DoF/Subsystem2/I x w'
 * '<S85>'  : 'SkySurfer_Core/UAV/UAV/6DoF/Subsystem2/I x w1'
 * '<S86>'  : 'SkySurfer_Core/UAV/UAV/6DoF/Subsystem2/3x3 Cross Product/Subsystem'
 * '<S87>'  : 'SkySurfer_Core/UAV/UAV/6DoF/Subsystem2/3x3 Cross Product/Subsystem1'
 * '<S88>'  : 'SkySurfer_Core/UAV/UAV/6DoF/Vbxw/Subsystem'
 * '<S89>'  : 'SkySurfer_Core/UAV/UAV/6DoF/Vbxw/Subsystem1'
 * '<S90>'  : 'SkySurfer_Core/UAV/UAV/Aerodynamic/CD'
 * '<S91>'  : 'SkySurfer_Core/UAV/UAV/Aerodynamic/CDD'
 * '<S92>'  : 'SkySurfer_Core/UAV/UAV/Aerodynamic/CL'
 * '<S93>'  : 'SkySurfer_Core/UAV/UAV/Aerodynamic/CLL'
 * '<S94>'  : 'SkySurfer_Core/UAV/UAV/Aerodynamic/CMl'
 * '<S95>'  : 'SkySurfer_Core/UAV/UAV/Aerodynamic/CMm'
 * '<S96>'  : 'SkySurfer_Core/UAV/UAV/Aerodynamic/CMn'
 * '<S97>'  : 'SkySurfer_Core/UAV/UAV/Aerodynamic/CSS'
 * '<S98>'  : 'SkySurfer_Core/UAV/UAV/Aerodynamic/CY'
 * '<S99>'  : 'SkySurfer_Core/UAV/UAV/Aerodynamic/Cl'
 * '<S100>' : 'SkySurfer_Core/UAV/UAV/Aerodynamic/Cm'
 * '<S101>' : 'SkySurfer_Core/UAV/UAV/Aerodynamic/Cn'
 * '<S102>' : 'SkySurfer_Core/UAV/UAV/Aerodynamic/Degrees to Radians'
 * '<S103>' : 'SkySurfer_Core/UAV/UAV/Aerodynamic/Dynamic Pressure'
 * '<S104>' : 'SkySurfer_Core/UAV/UAV/Aerodynamic/CDD/Degrees to Radians'
 * '<S105>' : 'SkySurfer_Core/UAV/UAV/Aerodynamic/CDD/Degrees to Radians1'
 * '<S106>' : 'SkySurfer_Core/UAV/UAV/Aerodynamic/CDD/Degrees to Radians2'
 * '<S107>' : 'SkySurfer_Core/UAV/UAV/Aerodynamic/CDD/Degrees to Radians3'
 * '<S108>' : 'SkySurfer_Core/UAV/UAV/Aerodynamic/CLL/Degrees to Radians4'
 * '<S109>' : 'SkySurfer_Core/UAV/UAV/Aerodynamic/CLL/Degrees to Radians5'
 * '<S110>' : 'SkySurfer_Core/UAV/UAV/Aerodynamic/CLL/Degrees to Radians6'
 * '<S111>' : 'SkySurfer_Core/UAV/UAV/Aerodynamic/CLL/Degrees to Radians7'
 * '<S112>' : 'SkySurfer_Core/UAV/UAV/Aerodynamic/CMl/Degrees to Radians4'
 * '<S113>' : 'SkySurfer_Core/UAV/UAV/Aerodynamic/CMl/Degrees to Radians5'
 * '<S114>' : 'SkySurfer_Core/UAV/UAV/Aerodynamic/CMl/Degrees to Radians6'
 * '<S115>' : 'SkySurfer_Core/UAV/UAV/Aerodynamic/CMl/Degrees to Radians7'
 * '<S116>' : 'SkySurfer_Core/UAV/UAV/Aerodynamic/CMm/Degrees to Radians4'
 * '<S117>' : 'SkySurfer_Core/UAV/UAV/Aerodynamic/CMm/Degrees to Radians5'
 * '<S118>' : 'SkySurfer_Core/UAV/UAV/Aerodynamic/CMm/Degrees to Radians6'
 * '<S119>' : 'SkySurfer_Core/UAV/UAV/Aerodynamic/CMm/Degrees to Radians7'
 * '<S120>' : 'SkySurfer_Core/UAV/UAV/Aerodynamic/CMn/Degrees to Radians4'
 * '<S121>' : 'SkySurfer_Core/UAV/UAV/Aerodynamic/CMn/Degrees to Radians5'
 * '<S122>' : 'SkySurfer_Core/UAV/UAV/Aerodynamic/CMn/Degrees to Radians6'
 * '<S123>' : 'SkySurfer_Core/UAV/UAV/Aerodynamic/CMn/Degrees to Radians7'
 * '<S124>' : 'SkySurfer_Core/UAV/UAV/Aerodynamic/CSS/Degrees to Radians4'
 * '<S125>' : 'SkySurfer_Core/UAV/UAV/Aerodynamic/CSS/Degrees to Radians5'
 * '<S126>' : 'SkySurfer_Core/UAV/UAV/Aerodynamic/CSS/Degrees to Radians6'
 * '<S127>' : 'SkySurfer_Core/UAV/UAV/Aerodynamic/CSS/Degrees to Radians7'
 * '<S128>' : 'SkySurfer_Core/UAV/UAV/Aerodynamic/Dynamic Pressure/dot'
 * '<S129>' : 'SkySurfer_Core/UAV/UAV/Environment/Gravity'
 * '<S130>' : 'SkySurfer_Core/UAV/UAV/Environment/ISA Atmosphere Model'
 * '<S131>' : 'SkySurfer_Core/UAV/UAV/Environment/Wind'
 * '<S132>' : 'SkySurfer_Core/UAV/UAV/Environment/ISA Atmosphere Model/Density Subsystem'
 * '<S133>' : 'SkySurfer_Core/UAV/UAV/Environment/ISA Atmosphere Model/DynVisc Subsystem'
 * '<S134>' : 'SkySurfer_Core/UAV/UAV/Environment/ISA Atmosphere Model/Height Subsystem'
 * '<S135>' : 'SkySurfer_Core/UAV/UAV/Environment/ISA Atmosphere Model/KineVisc Subsystem'
 * '<S136>' : 'SkySurfer_Core/UAV/UAV/Environment/ISA Atmosphere Model/Modelling'
 * '<S137>' : 'SkySurfer_Core/UAV/UAV/Environment/ISA Atmosphere Model/Pressure Subsystem'
 * '<S138>' : 'SkySurfer_Core/UAV/UAV/Environment/ISA Atmosphere Model/Speed Subsystem'
 * '<S139>' : 'SkySurfer_Core/UAV/UAV/Environment/ISA Atmosphere Model/Temperature Subsystem'
 * '<S140>' : 'SkySurfer_Core/UAV/UAV/Environment/Wind/Discrete Wind Gust Model - On'
 * '<S141>' : 'SkySurfer_Core/UAV/UAV/Environment/Wind/Dryden Wind Turbulence Model  (Continuous (+q -r))'
 * '<S142>' : 'SkySurfer_Core/UAV/UAV/Environment/Wind/Horizontal Wind Model'
 * '<S143>' : 'SkySurfer_Core/UAV/UAV/Environment/Wind/Velocity Conversion3'
 * '<S144>' : 'SkySurfer_Core/UAV/UAV/Environment/Wind/Wind Shear Model'
 * '<S145>' : 'SkySurfer_Core/UAV/UAV/Environment/Wind/Discrete Wind Gust Model - On/Distance into gust (x)'
 * '<S146>' : 'SkySurfer_Core/UAV/UAV/Environment/Wind/Discrete Wind Gust Model - On/Distance into gust (y)'
 * '<S147>' : 'SkySurfer_Core/UAV/UAV/Environment/Wind/Discrete Wind Gust Model - On/Distance into gust (z)'
 * '<S148>' : 'SkySurfer_Core/UAV/UAV/Environment/Wind/Discrete Wind Gust Model - On/Velocity Conversion'
 * '<S149>' : 'SkySurfer_Core/UAV/UAV/Environment/Wind/Dryden Wind Turbulence Model  (Continuous (+q -r))/Angle Conversion'
 * '<S150>' : 'SkySurfer_Core/UAV/UAV/Environment/Wind/Dryden Wind Turbulence Model  (Continuous (+q -r))/Filters on angular rates'
 * '<S151>' : 'SkySurfer_Core/UAV/UAV/Environment/Wind/Dryden Wind Turbulence Model  (Continuous (+q -r))/Filters on velocities'
 * '<S152>' : 'SkySurfer_Core/UAV/UAV/Environment/Wind/Dryden Wind Turbulence Model  (Continuous (+q -r))/Length Conversion'
 * '<S153>' : 'SkySurfer_Core/UAV/UAV/Environment/Wind/Dryden Wind Turbulence Model  (Continuous (+q -r))/Length Conversion1'
 * '<S154>' : 'SkySurfer_Core/UAV/UAV/Environment/Wind/Dryden Wind Turbulence Model  (Continuous (+q -r))/RMS turbulence  intensities'
 * '<S155>' : 'SkySurfer_Core/UAV/UAV/Environment/Wind/Dryden Wind Turbulence Model  (Continuous (+q -r))/Select angular rates'
 * '<S156>' : 'SkySurfer_Core/UAV/UAV/Environment/Wind/Dryden Wind Turbulence Model  (Continuous (+q -r))/Select velocities'
 * '<S157>' : 'SkySurfer_Core/UAV/UAV/Environment/Wind/Dryden Wind Turbulence Model  (Continuous (+q -r))/Turbulence scale lengths'
 * '<S158>' : 'SkySurfer_Core/UAV/UAV/Environment/Wind/Dryden Wind Turbulence Model  (Continuous (+q -r))/Velocity Conversion'
 * '<S159>' : 'SkySurfer_Core/UAV/UAV/Environment/Wind/Dryden Wind Turbulence Model  (Continuous (+q -r))/Velocity Conversion2'
 * '<S160>' : 'SkySurfer_Core/UAV/UAV/Environment/Wind/Dryden Wind Turbulence Model  (Continuous (+q -r))/White Noise'
 * '<S161>' : 'SkySurfer_Core/UAV/UAV/Environment/Wind/Dryden Wind Turbulence Model  (Continuous (+q -r))/Filters on angular rates/Hpgw'
 * '<S162>' : 'SkySurfer_Core/UAV/UAV/Environment/Wind/Dryden Wind Turbulence Model  (Continuous (+q -r))/Filters on angular rates/Hqgw'
 * '<S163>' : 'SkySurfer_Core/UAV/UAV/Environment/Wind/Dryden Wind Turbulence Model  (Continuous (+q -r))/Filters on angular rates/Hrgw'
 * '<S164>' : 'SkySurfer_Core/UAV/UAV/Environment/Wind/Dryden Wind Turbulence Model  (Continuous (+q -r))/Filters on velocities/Hugw(s)'
 * '<S165>' : 'SkySurfer_Core/UAV/UAV/Environment/Wind/Dryden Wind Turbulence Model  (Continuous (+q -r))/Filters on velocities/Hvgw(s)'
 * '<S166>' : 'SkySurfer_Core/UAV/UAV/Environment/Wind/Dryden Wind Turbulence Model  (Continuous (+q -r))/Filters on velocities/Hwgw(s)'
 * '<S167>' : 'SkySurfer_Core/UAV/UAV/Environment/Wind/Dryden Wind Turbulence Model  (Continuous (+q -r))/RMS turbulence  intensities/High Altitude Intensity'
 * '<S168>' : 'SkySurfer_Core/UAV/UAV/Environment/Wind/Dryden Wind Turbulence Model  (Continuous (+q -r))/RMS turbulence  intensities/Low Altitude Intensity'
 * '<S169>' : 'SkySurfer_Core/UAV/UAV/Environment/Wind/Dryden Wind Turbulence Model  (Continuous (+q -r))/Select angular rates/Interpolate  rates'
 * '<S170>' : 'SkySurfer_Core/UAV/UAV/Environment/Wind/Dryden Wind Turbulence Model  (Continuous (+q -r))/Select angular rates/Low altitude  rates'
 * '<S171>' : 'SkySurfer_Core/UAV/UAV/Environment/Wind/Dryden Wind Turbulence Model  (Continuous (+q -r))/Select angular rates/Medium//High  altitude rates'
 * '<S172>' : 'SkySurfer_Core/UAV/UAV/Environment/Wind/Dryden Wind Turbulence Model  (Continuous (+q -r))/Select angular rates/Merge Subsystems'
 * '<S173>' : 'SkySurfer_Core/UAV/UAV/Environment/Wind/Dryden Wind Turbulence Model  (Continuous (+q -r))/Select angular rates/Interpolate  rates/wind to body transformation'
 * '<S174>' : 'SkySurfer_Core/UAV/UAV/Environment/Wind/Dryden Wind Turbulence Model  (Continuous (+q -r))/Select angular rates/Interpolate  rates/wind to body transformation/convert to earth coords'
 * '<S175>' : 'SkySurfer_Core/UAV/UAV/Environment/Wind/Dryden Wind Turbulence Model  (Continuous (+q -r))/Select angular rates/Low altitude  rates/wind to body transformation'
 * '<S176>' : 'SkySurfer_Core/UAV/UAV/Environment/Wind/Dryden Wind Turbulence Model  (Continuous (+q -r))/Select angular rates/Low altitude  rates/wind to body transformation/convert to earth coords'
 * '<S177>' : 'SkySurfer_Core/UAV/UAV/Environment/Wind/Dryden Wind Turbulence Model  (Continuous (+q -r))/Select velocities/Interpolate  velocities'
 * '<S178>' : 'SkySurfer_Core/UAV/UAV/Environment/Wind/Dryden Wind Turbulence Model  (Continuous (+q -r))/Select velocities/Low altitude  velocities'
 * '<S179>' : 'SkySurfer_Core/UAV/UAV/Environment/Wind/Dryden Wind Turbulence Model  (Continuous (+q -r))/Select velocities/Medium//High  altitude velocities'
 * '<S180>' : 'SkySurfer_Core/UAV/UAV/Environment/Wind/Dryden Wind Turbulence Model  (Continuous (+q -r))/Select velocities/Merge Subsystems'
 * '<S181>' : 'SkySurfer_Core/UAV/UAV/Environment/Wind/Dryden Wind Turbulence Model  (Continuous (+q -r))/Select velocities/Interpolate  velocities/wind to body transformation'
 * '<S182>' : 'SkySurfer_Core/UAV/UAV/Environment/Wind/Dryden Wind Turbulence Model  (Continuous (+q -r))/Select velocities/Interpolate  velocities/wind to body transformation/convert to earth coords'
 * '<S183>' : 'SkySurfer_Core/UAV/UAV/Environment/Wind/Dryden Wind Turbulence Model  (Continuous (+q -r))/Select velocities/Low altitude  velocities/wind to body transformation'
 * '<S184>' : 'SkySurfer_Core/UAV/UAV/Environment/Wind/Dryden Wind Turbulence Model  (Continuous (+q -r))/Select velocities/Low altitude  velocities/wind to body transformation/convert to earth coords'
 * '<S185>' : 'SkySurfer_Core/UAV/UAV/Environment/Wind/Dryden Wind Turbulence Model  (Continuous (+q -r))/Turbulence scale lengths/Low altitude scale length'
 * '<S186>' : 'SkySurfer_Core/UAV/UAV/Environment/Wind/Dryden Wind Turbulence Model  (Continuous (+q -r))/Turbulence scale lengths/Medium//High altitude scale length'
 * '<S187>' : 'SkySurfer_Core/UAV/UAV/Environment/Wind/Dryden Wind Turbulence Model  (Continuous (+q -r))/Turbulence scale lengths/Medium//High altitude scale length/Length Conversion'
 * '<S188>' : 'SkySurfer_Core/UAV/UAV/Environment/Wind/Horizontal Wind Model/Angle Conversion'
 * '<S189>' : 'SkySurfer_Core/UAV/UAV/Environment/Wind/Wind Shear Model/Angle Conversion'
 * '<S190>' : 'SkySurfer_Core/UAV/UAV/Environment/Wind/Wind Shear Model/Length Conversion'
 * '<S191>' : 'SkySurfer_Core/UAV/UAV/Ground Model/Friction Force'
 * '<S192>' : 'SkySurfer_Core/UAV/UAV/Ground Model/Normal Force'
 * '<S193>' : 'SkySurfer_Core/UAV/UAV/Ground Model/Friction Force/Soft Coulomb Friction'
 * '<S194>' : 'SkySurfer_Core/UAV/UAV/Measurement/Mach Number'
 * '<S195>' : 'SkySurfer_Core/UAV/UAV/Measurement/Radians to Degrees4'
 * '<S196>' : 'SkySurfer_Core/UAV/UAV/Measurement/Radians to Degrees5'
 * '<S197>' : 'SkySurfer_Core/UAV/UAV/Measurement/Subsystem'
 * '<S198>' : 'SkySurfer_Core/UAV/UAV/Measurement/Mach Number/dot'
 * '<S199>' : 'SkySurfer_Core/UAV/UAV/Measurement/Subsystem/Subsystem'
 * '<S200>' : 'SkySurfer_Core/UAV/UAV/Measurement/Subsystem/Subsystem1'
 * '<S201>' : 'SkySurfer_Core/UAV/UAV/Measurement/Subsystem/dot'
 * '<S202>' : 'SkySurfer_Core/UAV/UAV/Subsystem/Degrees to Radians6'
 */
#endif                                 /* SkySurfer_Core_h_ */

/*
 * File trailer for generated code.
 *
 * [EOF]
 */
