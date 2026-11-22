"""Management failures against the native library and a memory FakeFC only."""
import ctypes as C
import hashlib
import json
import struct
import os
from pathlib import Path
import socket
import subprocess
import sys
import tempfile
import time
import unittest
from unittest.mock import patch

RUNTIME=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(RUNTIME))
from platform_support import needs_model
from host.core import Core
from host.transport import FakeFC
from host.abi import Model,Worker,io_stats,io_drain
from host.release import read_release
from pymavlink.dialects.v20 import common as mav

def wait(predicate,seconds=3):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        if predicate():return
        time.sleep(.01)
    raise AssertionError('condition timeout')

class HungPilot:
    pid=999999
    def __init__(self):self.code=None;self.killed=False
    def poll(self):return self.code
    def wait(self,timeout):
        if self.code is None:raise subprocess.TimeoutExpired('test pilot',timeout)
        return self.code
    def terminate(self):pass
    def kill(self):self.killed=True;self.code=-9

@needs_model
class ManagementFaultTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.fc=FakeFC(RUNTIME.parent)
        self.core=Core(RUNTIME,self.fc,self.temp.name,network=False,fake_state_dir=Path(self.temp.name)/'state')
        wait(lambda:self.core.status()['ready_to_start_model'])
    def tearDown(self):self.core.close(force=True);self.temp.cleanup()
    def test_stop_timeout_stops_model_and_reaps_child(self):
        self.core.start();wait(lambda:self.fc.counts.get('HIL_SENSOR',0)>5)
        self.core.pilot=HungPilot()
        with self.assertRaisesRegex(RuntimeError,'stop timed out'):self.core.stop()
        count=self.fc.counts['HIL_SENSOR'];time.sleep(.05)
        self.assertEqual(count,self.fc.counts['HIL_SENSOR'])
        self.assertEqual(self.core.state,'fault');self.assertTrue(self.core.recovery_required)
        self.assertTrue(self.core.pilot.killed);self.assertFalse(self.core.external_controls_enabled)
    def test_model_stop_returns_with_complete_timing_log(self):
        # model-stop's log barrier: when stop() returns, timing.csv already holds every produced step.
        self.core.start();wait(lambda:self.fc.counts.get('HIL_SENSOR',0)>50)
        self.core.stop()
        rows=(Path(self.temp.name)/'timing.csv').read_text().splitlines()  # read at once, no waiting
        steps=[int(r.split(',')[0]) for r in rows]
        self.assertEqual(len(steps),self.core.status()['produced_steps'])
        self.assertEqual(steps,list(range(len(steps))))
        self.assertEqual(self.core.counters['log_flush_timeouts'],0)
    def test_fetch_log_gives_up_without_progress(self):
        import host.core as core_module
        self.fc.config['log_mute']=True  # LOG_ENTRY arrives, LOG_DATA never does
        with patch.object(core_module,'LOG_NO_PROGRESS_S',1.0):
            start=time.monotonic()
            with self.assertRaisesRegex(RuntimeError,'no progress'):self.core.fetch_log(Path(self.temp.name)/'fc')
        self.assertLess(time.monotonic()-start,5)
        self.assertIsNone(self.core.log_fetch)
    def test_app_nap_activity_held_from_before_worker_start_to_stop(self):
        activity=self.core.activity;activity.supported=True;seen=[]
        start=self.core.worker.start
        def checked_start():seen.append(bool(activity.token));return start()
        with patch.object(activity,'_begin',return_value=7) as begin,patch.object(activity,'_end') as end,\
             patch.object(self.core.worker,'start',side_effect=checked_start):
            self.core.start();self.assertEqual(seen,[True])  # active before the worker's first wait
            self.assertTrue(self.core.status()['scheduler']['activity']['active'])
            self.core.stop();end.assert_called_once_with(7);self.assertEqual(begin.call_count,1)
        self.assertFalse(self.core.status()['scheduler']['activity']['active'])
    def test_fc_transfers_hold_the_app_nap_guard(self):
        # 2026-10-16: with the model stopped, macOS throttled the idle owner's serial reads to ~27 ms apart and a
        # 11 MB log came at 32 instead of 740 kB/s. fetch-log and param-readback hold their own guard, nested
        # transfers share it, and it is released afterwards, also after a failure.
        seen=[];on=self.core.transfer_activity.supported  # App Nap exists on macOS only; elsewhere nothing is held
        def probe(*args,**kwargs):
            seen.append(self.core.transfer_activity.diagnostics()['active'])
            if kwargs.get('fail') or (len(args)>2 and args[2]=='fail'):raise RuntimeError('made to fail')
            return {'ok':True}
        with patch.object(self.core,'_fetch_log',side_effect=probe):
            r=self.core.fetch_log(Path(self.temp.name)/'fc')
            self.assertEqual((seen,r['app_nap_guard']),([on],True))
            self.core._transfer(lambda:self.core.fetch_log(Path(self.temp.name)/'fc'))  # nested: still held inside
            self.assertEqual(seen,[on,on])
            with self.assertRaisesRegex(RuntimeError,'made to fail'):self.core.fetch_log(Path(self.temp.name)/'fc',None,'fail')
        self.assertFalse(self.core.transfer_activity.diagnostics()['active']);self.assertEqual(self.core.transfer_depth,0)
        with patch.object(self.core,'_param_readback',side_effect=probe):self.core.param_readback(Path(self.temp.name)/'p')
        self.assertEqual(seen[-1],on);self.assertFalse(self.core.transfer_activity.diagnostics()['active'])
        self.assertIn('transfer_activity',self.core.status()['scheduler'])
    def test_param_value_bits_come_from_the_wire(self):
        # An Int32 whose bits look like a signalling NaN: a float round trip would turn 0x7f800001 into 0x7fc00001.
        import struct
        from pymavlink.generator.mavcrc import x25crc
        import host.core as core_module
        for raw, expected in [(bytes.fromhex('0100807f'), 2139095041), (bytes.fromhex('010080ff'), -8388607),
                              (struct.pack('<i', 2100), 2100)]:
            writer=mav.MAVLink(None,1,1)
            buf=bytearray(mav.MAVLink_param_value_message(b'ZZ_BITS',0.0,6,3,1).pack(writer))
            buf[10:14]=raw
            crc=x25crc(bytes(buf[1:-2]));crc.accumulate_str(struct.pack('B',mav.MAVLink_param_value_message.crc_extra))
            buf[-2:]=struct.pack('<H',crc.crc)
            message=mav.MAVLink(None).parse_buffer(bytes(buf))[0]
            self.assertEqual(core_module.param_bits(message),raw)
            self.core.param_fetch={'values':{},'by_index':{},'count':None,'activity':0,'received_at':0,'received':0,
                                   'autopilot_version':None,'log':[]}
            try:
                self.core._receive(bytes(buf),time.monotonic())
                got=self.core.param_fetch['values']['ZZ_BITS']
            finally:
                self.core.param_fetch=None
            self.assertEqual((got['value'],got['bits']),(expected,raw.hex()))
            self.assertEqual(self.core.parameters['ZZ_BITS'],expected)
    def test_param_stream_consistency(self):
        from host.core import param_consistency
        ok=[('A',0,2,6,'00000000'),('B',1,2,6,'01000000'),('C',-1,2,9,'00000000'),('A',0,2,6,'00000000')]
        self.assertEqual(param_consistency(ok,2),[])
        problems={p['problem'] for p in param_consistency(
            [('A',0,3,6,'00'),('B',0,3,6,'00'),('C',99,3,6,'00'),('A',2,0,6,'00'),('C',99,3,6,'01')],3)}
        self.assertEqual(problems,{'count_changed','index_conflict','index_out_of_range','name_index_conflict','value_changed'})
        # Review 9 D6: used -> unused (index 0, then -1) is a change too.
        self.assertEqual([p['problem'] for p in param_consistency([('A',0,1,6,'00'),('A',-1,1,6,'00')],1)],['name_index_conflict'])
    def test_param_readback_wrong_index_or_no_identity_is_incomplete(self):
        out=Path(self.temp.name)/'p'
        self.fc.config['param_force_index']={'FW_R_TC':0}  # a second name on used index 0
        r=self.core.param_readback(out)
        self.assertEqual(r['verdict'],'INCOMPLETE')
        self.assertIn('index_conflict',{p['problem'] for p in r['consistency']})
        # Only the stream check sees this one: a value changed (and announced) after it was read.
        self.fc.config={'param_change_after_list':{'FW_R_TC':0.7}}
        r=self.core.param_readback(out)
        self.assertEqual(r['verdict'],'INCOMPLETE')
        self.assertEqual([p['problem'] for p in r['consistency']],['value_changed'])
        self.assertEqual((r['used_index_missing'],r['missing'],r['identity_missing']),([],[],False))
        self.fc.config={'no_autopilot_version':True}
        r=self.core.param_readback(out)
        self.assertEqual((r['verdict'],r['identity_missing'],r['consistency']),('INCOMPLETE',True,[]))
    def test_app_nap_failure_marks_the_run_and_start_failure_releases(self):
        activity=self.core.activity;activity.supported=True
        with patch.object(activity,'_begin',side_effect=RuntimeError('activity rejected')):
            self.core.start()  # the model still starts, but the run is marked
        self.assertEqual(self.core.state,'running')
        self.assertFalse(self.core.status()['scheduler']['activity_run_ok'])
        self.assertEqual(self.core.counters['activity_failures'],1)
        self.core.stop();self.core.recover()
        with patch.object(activity,'_begin',return_value=9),patch.object(activity,'_end') as end,\
             patch.object(self.core.worker,'start',side_effect=RuntimeError('worker start failed')):
            with self.assertRaisesRegex(RuntimeError,'worker start failed'):self.core.start()
            end.assert_called_once_with(9)
        self.assertFalse(activity.diagnostics()['active'])
    def drift(self,**values):
        """Values on the fake FC (in RAM and saved) that differ from the release's set."""
        for name,value in values.items():self.fc.set_persistent(name,value)
        self.fc.px4io_seen=None  # as if PX4 booted with them (px4io_servo_disarmed: px4io's first cycle)
    def journal(self,result):return json.loads(Path(result['journal']).read_text())
    def deploy_failure(self,out):
        """param_deploy that raises: the journal of the newest transaction under out."""
        with self.assertRaises(RuntimeError) as caught:self.core.param_deploy(out)
        newest=sorted(Path(out).glob('deploy_*'))[-1]
        return str(caught.exception),json.loads((newest/'journal.json').read_text())
    def test_param_deploy_nothing_to_write(self):
        plan=self.core.param_plan(Path(self.temp.name)/'plan')
        self.assertEqual((plan['writes'],plan['blocking']),([],[]))
        r=self.core.param_deploy(Path(self.temp.name)/'d0')
        self.assertEqual((r['verdict'],r['written'],self.journal(r)['state']),('PASS',[],'no_op'))
        self.assertNotIn('PARAM_SET',self.fc.counts);self.assertNotIn(246,self.fc.command_ids)  # no reboot
    def test_param_deploy_each_run_has_its_own_directory(self):
        # Review 9 D7: a second plan / deploy into the same --out never overwrites the first one's files.
        out=Path(self.temp.name)/'same'
        a=self.core.param_plan(out);b=self.core.param_plan(out)
        self.assertNotEqual(Path(a['path']).parent,Path(b['path']).parent)
        r=self.core.param_deploy(out);self.assertEqual(self.journal(r)['plan_sha256'],
                                                       hashlib.sha256(Path(r['plan']).read_bytes()).hexdigest())
    def test_param_deploy_writes_saves_reboots_and_verifies(self):
        self.drift(SDLOG_PROFILE=1,HIL_ACT_REV=0)
        generation=self.core.fc_generation
        r=self.core.param_deploy(Path(self.temp.name)/'d1')
        self.assertEqual(r['verdict'],'PASS',r);self.assertEqual(r['written'],['HIL_ACT_REV','SDLOG_PROFILE'])
        self.assertEqual(self.fc.counts['PARAM_SET'],2)
        self.assertGreater(self.core.fc_generation,generation)  # always rebooted: the readback proves the save
        self.assertEqual((self.fc.param_saved['SDLOG_PROFILE'],self.fc.param_saved['HIL_ACT_REV']),(17,2))
        self.assertEqual(self.journal(r)['state'],'complete')
        self.assertFalse(self.core.recovery_required);self.assertIsNone(self.core.param_deploy_pending)
    def test_param_deploy_failure_restores_what_this_deploy_wrote(self):
        new17=struct.pack('<i',17).hex()
        for name,config,needle,restored in [
                ('ignored',{'param_set_ignore':{'SDLOG_PROFILE':[new17]}},'no matching PARAM_VALUE',['HIL_ACT_REV']),
                ('other writer',{'param_change_on_set':{'FW_R_TC':0.9}},'changed during the deploy',['HIL_ACT_REV','SDLOG_PROFILE']),
                # Review 9 D3: changed and changed back (A -> B -> A) is still seen, from the announcements.
                ('changed back',{'param_flap_on_set':{'FW_R_TC':[0.9,0.4]}},'changed during the deploy',['HIL_ACT_REV','SDLOG_PROFILE']),
                # Review 9 D4: a value that never reaches flash is gone after the reboot: FAIL, nothing to restore.
                ('not saved',{'param_save_fail':True},'intended',[])]:
            with self.subTest(name):
                self.fc.config=config;self.fc.other_writer_done=False;self.drift(SDLOG_PROFILE=1,HIL_ACT_REV=0,FW_R_TC=0.4)
                r=self.core.param_deploy(Path(self.temp.name)/('f_'+name.replace(' ','_')))
                self.assertEqual(r['verdict'],'FAIL',r);self.assertIn(needle,r['error'])
                self.assertEqual(r['restored'],restored)
                self.assertEqual((self.fc.param_saved['HIL_ACT_REV'],self.fc.param_saved['SDLOG_PROFILE']),(0,1))
                self.assertEqual(self.journal(r)['state'],'rolled_back')
                if name=='other writer':self.assertEqual(r['others_changed'],['FW_R_TC'])  # reported, not undone
                self.assertFalse(self.core.recovery_required)
                # Review 10 E5: FAIL keeps the deploy pending even after a complete rollback (user 2026-10-16).
                self.assertEqual(self.core.param_deploy_pending['state'],'rolled_back')
        self.fc.config={};self.drift(FW_R_TC=0.4)
        self.assert_pending_blocks_and_clears()
    def servo_release(self,disarmed={1:1425}):
        """A copy of the default release that also sets MAIN channels to servos (202, 203, ...) with their own
        disarmed values ({channel: value})."""
        import shutil
        release=Path(self.temp.name)/('servo_release_%d'%len(disarmed))
        shutil.copytree(RUNTIME.parent/'deploy/00_native',release,symlinks=True)
        config=json.loads((release/'params.json').read_text())
        for k,(channel,value) in enumerate(sorted(disarmed.items())):
            config['set']['PWM_MAIN_FUNC%d'%channel]={'value':202+k,'reason':'test'}
            config['set']['PWM_MAIN_DIS%d'%channel]={'value':value,'reason':'test'}
        (release/'params.json').write_text(json.dumps(config,indent=1))
        return release
    def test_param_deploy_px4io_sets_the_disarmed_value_of_a_new_servo(self):
        # 2026-11-22 (aircraft Cube, _flightcheck -> _hitl_surfaces): PX4's px4io sets PWM_MAIN_DISn to 1500 when
        # the channel's function goes from 0 to a servo; the deploy writes the function first, then the release's
        # disarmed value again after PX4's 1500, and PX4's announcement is not another writer.
        release=self.servo_release();self.fc.config={'px4io_servo_disarmed':True}
        self.drift(PWM_MAIN_FUNC1=0,PWM_MAIN_DIS1=1425)
        plan=self.core.param_plan(Path(self.temp.name)/'px4io_plan',release)
        names=[w['name'] for w in plan['writes']]
        self.assertEqual(names,['PWM_MAIN_FUNC1','PWM_MAIN_DIS1'])
        dis=plan['writes'][1];self.assertEqual((dis['old'],dis['new']),(1425,1425));self.assertIn('px4io',dis['px4io_reason'])
        r=self.core.param_deploy(Path(self.temp.name)/'px4io',release)
        self.assertEqual(r['verdict'],'PASS',r);self.assertEqual(r['written'],['PWM_MAIN_FUNC1','PWM_MAIN_DIS1'])
        self.assertEqual((self.fc.param_saved['PWM_MAIN_FUNC1'],self.fc.param_saved['PWM_MAIN_DIS1']),(202,1425))
        self.assertIsNone(self.core.param_deploy_pending)
        # a failure after the function write: the rollback also undoes PX4's 1500
        self.fc.config={'px4io_servo_disarmed':True,'param_save_fail':True};self.drift(PWM_MAIN_FUNC1=0,PWM_MAIN_DIS1=1425)
        r=self.core.param_deploy(Path(self.temp.name)/'px4io_fail',release)
        self.assertEqual(r['verdict'],'FAIL',r)
        self.assertEqual((self.fc.param_table['PWM_MAIN_FUNC1'][0],self.fc.param_table['PWM_MAIN_DIS1'][0]),(0,1425))
        self.fc.config={}
    def test_param_deploy_waits_for_px4io_when_the_disarmed_value_is_already_1500(self):
        # 2026-11-22, second try on the aircraft Cube: DIS already 1500 (left by the first try), so the FC shows
        # nothing to wait for; px4io looks at parameter changes once a second and set 1500 after the deploy had
        # written the release's value. The deploy waits for px4io after the function write and checks again after.
        # Two channels: px4io acts on the first function write at once and on the second about 1 s later.
        release=self.servo_release({1:1425,2:1450});self.fc.config={'px4io_servo_disarmed':True}
        self.drift(PWM_MAIN_FUNC1=0,PWM_MAIN_FUNC2=0,PWM_MAIN_DIS1=1500,PWM_MAIN_DIS2=1500)
        r=self.core.param_deploy(Path(self.temp.name)/'px4io_1500',release)
        self.assertEqual(r['verdict'],'PASS',r)
        self.assertEqual(r['written'],['PWM_MAIN_FUNC1','PWM_MAIN_FUNC2','PWM_MAIN_DIS1','PWM_MAIN_DIS2'])
        self.assertEqual([self.fc.param_saved[n] for n in ('PWM_MAIN_FUNC1','PWM_MAIN_FUNC2','PWM_MAIN_DIS1','PWM_MAIN_DIS2')],
                         [202,203,1425,1450])
        entries={e['name']:e for e in self.journal(r)['entries']}
        self.assertEqual(entries['PWM_MAIN_FUNC2']['px4io_trigger'],'PWM_MAIN_DIS2')
        for name in ('PWM_MAIN_DIS1','PWM_MAIN_DIS2'):
            self.assertNotIn('rewritten_after_px4io',entries[name])  # written after px4io, not before
        self.assertIsNone(self.core.param_deploy_pending)
        self.fc.config={}
    def test_param_deploy_never_restores_a_value_it_did_not_write(self):
        # Review 10 E2: a PARAM_VALUE has no transaction id. The FC stored another value (5) for this deploy's
        # write, or another writer's announcement (3) arrived while this deploy's write was lost: neither is
        # written over by the rollback; it does not finish and the deploy stays pending.
        new17=struct.pack('<i',17).hex();new2=struct.pack('<i',2).hex()
        for name,config,param,final in [
                ('FC stored another value',{'param_set_echo_bits':{'SDLOG_PROFILE':{new17:struct.pack('<i',5).hex()}}},
                 'SDLOG_PROFILE',5),
                ('foreign announcement',{'param_set_ignore':{'HIL_ACT_REV':[new2]},'param_flap_on_set':{'HIL_ACT_REV':[3]}},
                 'HIL_ACT_REV',3)]:
            with self.subTest(name):
                self.fc.config=config;self.fc.other_writer_done=False;self.drift(SDLOG_PROFILE=1,HIL_ACT_REV=0)
                error,journal=self.deploy_failure(Path(self.temp.name)/('e2_'+name.replace(' ','_')))
                self.assertIn('rollback did not finish',error);self.assertEqual(journal['state'],'rollback_failed')
                entry={e['name']:e for e in journal['entries']}[param]
                self.assertEqual(entry['rollback'],'foreign_value')
                self.assertEqual(self.fc.param_table[param][0],final)
                self.assertTrue(self.core.param_deploy_pending['pending'])
        self.fc.config={}
        self.assert_pending_blocks_and_clears()
    def test_param_deploy_readbacks_pass_the_gate(self):
        # Review 10 E1: armed during the readback after the reboot: the readback stops, no PASS, no rollback.
        self.drift(HIL_ACT_REV=0)
        readback=self.core.param_readback;reads=[]
        def armed_after(out,*args,**kwargs):
            if Path(out).name=='after':
                self.fc.armed=True;self.fc.next_heartbeat=0;wait(lambda:self.core.fc['armed'] is True)
            return readback(out,*args,**kwargs)
        send=self.core._send_message
        def counted(message):
            if message.get_type()=='PARAM_REQUEST_READ' and self.core.fc['armed']:reads.append(message.param_id)
            return send(message)
        with patch.object(self.core,'param_readback',side_effect=armed_after),\
             patch.object(self.core,'_send_message',side_effect=counted):
            error,journal=self.deploy_failure(Path(self.temp.name)/'e1')
        self.assertIn('FC unarmed',error);self.assertEqual(journal['state'],'stopped');self.assertEqual(reads,[])
        self.assertEqual(self.fc.counts['PARAM_SET'],1)  # the write only: no rollback while armed
        self.fc.armed=False;self.fc.next_heartbeat=0;wait(lambda:self.core.fc['armed'] is False)
        self.assert_pending_blocks_and_clears()
    def test_param_deploy_stops_on_an_unexpected_reconnection(self):
        # Review 10 E3: only the transaction's own reboot may change the connection generation. A reconnection
        # during the readback after the reboot, or before the rollback, stops: no rollback, no second reboot.
        for name in ['during the readback','before the rollback']:
            with self.subTest(name):
                self.drift(HIL_ACT_REV=0);self.fc.counts.clear();self.fc.command_ids.clear()
                readback=self.core.param_readback;verify=self.core._param_deploy_verify
                def reconnect_after(out,*args,**kwargs):
                    if Path(out).name=='after':self.core.fc_generation+=1
                    return readback(out,*args,**kwargs)
                def reconnect_then_fail(*args,**kwargs):
                    self.core.fc_generation+=1
                    return ['made to fail'],[]
                target=('param_readback',reconnect_after) if name=='during the readback' else ('_param_deploy_verify',reconnect_then_fail)
                with patch.object(self.core,target[0],side_effect=target[1]):
                    error,journal=self.deploy_failure(Path(self.temp.name)/('e3_'+name.replace(' ','_')))
                self.assertEqual(journal['state'],'stopped',error);self.assertIn('generation' if name=='during the readback' else 'reconnected',error)
                self.assertEqual(self.fc.counts['PARAM_SET'],1);self.assertEqual(self.fc.command_ids.count(246),1)
                self.assertTrue(self.core.param_deploy_pending['pending'])
                self.drift(HIL_ACT_REV=2)
                r=self.core.param_deploy(Path(self.temp.name)/('e3_clear_'+name.replace(' ','_')))
                self.assertEqual(r['verdict'],'PASS');self.assertIsNone(self.core.param_deploy_pending)
    def test_param_deploy_watches_from_the_plan(self):
        # Review 10 E4: a value changed and changed back between the plan and the writes is seen.
        self.drift(HIL_ACT_REV=0)
        def flap(plan,path):
            for value in (0.9,0.4):
                self.fc.set_persistent('FW_R_TC',value);table,used=self.fc._params()
                self.core._receive(self.fc._param_value(table,used,'FW_R_TC'),time.monotonic())
        with patch.object(self.core,'_param_plan_ready',side_effect=flap):
            r=self.core.param_deploy(Path(self.temp.name)/'e4')
        self.assertEqual(r['verdict'],'FAIL');self.assertIn('FW_R_TC',r['error'])
        self.assertEqual(r['restored'],['HIL_ACT_REV'])
        self.assert_pending_blocks_and_clears()
    def test_param_deploy_identify_keeps_the_generation(self):
        # Review 11 F1: a reconnection while the FC is being identified (AUTOPILOT_VERSION) stops the deploy;
        # the new generation is not taken over. Nothing is written.
        self.drift(HIL_ACT_REV=0)
        version=self.core._fc_version
        def reconnect_during(*args):
            value=version(*args);self.core.fc_generation+=1;return value
        with patch.object(self.core,'_fc_version',side_effect=reconnect_during):
            error,journal=self.deploy_failure(Path(self.temp.name)/'f1')
        self.assertIn('reconnected while it was being identified',error)
        self.assertEqual(journal['state'],'stopped_before_writing');self.assertNotIn('PARAM_SET',self.fc.counts)
        self.drift(HIL_ACT_REV=2)
    def test_param_deploy_no_op_checks_before_clearing(self):
        # Review 11 F2: a no-op clears the pending latch only after the same checks as a write: the plan's
        # readback passes the gate (here the FC arms during it), and nothing was announced changed (a flap).
        self.core._param_pending({'pending':True,'journal':'earlier','state':'rolled_back'})
        readback=self.core._param_readback
        def arm_during(out,*args,**kwargs):
            # Armed only while the plan's readback runs: only a gated readback can see it.
            if Path(out).name!='before':return readback(out,*args,**kwargs)
            self.fc.armed=True;self.fc.next_heartbeat=0;wait(lambda:self.core.fc['armed'] is True)
            try:return readback(out,*args,**kwargs)
            finally:self.fc.armed=False;self.fc.next_heartbeat=0;wait(lambda:self.core.fc['armed'] is False)
        with patch.object(self.core,'_param_readback',side_effect=arm_during):
            with self.assertRaisesRegex(RuntimeError,'FC unarmed'):self.core.param_deploy(Path(self.temp.name)/'f2a')
        self.assertTrue(self.core.param_deploy_pending['pending'])
        self.fc.armed=False;self.fc.next_heartbeat=0;wait(lambda:self.core.fc['armed'] is False)
        def flap(out,*args,**kwargs):
            result=readback(out,*args,**kwargs)
            for value in (0.9,0.4):
                self.fc.set_persistent('FW_R_TC',value);table,used=self.fc._params()
                self.core._receive(self.fc._param_value(table,used,'FW_R_TC'),time.monotonic())
            return result
        with patch.object(self.core,'_param_readback',side_effect=flap):
            error,journal=self.deploy_failure(Path(self.temp.name)/'f2b')
        self.assertIn('FW_R_TC',error);self.assertEqual(journal['state'],'no_op_refused')
        self.assertTrue(self.core.param_deploy_pending['pending']);self.assertNotIn('PARAM_SET',self.fc.counts)
        r=self.core.param_deploy(Path(self.temp.name)/'f2c')  # a clean no-op still clears it
        self.assertEqual(r['verdict'],'PASS');self.assertIsNone(self.core.param_deploy_pending)
    def test_param_deploy_no_op_decides_after_identifying(self):
        # Review 12 N1: the no-op's last query (AUTOPILOT_VERSION) waits; the FC arming, or a parameter announced
        # changed, while it waits keeps the latch (no_op_refused). A clean no-op still clears it.
        self.core._param_pending({'pending':True,'journal':'earlier','state':'rolled_back'})
        version=self.core._fc_version
        def arm_during(*args):
            value=version(*args);self.fc.armed=True;self.fc.next_heartbeat=0
            wait(lambda:self.core.fc['armed'] is True);return value
        with patch.object(self.core,'_fc_version',side_effect=arm_during):
            error,journal=self.deploy_failure(Path(self.temp.name)/'n1a')
        self.assertIn('FC unarmed',error);self.assertEqual(journal['state'],'no_op_refused')
        self.assertTrue(self.core.param_deploy_pending['pending'])
        self.fc.armed=False;self.fc.next_heartbeat=0;wait(lambda:self.core.fc['armed'] is False)
        def flap_during(*args):
            value=version(*args)
            for v in (0.9,0.4):
                self.fc.set_persistent('FW_R_TC',v);table,used=self.fc._params()
                self.core._receive(self.fc._param_value(table,used,'FW_R_TC'),time.monotonic())
            return value
        with patch.object(self.core,'_fc_version',side_effect=flap_during):
            error,journal=self.deploy_failure(Path(self.temp.name)/'n1b')
        self.assertIn('FW_R_TC',error);self.assertEqual(journal['state'],'no_op_refused')
        self.assertTrue(self.core.param_deploy_pending['pending']);self.assertNotIn('PARAM_SET',self.fc.counts)
        r=self.core.param_deploy(Path(self.temp.name)/'n1c')
        self.assertEqual(r['verdict'],'PASS');self.assertIsNone(self.core.param_deploy_pending)
    def test_param_deploy_write_decides_after_the_last_readback(self):
        # Review 12 N1 (the write's end): the FC arming after the last readback, before the latch is cleared,
        # stops the deploy (pending), it does not end PASS.
        self.drift(SDLOG_PROFILE=1)
        verify=self.core._param_deploy_verify
        def arm_during(*args):
            value=verify(*args);self.fc.armed=True;self.fc.next_heartbeat=0
            wait(lambda:self.core.fc['armed'] is True);return value
        with patch.object(self.core,'_param_deploy_verify',side_effect=arm_during):
            error,journal=self.deploy_failure(Path(self.temp.name)/'n1w')
        self.assertIn('FC unarmed',error);self.assertEqual(journal['state'],'stopped')
        self.assertTrue(self.core.param_deploy_pending['pending'])
        self.fc.armed=False;self.fc.next_heartbeat=0;wait(lambda:self.core.fc['armed'] is False)
        r=self.core.param_deploy(Path(self.temp.name)/'n1w2')  # the value is written: a no-op clears it
        self.assertEqual(r['verdict'],'PASS');self.assertIsNone(self.core.param_deploy_pending)
    def test_param_deploy_final_check_needs_a_fresh_heartbeat(self):
        # Review 13 R13-1: a stall inside fc_lock right before the final check (nothing is received meanwhile)
        # leaves a stale heartbeat: neither a no-op nor a write ends PASS, the latch stays.
        gate=self.core._param_txn_gate
        def stalled(txn,final=False):
            if final:time.sleep(3.3)
            return gate(txn,final=final)
        self.core._param_pending({'pending':True,'journal':'earlier','state':'rolled_back'})
        with patch.object(self.core,'_param_txn_gate',side_effect=stalled):
            error,journal=self.deploy_failure(Path(self.temp.name)/'r1a')
        self.assertIn('fresh FC heartbeat',error);self.assertEqual(journal['state'],'no_op_refused')
        self.assertTrue(self.core.param_deploy_pending['pending'])
        self.drift(SDLOG_PROFILE=1)
        with patch.object(self.core,'_param_txn_gate',side_effect=stalled):
            error,journal=self.deploy_failure(Path(self.temp.name)/'r1b')
        self.assertIn('fresh FC heartbeat',error);self.assertEqual(journal['state'],'stopped')
        self.assertTrue(self.core.param_deploy_pending['pending']);self.assertEqual(self.fc.counts['PARAM_SET'],1)
        r=self.core.param_deploy(Path(self.temp.name)/'r1c')  # the value was written and saved: a no-op clears it
        self.assertEqual(r['verdict'],'PASS');self.assertIsNone(self.core.param_deploy_pending)
    def test_param_latch_clear_outlasting_the_heartbeat_is_set_back(self):
        # Review 14 R14-1: the rename that clears the latch stalls 3.3 s after the final decision (nothing is
        # received meanwhile): the decision is too old by then, so the latch is set back and the deploy stops.
        # A slow write before the decision is fine: the decision waits for a fresh heartbeat after it.
        import host.core as core_module
        real_replace,real_write=core_module.os.replace,Path.write_text
        def slow_clear(src,dst):
            if Path(dst).name=='param_deploy.json' and '"pending": false' in Path(src).read_text():time.sleep(3.3)
            return real_replace(src,dst)
        earlier={'pending':True,'journal':'earlier','state':'rolled_back'}
        self.core._param_pending(dict(earlier))
        with patch.object(core_module.os,'replace',side_effect=slow_clear):
            error,journal=self.deploy_failure(Path(self.temp.name)/'r14a')
        self.assertIn('outlasted',error);self.assertEqual(journal['state'],'no_op_refused')
        self.assertEqual(self.core.param_deploy_pending,earlier)  # set back as it was
        self.assertEqual(json.loads(self.core.param_latch_file.read_text()),earlier)
        self.assertFalse(self.core.status()['ready_to_start_model'])
        self.drift(SDLOG_PROFILE=1)
        with patch.object(core_module.os,'replace',side_effect=slow_clear):
            error,journal=self.deploy_failure(Path(self.temp.name)/'r14b')
        self.assertIn('outlasted',error);self.assertEqual(journal['state'],'stopped')
        self.assertTrue(self.core.param_deploy_pending['pending']);self.assertEqual(self.fc.counts['PARAM_SET'],1)
        def slow_write(path,data,*args,**kwargs):
            if path.name=='param_deploy.tmp' and '"pending": false' in data:time.sleep(3.3)
            return real_write(path,data,*args,**kwargs)
        with patch.object(Path,'write_text',slow_write):
            r=self.core.param_deploy(Path(self.temp.name)/'r14c')  # slow before the decision: still PASS
        self.assertEqual(r['verdict'],'PASS');self.assertIsNone(self.core.param_deploy_pending)
        self.assertEqual(json.loads(self.core.param_latch_file.read_text()),{'pending':False})
    def test_param_latch_that_cannot_be_cleared_stays_pending(self):
        # Review 13 R13-2: the latch file cannot be written when a deploy clears it: the owner keeps it pending
        # (memory and file) and the model does not start; a write's end stops without a rollback.
        real=Path.write_text
        def failing(path,data,*args,**kwargs):
            if path.name=='param_deploy.tmp' and '"pending": false' in data:raise OSError('disk full (injected)')
            return real(path,data,*args,**kwargs)
        def blocked():
            return (self.core.param_deploy_pending['pending'],json.loads(self.core.param_latch_file.read_text())['pending'],
                    self.core.status()['ready_to_start_model'])
        self.core._param_pending({'pending':True,'journal':'earlier','state':'rolled_back'})
        with patch.object(Path,'write_text',failing):
            error,journal=self.deploy_failure(Path(self.temp.name)/'r2a')
        self.assertIn('disk full',error);self.assertEqual(journal['state'],'no_op_refused')
        self.assertEqual(blocked(),(True,True,False));self.assertNotIn('PARAM_SET',self.fc.counts)
        self.drift(SDLOG_PROFILE=1)
        with patch.object(Path,'write_text',failing):
            error,journal=self.deploy_failure(Path(self.temp.name)/'r2b')
        self.assertIn('disk full',error);self.assertEqual(journal['state'],'stopped')
        self.assertEqual(blocked(),(True,True,False));self.assertEqual(self.fc.counts['PARAM_SET'],1)  # no rollback
        # Review 14: the rename that clears the latch fails: the owner keeps it pending too.
        import host.core as core_module
        real_replace=core_module.os.replace
        def failing_rename(src,dst):
            if Path(dst).name=='param_deploy.json' and '"pending": false' in Path(src).read_text():
                raise OSError('rename failed (injected)')
            return real_replace(src,dst)
        with patch.object(core_module.os,'replace',side_effect=failing_rename):
            error,journal=self.deploy_failure(Path(self.temp.name)/'r2d')
        self.assertIn('rename failed',error);self.assertEqual(journal['state'],'no_op_refused')
        self.assertEqual(blocked(),(True,True,False))
        r=self.core.param_deploy(Path(self.temp.name)/'r2c')
        self.assertEqual(r['verdict'],'PASS');self.assertIsNone(self.core.param_deploy_pending)
        # The pending latch cannot be written when a write starts: the owner holds it pending, nothing is written.
        self.drift(HIL_ACT_REV=0);sets=self.fc.counts['PARAM_SET']
        def failing_pending(path,data,*args,**kwargs):
            if path.name=='param_deploy.tmp' and '"writing"' in data:raise OSError('disk full (injected)')
            return real(path,data,*args,**kwargs)
        with patch.object(Path,'write_text',failing_pending):
            with self.assertRaisesRegex(OSError,'disk full'):self.core.param_deploy(Path(self.temp.name)/'r2e')
        self.assertTrue(self.core.param_deploy_pending['pending']);self.assertFalse(self.core.status()['ready_to_start_model'])
        self.assertEqual(self.fc.counts['PARAM_SET'],sets)
        self.drift(HIL_ACT_REV=2)
    def test_fake_fc_needs_its_own_state_directory(self):
        # Review 12 N2: the real state directory holds the real owner's recovery marker and deploy latch.
        with self.assertRaisesRegex(ValueError,'own state directory'):
            Core(RUNTIME,FakeFC(RUNTIME.parent),Path(self.temp.name)/'nostate',network=False)
    def test_param_readback_gate_before_every_send(self):
        # Review 11 F3: the AUTOPILOT_VERSION request and the parameter list request each pass the gate.
        send=self.core._send_message;sent=[]
        def arm_after_version(message):
            sent.append(message.get_type());result=send(message)
            if message.get_type()=='COMMAND_LONG':self.core.fc['armed']=True
            return result
        txn={'identity':tuple(self.core.fc['identity']),'generation':self.core.fc_generation,'version':{}}
        with patch.object(self.core,'_send_message',side_effect=arm_after_version):
            with self.assertRaisesRegex(RuntimeError,'FC unarmed'):self.core.param_readback(Path(self.temp.name)/'f3',txn=txn)
        self.assertNotIn('PARAM_REQUEST_LIST',sent)
        self.core.fc['armed']=False
    def test_status_keeps_old_operation_results_small(self):
        # Review 11 F7 / review 12 N5: status lists every operation only as a bounded summary (scalars, strings
        # cut, at most STATUS_OPERATION_BYTES each); the whole operation stays in the owner for its client.
        for n in range(32):
            self.core.operations.append({'request_id':f'op{n}','action':'fetch-log','state':'complete','error':'e'*9000,
                                         'result':{'entries':[{'id':i,'size':i} for i in range(20000)],'newest_id':n,
                                                   'note':'x'*9000,**{f'k{k}':'y'*1000 for k in range(20)}}})
        view=self.core.status()['operations']
        self.assertEqual(len(view),32);self.assertTrue(all(o['result_summarized'] for o in view))
        self.assertTrue(all(len(json.dumps(o))<=Core.STATUS_OPERATION_BYTES for o in view))
        self.assertEqual(len(view[-1]['error']),Core.STATUS_TEXT);self.assertNotIn('result',view[-1])  # too large
        self.core.operations.append({'request_id':'small','action':'fetch-log','state':'complete','error':None,
                                     'result':{'entries':[1,2],'newest_id':5,'note':'z'*3000}})
        small=self.core.status()['operations'][-1]['result']
        self.assertEqual(small,{'newest_id':5,'note':'z'*Core.STATUS_TEXT})
        self.assertEqual(len(self.core.operations[0]['result']['entries']),20000)  # kept whole in the owner
        # Review 14 R14-4: the limit counts the bytes as sent (JSON escapes non-ASCII characters).
        self.core.operations.append({'request_id':'emoji','action':'fetch-log','state':'failed','error':'\U0001F600'*3000,
                                     'result':{'note':'x'*9000}})
        last=self.core.status()['operations'][-1]
        self.assertLessEqual(len(json.dumps(last)),Core.STATUS_OPERATION_BYTES);self.assertTrue(last['error'])
    def test_param_latch_that_cannot_be_read_counts_as_pending(self):
        # Review 10 E6: only {"pending": false, ...} is clear; an empty object, broken JSON or another shape is
        # pending at owner start (fail closed), and the owner still starts.
        latch=self.core.param_latch_file
        for n,text in enumerate(['{}','{','[]','{"pending": "no"}','{"pending": true}']):
            with self.subTest(text):
                self.core.close(force=True);latch.write_text(text)
                self.core=Core(RUNTIME,self.fc,Path(self.temp.name)/f'restart{n}',network=False,
                               fake_state_dir=Path(self.temp.name)/'state')
                wait(lambda:self.core.fc['state']=='verified')
                self.assertTrue(self.core.param_deploy_pending['pending'])
                self.assertFalse(self.core.status()['ready_to_start_model'])
                self.assertTrue(any('parameter deploy pending' in m for m in self.core.status()['missing_conditions']))
        r=self.core.param_deploy(Path(self.temp.name)/'e6')  # a deploy that ends PASS clears it
        self.assertEqual(r['verdict'],'PASS');self.assertEqual(json.loads(latch.read_text()),{'pending':False})
        self.core.close(force=True)
        self.core=Core(RUNTIME,self.fc,Path(self.temp.name)/'restart_clear',network=False,fake_state_dir=Path(self.temp.name)/'state')
        wait(lambda:self.core.status()['ready_to_start_model'])
    def test_param_deploy_does_not_overwrite_another_writers_value(self):
        # Review 9 D3: someone sets the planned parameter between the plan and the write: nothing is written over it.
        self.drift(HIL_ACT_REV=0)
        ready=self.core._param_plan_ready
        def other_writer(plan,path):ready(plan,path);self.fc.set_persistent('HIL_ACT_REV',3)
        with patch.object(self.core,'_param_plan_ready',side_effect=other_writer):
            r=self.core.param_deploy(Path(self.temp.name)/'c1')
        self.assertEqual(r['verdict'],'FAIL');self.assertIn('changed since the plan',r['error'])
        self.assertNotIn('PARAM_SET',self.fc.counts);self.assertEqual(self.fc.param_table['HIL_ACT_REV'][0],3)
        # ... and after this deploy wrote its value: the rollback leaves the foreign value, the deploy stays pending.
        self.drift(HIL_ACT_REV=0,SDLOG_PROFILE=1)
        self.fc.config={'param_set_ignore':{'SDLOG_PROFILE':[struct.pack('<i',17).hex()]},
                        'param_change_on_set_of':{'SDLOG_PROFILE':{'HIL_ACT_REV':3}}}
        error,journal=self.deploy_failure(Path(self.temp.name)/'c2')
        self.assertIn('rollback did not finish',error);self.assertEqual(journal['state'],'rollback_failed')
        self.assertEqual(self.fc.param_table['HIL_ACT_REV'][0],3)
        self.fc.config={}
        self.assert_pending_blocks_and_clears()
    def assert_pending_blocks_and_clears(self):
        # Review 9 D5: a pending deploy refuses model start (and so takeoff) until a param-deploy ends PASS.
        latch=json.loads(self.core.param_latch_file.read_text())
        self.assertTrue(latch['pending'])
        status=self.core.status()
        self.assertFalse(status['ready_to_start_model'])
        self.assertTrue(any('parameter deploy pending' in m for m in status['missing_conditions']))
        with self.assertRaisesRegex(RuntimeError,'parameter deploy pending'):self.core.start()
        self.drift(HIL_ACT_REV=2,SDLOG_PROFILE=17)  # the FC matches the release again: the next deploy is a no-op
        r=self.core.param_deploy(Path(self.temp.name)/'clear')
        self.assertEqual((r['verdict'],r['written']),('PASS',[]))
        self.assertIsNone(self.core.param_deploy_pending);self.assertFalse(json.loads(self.core.param_latch_file.read_text())['pending'])
        self.assertTrue(self.core.status()['ready_to_start_model'])
    def test_param_deploy_stops_for_another_fc(self):
        # Review 9 D1: the FC behind the link is not the planned one (uid): stop before writing anything.
        self.drift(HIL_ACT_REV=0)
        ready=self.core._param_plan_ready
        def swapped(plan,path):ready(plan,path);self.fc.config={'autopilot_uid':202}
        with patch.object(self.core,'_param_plan_ready',side_effect=swapped):
            error,journal=self.deploy_failure(Path(self.temp.name)/'u1')
        self.assertIn('not the planned FC',error);self.assertEqual(journal['state'],'stopped_before_writing')
        self.assertNotIn('PARAM_SET',self.fc.counts);self.assertIsNone(self.core.param_deploy_pending)
        self.fc.config={};self.drift(HIL_ACT_REV=2)
    def test_param_deploy_stops_when_the_fc_arms(self):
        # Review 9 D2: armed after the first write: nothing more is written, no rollback, the deploy is pending.
        self.drift(SDLOG_PROFILE=1,HIL_ACT_REV=0)
        write=self.core._param_set
        def then_arm(*args,**kwargs):
            write(*args,**kwargs);self.fc.armed=True;self.fc.next_heartbeat=0
            wait(lambda:self.core.fc['armed'] is True)
        with patch.object(self.core,'_param_set',side_effect=then_arm):
            error,journal=self.deploy_failure(Path(self.temp.name)/'a1')
        self.assertIn('FC unarmed',error);self.assertEqual(journal['state'],'stopped')
        self.assertEqual(self.fc.counts['PARAM_SET'],1)
        self.assertEqual([e['status'] for e in journal['entries']],['written','pending'])
        self.fc.armed=False;self.fc.next_heartbeat=0;wait(lambda:self.core.fc['armed'] is False)
        self.assert_pending_blocks_and_clears()
    def test_param_deploy_refuses(self):
        self.core.start()
        with self.assertRaisesRegex(RuntimeError,'model stopped'):self.core.param_deploy(Path(self.temp.name)/'r0')
        self.core.stop();self.core.recover()
        self.drift(CA_AIRFRAME=0)  # an airframe value is checked, never written by deploy
        with self.assertRaisesRegex(RuntimeError,'not written by deploy'):self.core.param_deploy(Path(self.temp.name)/'r1')
        self.assertNotIn('PARAM_SET',self.fc.counts)
        self.drift(CA_AIRFRAME=1)
        self.fc.config={'no_autopilot_version':True}
        with self.assertRaisesRegex(RuntimeError,'identity'):self.core.param_deploy(Path(self.temp.name)/'r2')
        self.fc.config={}
    def test_param_set_sends_the_exact_bytes(self):
        # A float round trip would send 0x7fc00001 instead; the FC's answer must match the bytes sent.
        self.fc._params()
        txn={'identity':tuple(self.core.fc['identity']),'generation':self.core.fc_generation}
        self.core._param_set(txn,'SDLOG_PROFILE',6,bytes.fromhex('0100807f'))
        self.assertEqual(self.fc.param_table['SDLOG_PROFILE'][0],2139095041)
        self.fc.param_table['SDLOG_PROFILE'][0]=17
    def test_param_readback_gives_up_without_any_reply(self):
        import host.core as core_module
        self.fc.config['param_mute']=True  # neither the list nor any name is answered
        with patch.object(core_module,'PARAM_NO_PROGRESS_S',1.0):
            start=time.monotonic()
            with self.assertRaisesRegex(RuntimeError,'no PARAM_VALUE'):self.core.param_readback(Path(self.temp.name)/'p')
        self.assertLess(time.monotonic()-start,5)
        self.assertIsNone(self.core.param_fetch)
    def test_recover_timeout_never_reboots_and_model_stops(self):
        self.core.start();self.core.pilot=HungPilot()
        with self.assertRaises(RuntimeError):self.core.recover()
        self.assertEqual(self.fc.command_ids,[]);self.assertEqual(self.core.recovery,'failed')
        self.assertFalse(self.core.worker.snapshot().running)
    def test_force_close_finishes_after_pilot_timeout(self):
        self.core.start();self.core.pilot=HungPilot();self.core.close(force=True)
        self.assertTrue(self.core.quit.is_set());self.assertFalse(self.core.io.is_alive())
        self.assertFalse(self.core.logger.is_alive());self.assertEqual(self.core.recovery,'failed')
    def test_negative_ack_beats_fresh_heartbeat_and_other_ack(self):
        for result in [1,2,3,4,6,7,8,9]:
            with self.subTest(result=result):
                self.core._recover_command([1,1],400,0,0,0,0,0,0,0)
                writer=mav.MAVLink(None,srcSystem=1,srcComponent=1)
                raw=b''.join(m.pack(writer) for m in [mav.MAVLink_command_ack_message(400,result),mav.MAVLink_heartbeat_message(1,12,0,7<<16,3,3),mav.MAVLink_command_ack_message(512,0),mav.MAVLink_command_ack_message(400,0)])
                self.core._receive(raw,time.monotonic())
                with self.assertRaisesRegex(RuntimeError,'rejected'):self.core._wait(lambda:True,.1,'timeout')
                self.assertEqual(self.core.recover_context['rejected'],result)
    def test_foreign_ack_target_and_connection_generation_not_accepted(self):
        self.core._recover_command([1,1],400,0,0,0,0,0,0,0)
        writer=mav.MAVLink(None,srcSystem=1,srcComponent=1)
        self.core._receive(mav.MAVLink_command_ack_message(400,0,target_system=254,target_component=190).pack(writer),time.monotonic())
        self.assertIsNone(self.core.recover_context['ack_result'])
        self.core.fc_generation+=1
        self.core._receive(mav.MAVLink_command_ack_message(400,0).pack(writer),time.monotonic())
        with self.assertRaisesRegex(RuntimeError,'connection changed'):self.core._wait(lambda:True,.1,'timeout')
    def test_gate_forwards_everything_while_controls_disabled(self):
        # HIL drives no hardware: QGC and agent traffic reaches the FC in every state.
        self.core.start()
        receiver=socket.socket(socket.AF_INET,socket.SOCK_DGRAM);receiver.bind(('127.0.0.1',0));receiver.setblocking(False)
        sender=socket.socket(socket.AF_INET,socket.SOCK_DGRAM)
        self.core.routes={'qgc':(receiver,('127.0.0.1',1))}
        try:
            w=mav.MAVLink(None,srcSystem=255,srcComponent=190)
            messages=[mav.MAVLink_param_set_message(1,1,b'SDLOG_PROFILE',17,6),
                      mav.MAVLink_log_request_list_message(1,1,0,0xffff),mav.MAVLink_file_transfer_protocol_message(0,1,1,bytes(251)),
                      mav.MAVLink_set_mode_message(1,1,4),mav.MAVLink_manual_control_message(1,0,0,500,0,0),
                      mav.MAVLink_command_long_message(1,1,400,0,1,0,0,0,0,0,0),mav.MAVLink_command_long_message(1,1,176,0,1,4,0,0,0,0,0)]
            for index,(state,recovery) in enumerate([('stopped','idle'),('stopped','disarming'),('fault','idle')]):
                self.core._block_external('test');self.core.state=state;self.core.recovery=recovery
                before=dict(self.fc.counts);ids=len(self.fc.command_ids)
                sender.sendto(b''.join(m.pack(w) for m in messages),receiver.getsockname());self.core._route_inputs(time.monotonic())
                # The owner IO thread may consume the UDP frame before this test thread.
                wait(lambda:len(self.fc.command_ids)>=ids+2)
                for name in ['PARAM_SET','LOG_REQUEST_LIST','FILE_TRANSFER_PROTOCOL','SET_MODE','MANUAL_CONTROL']:
                    self.assertEqual(self.fc.counts.get(name,0),before.get(name,0)+1,(state,recovery,name))
                self.assertEqual(self.fc.command_ids[ids:],[400,176])
            self.assertEqual(self.core.counters['blocked_external_control'],0)
        finally:sender.close();receiver.close();self.core.routes={}
    def test_explicit_stopped_hil_force_disarm_after_denial(self):
        self.fc.armed=True;self.fc.config['reject_normal_disarm']=True
        wait(lambda:self.core.fc['armed'] is True)
        self.core.recover(allow_hil_force_disarm=True)
        self.assertEqual(self.fc.command_ids,[400,400,246])
        self.assertTrue(self.core.recovery_details['force_disarm_used'])
        self.assertTrue(self.core.status()['ready_after_recovery'])
        self.assertFalse(self.core.recovery_required)
    def test_force_disarm_is_opt_in_and_second_rejection_stops_reboot(self):
        self.fc.armed=True;self.fc.config['reject_normal_disarm']=True
        wait(lambda:self.core.fc['armed'] is True)
        with self.assertRaisesRegex(RuntimeError,'rejected'):self.core.recover()
        self.assertEqual(self.fc.command_ids,[400])
        self.fc.config['reject_force_disarm']=True
        with self.assertRaisesRegex(RuntimeError,'rejected'):self.core.recover(allow_hil_force_disarm=True)
        self.assertEqual(self.fc.command_ids,[400,400,400])
        self.assertTrue(self.core.recovery_required)
        self.assertEqual(self.core.recovery,'failed')
    def test_force_disarm_not_used_for_unsupported_ack(self):
        self.fc.armed=True;self.fc.behavior='reject';self.fc.config['reject_result']=3
        wait(lambda:self.core.fc['armed'] is True)
        with self.assertRaisesRegex(RuntimeError,'rejected'):self.core.recover(allow_hil_force_disarm=True)
        self.assertEqual(self.fc.command_ids,[400])
        self.assertFalse(self.core.recovery_details['force_disarm_used'])


