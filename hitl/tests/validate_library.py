import argparse,ctypes as C,importlib.util,json,math,sys,time
from pathlib import Path
import numpy as np
RUNTIME=Path(__file__).resolve().parents[1];sys.path.insert(0,str(RUNTIME))
from host.abi import Model,Worker,Input,Output,Info,Initial,header
from host.packets import Encoder
PLANT=RUNTIME.parent/'plant';sys.path.insert(0,str(PLANT/'core'))
from toolchain import lib as libname
G0=9.80665;SEED=1 # adapter.c HIL_DEFAULT_SEED (seed_policy 0)
LAT,LON=22.910275834988674,120.31096929726908
def plant_module():
 # ctypes structs of Plant / PlantSensors; their layout is checked against the C headers by validate_plant.py.
 spec=importlib.util.spec_from_file_location('validate_plant',PLANT/'core/validate_plant.py');mod=importlib.util.module_from_spec(spec);spec.loader.exec_module(mod);return mod
def expected_raw(t,s):
 # raw_source[58] from PlantTruth / PlantSensorOutput, positions as in adapter.c fill_raw().
 d=180/math.pi;r=[0.0]*58;yaw=math.fmod(t.euler_rad[2],2*math.pi)
 if yaw<0:yaw+=2*math.pi
 r[0:5]=[t.surface_deflection_rad[1]*d,t.surface_deflection_rad[0]*d,t.surface_deflection_rad[2]*d,t.throttle_actual,t.surface_deflection_rad[3]*d]
 r[5]=t.angular_accel_body_rad_s2[0];r[6:10]=list(t.quaternion_nb);r[10]=0.0 if yaw>=2*math.pi else yaw;r[11]=t.euler_rad[1];r[12]=t.euler_rad[0]
 r[13]=t.angular_accel_body_rad_s2[1];r[14]=t.angular_accel_body_rad_s2[2];r[15:18]=list(t.velocity_ned_m_s);r[18]=-t.velocity_ned_m_s[2];r[19]=t.height_agl_m
 r[20]=t.latitude_deg;r[21]=t.longitude_deg;r[22:25]=list(t.position_ned_m);r[25]=t.alpha_rad*d;r[26]=t.beta_rad*d;r[27]=t.airspeed_true_m_s
 r[28:31]=list(t.rates_body_rad_s);r[31:34]=list(t.specific_force_body_m_s2);r[34]=-t.specific_force_body_m_s2[2]/G0;r[35]=t.ground_speed_m_s;r[36]=t.mach;r[37]=t.alpha_rad;r[38]=t.beta_rad
 r[39:42]=list(s.accel_m_s2);r[42:45]=list(s.gyro_rad_s);r[45:48]=[v/100 for v in s.magnetic_ut];r[48]=s.absolute_pressure_pa/100;r[49]=s.differential_pressure_pa/100
 r[50]=s.gps_lla_msl[0]*1e7;r[51]=s.gps_lla_msl[1]*1e7;r[52]=s.gps_lla_msl[2]*1000;r[53:56]=[v*100 for v in s.gps_velocity_ned_m_s];r[56]=s.gps_ground_speed_m_s*100;r[57]=s.gps_course_deg*100
 return r
def canonical(o):return [*o.accel_m_s2,*o.gyro_rad_s,*o.magnetic_uT,o.absolute_pressure_pa,o.differential_pressure_pa,*o.gps_lla_msl,*o.velocity_ned_m_s,o.ground_speed_m_s,o.course_deg]
def ratio(a,b,tol=1e-12):a=np.asarray(a,float);b=np.asarray(b,float);return float(np.max(np.abs(a-b)/(tol+tol*np.abs(b)))) if a.size else 0.0
def abi_initial(height,u,euler,geoid):
 x=header(Initial);x.height_m=height;x.body_velocity_m_s[0]=u;x.euler_deg[:]=euler;x.latitude_deg=LAT;x.longitude_deg=LON;x.geoid_separation_m=geoid;return x
