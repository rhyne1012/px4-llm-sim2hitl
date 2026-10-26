"""FC SD card files (sd-list, sd-get, sd-put, sd-rm; host/sd_files.py) against the native library and a memory
FakeFC whose MAVLink FTP server follows PX4 v1.17 mavlink_ftp.cpp. No hardware serial port."""
import hashlib
import json
from pathlib import Path
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
from host import mavftp, sd_files
from pymavlink.dialects.v20 import common as mav

EXTRAS='/fs/microsd/etc/extras.txt'
HELLO=b'# sim2hitl test\nguidance_template start\n'
LONG=b''.join(b'echo line %03d of a boot file longer than one FTP piece\n'%i for i in range(30))

def wait(predicate,seconds=3):
    end=time.monotonic()+seconds
    while time.monotonic()<end:
        if predicate():return
        time.sleep(.01)
    raise AssertionError('condition timeout')

class SdFileTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory();self.root=Path(self.temp.name);self.fc=FakeFC(RUNTIME.parent)
        self.core=Core(RUNTIME,self.fc,self.root/'log',network=False,fake_state_dir=self.root/'state')
        wait(lambda:self.core.status()['fc_ready'])
    def tearDown(self):self.core.close(force=True);self.temp.cleanup()
    def local(self,data,name='extras.txt'):
        path=self.root/'local'/name;path.parent.mkdir(exist_ok=True);path.write_bytes(data);return path
    def card(self,path=EXTRAS):return self.fc._sd()['files'].get(path)
    def seed(self,data):
        sd=self.fc._sd();sd['dirs'].add('/fs/microsd/etc');sd['files'][EXTRAS]=data
        self.fc.sd_booted={'dirs':set(sd['dirs']),'files':dict(sd['files'])}
    def reboots(self):return self.fc.command_ids.count(246)
    def journal(self,result):return json.loads(Path(result['journal']).read_text())

    def test_payload_round_trip_and_list_format(self):
        payload=mavftp.pack(65535,mavftp.WRITE,offset=480,data=b'abc')
        self.assertEqual(len(payload),251)
        got=mavftp.unpack(payload)
        self.assertEqual((got['seq'],got['opcode'],got['size'],got['offset'],got['data']),(65535,mavftp.WRITE,3,480,b'abc'))
        self.assertEqual(mavftp.parse_list(b'Fextras.txt\t31\0Dlog\0S\0'),
                         [{'type':'file','name':'extras.txt','size':31},{'type':'dir','name':'log'},{'type':'skip','name':''}])
        with self.assertRaises(ValueError):mavftp.pack(0,mavftp.WRITE,data=bytes(240))
    def test_list_and_get_are_read_only(self):
        r=self.core.sd_list('/fs/microsd')
        self.assertEqual(r['entries'],[{'type':'dir','name':'log'}]);self.assertTrue(r['app_nap_guard'])
        self.assertEqual(self.core.sd_list()['exists'],False)  # no /fs/microsd/etc on a fresh card
        # Without etc/ the real FC answers FAIL_ERRNO ENOTDIR (2026-10-17), not FILE_NOT_FOUND: still 'no file'.
        self.assertEqual(self.core.sd_get(EXTRAS,self.root/'get')['exists'],False)
        self.assertEqual(self.core.sd_get('/fs/microsd/no_dir/a/b.txt',self.root/'get')['exists'],False)
        self.fc.config['ftp_nak']={str(mavftp.OPEN_RO):1}  # any other error is still an error
        with self.assertRaisesRegex(RuntimeError,'FAIL'):self.core.sd_get(EXTRAS,self.root/'get')
        self.seed(LONG)
        g=self.core.sd_get(EXTRAS,self.root/'get')
        self.assertEqual((g['size'],g['sha256']),(len(LONG),hashlib.sha256(LONG).hexdigest()))
        self.assertEqual(Path(g['file']).read_bytes(),LONG)
        self.assertEqual(self.fc.ftp_writes,0);self.assertEqual(self.reboots(),0);self.assertIsNone(self.fc.ftp_session)
    def test_put_creates_the_boot_file_reboots_and_verifies(self):
        generation=self.core.fc_generation
        r=self.core.sd_put(self.local(LONG),EXTRAS,self.root/'out')
        self.assertEqual((r['verdict'],r['changed']),('PASS',True),r)
        self.assertEqual(self.card(),LONG);self.assertIsNone(self.card(sd_files.SD_TEMP))
        self.assertEqual(self.reboots(),1);self.assertGreater(self.core.fc_generation,generation)
        self.assertIn('mkdir /fs/microsd/etc',r['steps'])
        j=self.journal(r);self.assertEqual((j['state'],j['old_sha256'],j['new_sha256']),
                                           ('complete',None,hashlib.sha256(LONG).hexdigest()))
        folder=Path(r['transaction'])
        self.assertFalse((folder/'before/extras.txt').exists());self.assertEqual((folder/'after/extras.txt').read_bytes(),LONG)
        self.assertFalse(self.core.recovery_required)
    def test_same_content_is_a_no_op(self):
        self.seed(HELLO)
        r=self.core.sd_put(self.local(HELLO),EXTRAS,self.root/'out')
        self.assertEqual((r['verdict'],r['changed'],self.journal(r)['state']),('PASS',False,'no_op'))
        self.assertEqual((self.fc.ftp_writes,self.reboots()),(0,0))
    def test_replace_keeps_the_old_file_in_before(self):
        self.seed(HELLO)
        r=self.core.sd_put(self.local(LONG),EXTRAS,self.root/'out')
        self.assertEqual(r['verdict'],'PASS',r);self.assertEqual(self.card(),LONG)
        self.assertEqual((Path(r['transaction'])/'before/extras.txt').read_bytes(),HELLO)
        self.assertEqual(r['old_sha256'],hashlib.sha256(HELLO).hexdigest())
    def test_remove_without_the_directory_is_a_no_op(self):
        r=self.core.sd_remove(EXTRAS,self.root/'out')
        self.assertEqual((r['verdict'],r['changed']),('PASS',False));self.assertEqual((self.fc.ftp_writes,self.reboots()),(0,0))
        txn=self.core._sd_read_txn()  # the remove step itself: FAT answers ENOENT -> FILE_NOT_FOUND, 'not there'
        self.assertFalse(self.core._sd_remove(txn,EXTRAS))
    def test_remove_and_remove_again(self):
        self.seed(HELLO)
        r=self.core.sd_remove(EXTRAS,self.root/'out')
        self.assertEqual((r['verdict'],r['changed']),('PASS',True),r);self.assertIsNone(self.card());self.assertEqual(self.reboots(),1)
        r=self.core.sd_remove(EXTRAS,self.root/'out')
        self.assertEqual((r['verdict'],r['changed']),('PASS',False));self.assertEqual(self.reboots(),1)
    def test_only_the_boot_files_and_only_below_the_card(self):
        for path in ['/fs/microsd/etc/rc.txt','/fs/microsd/etc/config.txt','/fs/microsd/params','/fs/microsd/.format',
                     '/fs/microsd/etc/../etc/extras.txt','/fs/microsd/etc/./extras.txt','/fs/microsd/./etc/extras.txt',
                     '/fs/microsd/etc//extras.txt','/fs/microsd/etc/sub/extras.txt']:
            with self.assertRaisesRegex(ValueError,'only|without'):self.core.sd_put(self.local(HELLO),path,self.root/'out')
            with self.assertRaisesRegex(ValueError,'only|without'):self.core.sd_remove(path,self.root/'out')
        for path in ['/etc','/fs/microsdx','/fs/microsd/../','relative',' /fs/microsd','/fs/microsd/日誌']:
            with self.assertRaises(ValueError):self.core.sd_list(path)
        with self.assertRaisesRegex(ValueError,'more than'):self.core.sd_put(self.local(bytes(sd_files.SD_PUT_MAX+1)),EXTRAS,self.root/'o')
        self.assertNotIn('FILE_TRANSFER_PROTOCOL',self.fc.counts)
    def test_a_line_nsh_would_cut_is_not_written(self):
        # nsh warns above NSH_MAX_WORDS words a line (the command counted) and drops the words after the 19th; it reads
        # NSH_MAX_LINE_BYTES bytes of a line at a time and runs the rest as a line of its own
        fits=b'my_module start'+b' -x 1'*6+b' -y'
        self.assertEqual(sd_files.boot_file_problems(fits+b'\n# '+b'w '*40+b'\n'),[])
        with self.assertRaisesRegex(ValueError,'16 words'):self.core.sd_put(self.local(fits+b' 2\n'),EXTRAS,self.root/'o')
        with self.assertRaisesRegex(ValueError,'quotation'):self.core.sd_put(self.local(b'echo "open\n'),EXTRAS,self.root/'o')
        longest=b'echo '+b'x'*(sd_files.NSH_MAX_LINE_BYTES-5)
        self.assertEqual(sd_files.boot_file_problems(longest+b'\n'),[])
        with self.assertRaisesRegex(ValueError,'line 2: 128 bytes'):self.core.sd_put(self.local(b'\n'+longest+b'x\n'),EXTRAS,self.root/'o')
        self.assertRegex(sd_files.boot_file_problems(('# '+'註'*42).encode())[0],'128 bytes')  # 3 bytes a character, comments too
        self.assertNotIn('FILE_TRANSFER_PROTOCOL',self.fc.counts)
        for recipe in sorted((RUNTIME.parent/'deploy').glob('*/sd/etc/extras.txt')):
            self.assertEqual(sd_files.boot_file_problems(recipe.read_bytes()),[],recipe)
    def test_lost_replies_are_asked_again(self):
        self.fc.config['ftp_drop_every']=3
        r=self.core.sd_put(self.local(LONG),EXTRAS,self.root/'out')
        self.assertEqual(r['verdict'],'PASS',r);self.assertGreater(r['resends'],0);self.assertEqual(self.card(),LONG)
    def test_busy_or_closed_session_starts_the_step_again(self):
        # PX4 has one FTP session for every client of the link (QGC too): busy, or closed by another client.
        self.fc.config.update(ftp_busy=1,ftp_close_after_writes=1)
        r=self.core.sd_put(self.local(LONG),EXTRAS,self.root/'out')
        self.assertEqual(r['verdict'],'PASS',r);self.assertGreaterEqual(r['session_restarts'],2);self.assertEqual(self.card(),LONG)
        self.fc.config['ftp_busy']=99
        with self.assertRaisesRegex(RuntimeError,'NO_SESSIONS'):self.core.sd_get(EXTRAS,self.root/'get')
    def test_another_client_taking_the_session(self):
        # GPT review 16 R16-1, a known limit: PX4 has one session for every client and WRITE names no file. Another
        # client that closes ours and opens its own file for writing gets our bytes; read-only, PX4 refuses them.
        # Either way our boot file stays as it was and the result is FAIL (do not run sd-put with QGC transferring).
        victim='/fs/microsd/qgc_upload.txt'
        for mode,changed in [('wo',True),('ro',False)]:
            self.seed(HELLO);self.fc._sd()['files'][victim]=b'QGC file\n'
            self.fc.config['ftp_other_client_after_create']={'path':victim,'mode':mode}
            r=self.core.sd_put(self.local(LONG),EXTRAS,self.root/('out_'+mode))
            self.assertEqual(r['verdict'],'FAIL',r);self.assertEqual(self.card(),HELLO);self.assertIsNone(self.card(sd_files.SD_TEMP))
            self.assertEqual(self.card(victim)!=b'QGC file\n',changed,mode)
            self.fc.ftp_session=None
        self.assertEqual(self.reboots(),0)
    def test_bad_temporary_file_never_touches_the_boot_file(self):
        self.seed(HELLO)
        self.fc.config['ftp_corrupt_write']=[sd_files.SD_TEMP]
        r=self.core.sd_put(self.local(LONG),EXTRAS,self.root/'out')
        self.assertEqual(r['verdict'],'FAIL');self.assertIn('read back differs',r['error'])
        self.assertEqual(self.card(),HELLO);self.assertIsNone(self.card(sd_files.SD_TEMP));self.assertEqual(self.reboots(),0)
        self.assertEqual(self.journal(r)['state'],'rolled_back')
    def test_failure_after_the_rename_puts_the_old_file_back(self):
        self.seed(HELLO)
        self.fc.config['sd_lose_on_reboot']=1  # the new file is gone after the reboot; the rollback's survives
        r=self.core.sd_put(self.local(LONG),EXTRAS,self.root/'out')
        self.assertEqual(r['verdict'],'FAIL',r);self.assertIn('verification',r['error'])
        self.assertEqual(self.card(),HELLO);self.assertEqual(self.reboots(),2)
        self.assertEqual((Path(r['transaction'])/'rollback/extras.txt').read_bytes(),HELLO)
    def test_rollback_writes_the_old_file_back(self):
        # After the reboot the boot file holds something else (the card, or another writer): only an active
        # rollback brings the old content back.
        self.seed(HELLO)
        original=self.core._sd_reboot
        def then_change(txn):  # only after the first reboot (the one of the change, not of the rollback)
            original(txn)
            if reboot.call_count==1:self.fc._sd()['files'][EXTRAS]=b'changed by someone else\n'
        with patch.object(self.core,'_sd_reboot',side_effect=then_change) as reboot:
            r=self.core.sd_put(self.local(LONG),EXTRAS,self.root/'out')
            self.assertEqual(reboot.call_count,2)
        self.assertEqual(r['verdict'],'FAIL',r);self.assertIn('verification',r['error'])
        self.assertEqual(self.card(),HELLO);self.assertIn('rename '+sd_files.SD_TEMP+' -> '+EXTRAS,r['rollback_steps'])
    def test_failed_rename_puts_the_old_file_back(self):
        self.seed(HELLO)
        self.fc.config['ftp_nak']={str(mavftp.RENAME):1}
        r=self.core.sd_put(self.local(LONG),EXTRAS,self.root/'out')
        self.assertEqual(r['verdict'],'FAIL',r);self.assertEqual(self.card(),HELLO);self.assertIsNone(self.card(sd_files.SD_TEMP))
        self.assertEqual(self.reboots(),1)  # the boot file was removed before the rename: rebooted after the rollback
    def test_temporary_file_left_is_a_failure(self):
        self.seed(HELLO)
        self.fc.config['ftp_rename_keeps_source']=1
        r=self.core.sd_put(self.local(LONG),EXTRAS,self.root/'out')
        self.assertEqual(r['verdict'],'FAIL',r);self.assertIn('left on the card',r['error'])
        self.assertEqual(self.card(),HELLO);self.assertIsNone(self.card(sd_files.SD_TEMP))
    def test_rollback_that_cannot_finish_is_an_error(self):
        self.seed(HELLO)
        self.fc.config['sd_lose_on_reboot']=1  # the new file is gone after the reboot ...
        original=self.core._sd_reboot
        def then_corrupt(txn):  # ... and the rollback's own temporary file comes back wrong
            original(txn);self.fc.config['ftp_corrupt_write']=[sd_files.SD_TEMP]
        with patch.object(self.core,'_sd_reboot',side_effect=then_corrupt):
            with self.assertRaisesRegex(RuntimeError,'did not finish'):self.core.sd_put(self.local(LONG),EXTRAS,self.root/'out')
        folder=next((self.root/'out').iterdir())
        self.assertEqual(json.loads((folder/'journal.json').read_text())['state'],'rollback_failed')
    def test_arming_stops_without_sending_more(self):
        self.seed(HELLO)
        original=self.core._sd_remove
        def arm_first(txn,path):
            self.fc.armed=True;self.fc.next_heartbeat=0;wait(lambda:self.core.fc['armed'] is True)
            return original(txn,path)
        with patch.object(self.core,'_sd_remove',side_effect=arm_first):
            with self.assertRaisesRegex(RuntimeError,'nothing more was sent'):self.core.sd_put(self.local(LONG),EXTRAS,self.root/'out')
        sent=self.fc.counts['FILE_TRANSFER_PROTOCOL'];time.sleep(.2)
        self.assertEqual(self.fc.counts['FILE_TRANSFER_PROTOCOL'],sent);self.assertEqual(self.card(),HELLO)
        self.assertEqual(self.reboots(),0)
    @needs_model
    def test_model_running_refuses(self):
        self.core.start();wait(lambda:self.fc.counts.get('HIL_SENSOR',0)>5)
        try:
            with self.assertRaisesRegex(RuntimeError,'[Mm]odel'):self.core.sd_list()
            with self.assertRaisesRegex(RuntimeError,'model stopped'):self.core.sd_put(self.local(HELLO),EXTRAS,self.root/'out')
        finally:self.core.stop()
        self.assertNotIn('FILE_TRANSFER_PROTOCOL',self.fc.counts)
    def test_replies_to_another_client_are_not_taken(self):
        writer=mav.MAVLink(None,srcSystem=1,srcComponent=1)
        reply=mavftp.pack(8,mavftp.ACK,req_opcode=mavftp.LIST,data=b'Dlog\0')
        with self.core.fc_lock:self.core.ftp={'replies':[]}
        try:
            self.core._receive(mav.MAVLink_file_transfer_protocol_message(0,255,190,reply).pack(writer),time.monotonic())
            self.assertEqual(self.core.ftp['replies'],[])
            self.core._receive(mav.MAVLink_file_transfer_protocol_message(0,2,51,reply).pack(writer),time.monotonic())
            self.assertEqual(len(self.core.ftp['replies']),1)
        finally:
            with self.core.fc_lock:self.core.ftp=None

if __name__=='__main__':unittest.main()