@needs_model
class NativeBarrierTests(unittest.TestCase):
    def test_command_backlog_purged_and_inflight_write_is_bounded(self):
        release,manifest=read_release(RUNTIME);model=Model(release/manifest['library']);worker=Worker(release/manifest['worker'],model)
        read_fd,write_fd=os.pipe();os.set_blocking(read_fd,False);os.set_blocking(write_fd,False)
        try:
            while True:
                try:os.write(write_fd,b'X'*4096)
                except BlockingIOError:break
            self.assertEqual(worker.lib.hil_io_start(write_fd),0)
            for _ in range(10):self.assertEqual(worker.lib.hil_io_command(b'OLD',3),0)
            time.sleep(.01);start=time.monotonic();worker.lib.hil_io_clear_commands()
            self.assertLess(time.monotonic()-start,.3)
            while True:
                try:os.read(read_fd,65536)
                except BlockingIOError:break
            self.assertEqual(worker.lib.hil_io_command(b'NEW',3),0)
            wait(lambda:io_stats(worker)['commands']==1)
            self.assertEqual(os.read(read_fd,65536),b'NEW')
            self.assertEqual([r[2] for r in io_drain(worker)], [b'NEW'])
        finally:worker.lib.hil_io_stop();os.close(read_fd);os.close(write_fd);model.lib.hil_model_terminate()

if __name__=='__main__':unittest.main(verbosity=2)