def adapter_checks(cache,m):
 # The adapter against Plant + PlantSensors run directly (libskysurfer_plant, same sources, same seed):
 # every raw_source field, every canonical field, P8 relations, raw/canonical decoding, time stamps, flags,
 # GPS latching and geoid. Then the raw yaw wrap at its boundaries.
 vp=plant_module();lib=vp.Lib(cache/'native'/libname('skysurfer_plant'));r=cache/'results';report={}
 fields={'raw':0.0,'canonical':0.0,'p8':0.0,'raw_canonical':0.0};timing=[];steps=0
 for case,height,u,euler,geoid in [('ground',0,0,[0,.8633,0],0.0),('air',100,20,[0,.8633,25],25.0)]:
  controls=np.loadtxt(r/f'controls_{case}.csv',delimiter=',')[:,1:];m.check(m.lib.hil_model_reset(C.byref(abi_initial(height,u,euler,geoid))))
  ic=vp.Initial();ic.height_agl_m=height;ic.velocity_body_m_s[0]=u;ic.latitude_deg=LAT;ic.longitude_deg=LON;ic.seed=SEED
  for k in range(3):ic.euler_rad[k]=euler[k]*(math.pi/180.0)
  plant=lib.plant();sensors=lib.sensors();config=lib.config();lib.lib.plant_init(plant,C.byref(ic));lib.lib.plant_sensors_init(sensors,C.byref(config),SEED)
  i=header(Input);o=header(Output);t=vp.Truth();s=vp.Output();pin=vp.Input();gps=None
  for k,row in enumerate(controls):
   i.step_index=k;i.actuator_valid=i.actuator_new=1;i.controls[:]=row;m.check(m.lib.hil_model_step(C.byref(i),C.byref(o)))
   pin.command[:]=row[:5];lib.lib.plant_step(plant,C.byref(pin),C.byref(t));lib.lib.plant_sensors_step(sensors,C.byref(t),C.byref(s))
   raw=list(o.raw_source);steps+=1
   fields['raw']=max(fields['raw'],ratio(raw,expected_raw(t,s)))
   ideal=[*s.accel_m_s2,*s.gyro_rad_s,*s.magnetic_ut,s.absolute_pressure_pa,s.differential_pressure_pa,s.gps_lla_msl[0],s.gps_lla_msl[1],s.gps_lla_msl[2]-geoid,*s.gps_velocity_ned_m_s,s.gps_ground_speed_m_s,s.gps_course_deg]
   fields['canonical']=max(fields['canonical'],ratio(canonical(o),ideal))
   # P8 (MODEL_REVIEW): G = -f_z / g and the horizontal ground speed, from the raw fields themselves.
   fields['p8']=max(fields['p8'],ratio([raw[34],raw[35]],[-raw[33]/G0,math.hypot(raw[15],raw[16])]))
   decoded=[*[v*100 for v in raw[45:48]],raw[48]*100,raw[49]*100,raw[50]*1e-7,raw[51]*1e-7,raw[52]/1000-geoid,*[v/100 for v in raw[53:56]],raw[56]/100,raw[57]/100]
   fields['raw_canonical']=max(fields['raw_canonical'],ratio(canonical(o)[6:],decoded,1e-9))
   update=k%25==0;gps=canonical(o)[11:] if update else gps
   timing.append(o.model_time_ns==k*4000000 and o.imu_sample_time_ns==o.model_time_ns and [o.imu_valid,o.imu_updated,o.gps_valid,o.pressure_height_valid,o.temperature_valid,o.fields_updated]==[1,1,1,0,0,0x7ff]
    and o.gps_updated==int(update) and o.gps_sample_time_ns==(k//25)*100000000 and canonical(o)[11:]==gps)
 report['adapter_fields']={'status':'PASS' if fields['raw']<=1 and fields['canonical']<=1 else 'FAIL','max_error_ratio_raw':fields['raw'],'max_error_ratio_canonical':fields['canonical'],'steps':steps,'tolerance':'1e-12 abs + 1e-12 rel'}
 report['p8_and_decoding']={'status':'PASS' if fields['p8']<=1 and fields['raw_canonical']<=1 else 'FAIL','max_error_ratio_p8':fields['p8'],'max_error_ratio_raw_canonical':fields['raw_canonical']}
 report['adapter_timing']={'status':'PASS' if all(timing) else 'FAIL','steps':len(timing),'failures':timing.count(False)}
 yaws={}
 for yaw in [0.0,1e-16,-1e-16,180.0,-180.0,359.9999999,360.0,-360.0]:
  m.check(m.lib.hil_model_reset(C.byref(abi_initial(0,0,[0,0,yaw],0.0))));i=header(Input);i.step_index=0;m.check(m.lib.hil_model_step(C.byref(i),C.byref(o)))
  v=o.raw_source[10];yaws[repr(yaw)]=v
  if not(0<=v<2*math.pi and abs(math.remainder(v-math.radians(yaw),2*math.pi))<1e-9):yaws['fail']=True
 report['yaw_wrap']={'status':'FAIL' if yaws.pop('fail',False) else 'PASS','raw_yaw_rad':yaws}
 return report
# raw_source index -> CoreSnapshot column (plant/include/plant_core.h), sign. Truth fields the core outputs directly.
RAW_FROM_CORE=[(22,0,1),(23,1,1),(24,2,1),(6,6,1),(7,7,1),(8,8,1),(9,9,1),(28,10,1),(29,11,1),(30,12,1),(15,13,1),(16,14,1),(17,15,1),
 (5,19,1),(13,20,1),(14,21,1),(12,16,1),(11,17,1),(25,53,1),(26,54,1),(27,52,1),(36,55,1),(0,67,1),(1,66,1),(2,68,1),(3,70,1),(4,69,1),(19,2,-1),(18,15,-1)]
def validate(cache):
 r=cache/'results';m=Model(cache/'native'/libname('skysurfer'));report={}
 ri=[a for a,b,c in RAW_FROM_CORE];ci=[b for a,b,c in RAW_FROM_CORE];sign=np.array([c for a,b,c in RAW_FROM_CORE],dtype=float)
 at=np.full(len(ri),1e-6);rt=np.full(len(ri),1e-8);at[3:7]=1e-9;at[22:27]=1e-9
 a=None;a_bytes=None
 # The wind case of build_core.m (every wind component on, from t = 0): steady 15 kts from 30 deg (not used in the
 # shear/gust/turbulence mode), gust from 0.3 s with the source amplitudes, shear 3 m/s from 30 deg, turbulence at the
 # reference W20 1 m/s, source seeds. The same through the HIL ABI (hil_model_configure_wind).
 wind_case=dict(steady_ned_m_s=[0.0,0.0,0.0],start_mode=2,start_height_m=5.0,start_time_s=0.0,ramp_s=0.0,gust_start_s=0.3,
  gust_length_m=[120.0,120.0,80.0],gust_magnitude_m_s=[3.5,3.0,3.0],shear_speed_6m_m_s=3.0,shear_from_deg=30.0,
  turbulence_speed_6m_m_s=1.0,turbulence_from_deg=0.0,turbulence_seed=[23341,23342,23343,23344])
 for case in ['ground','air','wind']:
  # Simulink: the unmodified source and the builder's core copy (plant/core/build_core.m) must agree exactly.
  source=np.loadtxt(r/f'source_{case}.csv',delimiter=',');ref=np.loadtxt(r/f'core_{case}.csv',delimiter=',');u=np.loadtxt(r/f'controls_{case}.csv',delimiter=',')[:,1:]
  data,canonical=m.run(u,case!='ground',wind=wind_case if case=='wind' else None)
  expected=ref[:,1:][:,ci]*sign;ratio=np.abs(data[:,1:][:,ri]-expected)/(at+rt*np.abs(expected))
  report[case]={'status':'PASS' if np.array_equal(source,ref) and np.isfinite(data).all() and ratio.max()<=1 and np.array_equal(data[:,0],ref[:,0]) else 'FAIL','max_error_ratio':float(ratio.max()),'samples':len(data),'fields':len(ri)}
  if case=='ground':a=data;a_bytes=canonical
 data,canonical=m.run(np.loadtxt(r/'controls_ground.csv',delimiter=',')[:,1:]);report['reset']={'status':'PASS' if canonical==a_bytes else 'FAIL'}
 u=np.zeros((100,16));u[10:,0]=.3;u[10:,4]=.2;x,_=m.run(u,flags=[(0,0)]*10+[(1,1)]+[(0,0)]*89);y,_=m.run(u);u[:,5:]=np.random.default_rng(42).uniform(-1,1,(100,11));z,_=m.run(u)
 report['hold_unused']={'status':'PASS' if np.array_equal(x,y) and np.array_equal(y,z) else 'FAIL'}
 quality={'fix_type':3,'satellites':10,'eph_cm':30,'epv_cm':50};encoder=Encoder(quality);frames=[]
 for raw in a_bytes:frames+=encoder.encode(Output.from_buffer_copy(raw),1000000)
 report['wire']={'status':'PASS' if sum(k=='HIL_SENSOR' for k,v in frames)==301 and sum(k=='HIL_GPS' for k,v in frames)==13 else 'FAIL'}
 overflow=Output.from_buffer_copy(a_bytes[0]);overflow.accel_m_s2[0]=1e100
 try:Encoder(quality).encode(overflow,1000000);passed=False
 except ValueError:passed=True
 report['wire_range_rejection']={'status':'PASS' if passed else 'FAIL'}
 # Uncontrolled glide from 100 m (no controls) until it hits the ground: the divergence guard must fault (code 3)
 # instead of passing the crash on. When it hits depends on the model (6.73 s with the CG at 50 mm, 7.44 s at 65 mm,
 # 2026-10-26), so only the fault is required, within 30 s; the time and the reason are reported. Was a fixed
 # "before 7.068 s" from the original project, which a deliberate CG change broke.
 m.reset(True);i=header(Input);o=header(Output);fault=None
 for k in range(7500):
  i.step_index=k;code=m.lib.hil_model_step(C.byref(i),C.byref(o))
  if code:
   b=C.create_string_buffer(256);m.lib.hil_model_get_last_error(b,256)
   fault={'step':k,'model_time_s':k*.004,'code':code,'reason':b.value.decode()};break
 report['source_divergence_guard']={'status':'PASS' if fault and fault['code']==3 else 'FAIL','fault':fault}
 report.update(adapter_checks(cache,m))
 m.reset();worker=Worker(cache/'native'/libname('hil_worker'),m);worker.start();start=time.monotonic();trace=[]
 while time.monotonic()-start<60:
  inp=header(Input);inp.actuator_valid=1;inp.input_sequence=int((time.monotonic()-start)*1000)+1;inp.actuator_age_ns=worker.now();worker.lib.hil_worker_input(C.byref(inp));trace+=worker.drain();s=worker.snapshot()
  if s.fault:break
  time.sleep(.01)
 worker.stop();inp=header(Input);inp.actuator_valid=1;inp.input_sequence=int((time.monotonic()-start)*1000)+1;inp.actuator_age_ns=worker.now();worker.lib.hil_worker_input(C.byref(inp));trace+=worker.drain();s=worker.snapshot();a=np.array(trace,dtype=np.int64);np.savetxt(r/'native_pacing.csv',a,delimiter=',',fmt='%d')
 windows=[]
 for j in range(2500,len(a),2500):
  lo=a[j-2500];hi=a[j-1];elapsed=(hi[0]-lo[0])*.004+(hi[2]-lo[2])/1e9;windows.append(((hi[0]-lo[0])*.004)/elapsed)
 report['native_pacing']={'status':'PASS' if len(a)>=14900 and not s.fault and np.percentile(a[:,1],99)<2000000 and max(a[:,1])<4000000 and all(.99<=v<=1.01 for v in windows) else 'FAIL','samples':len(a),'wall_seconds':time.monotonic()-start,'step_us':{str(q):float(np.percentile(a[:,1],q)/1000) for q in [50,95,99,100]},'lateness_us':{str(q):float(np.percentile(a[:,2],q)/1000) for q in [50,95,99,100]},'misses':int((a[:,2]>=4000000).sum()),'rtf_10s':windows,'fault':s.fault}
 report['abi']={'status':'PASS','version':65537,'sizes':{c.__name__:C.sizeof(c) for c in [Input,Output,Info]},'capabilities':m.info.capabilities}
 report['status']='PASS' if all(v.get('status')=='PASS' for v in report.values()) else 'FAIL';(r/'validation.json').write_text(json.dumps(report,indent=2));print(json.dumps(report,indent=2),flush=True);m.lib.hil_model_terminate()
 if report['status']!='PASS':raise SystemExit(1)
if __name__=='__main__':
 p=argparse.ArgumentParser();p.add_argument('--cache',type=Path,required=True);validate(p.parse_args().cache)
