#!/usr/bin/env python3
"""A PX4 flight controller over MAVLink: identity, parameters, SD card files, logs, disarm, reboot and recover.

    <python with pymavlink> tools/fc.py --link /dev/serial/by-id/<the FC> identity
    ... params-read [--firmware-params <parameters.json.xz>] --out <readback.json>
    ... sd-list [PATH] | sd-get PATH --out DIR | sd-put PATH FILE | sd-rm PATH
    ... logs | log-get [--id N] --out FILE.ulg
    ... recover [--force-disarm] [--expect-hitl 0|1]
    ... params-restore --from <readback.json>     put every parameter back as a saved readback had it (exact bytes)

--link is a serial device (a /dev path, at --baud) or a pymavlink UDP address (udpout:127.0.0.1:14612 for simhost's
MAVLink relay, which serves every peer it heard in the last 10 s; this tool sends a GCS heartbeat every second).
Nothing here changes a parameter except FC.set(); tools/deploy.py is the tool that writes a recipe.

Parameter values travel in a float field. A Python float would change an Int32 whose bits look like a signalling NaN,
so values are read from, and written into, the packet bytes. Every write waits for the FC's PARAM_VALUE with the same
name, type and bytes. A full readback asks for the parameter list, asks again for the indices that did not come, then
asks by name for every name of the firmware's parameter list that did not come (PX4 lists only the used parameters),
in batches, with rounds of asking again (PX4 drops a reply when its send buffer is full, and does not answer an
unknown name at all).
"""
import argparse
import hashlib
import json
import os
import math
import struct
import sys
import time
from pathlib import Path, PurePosixPath

from pymavlink import mavutil
from pymavlink.generator.mavcrc import x25crc

sys.path.insert(0, str(Path(__file__).resolve().parent))
import mavftp  # noqa: E402

mav = mavutil.mavlink
SOURCE = (254, 190)
FORCE_DISARM = 21196            # MAV_CMD_COMPONENT_ARM_DISARM param2: PX4's force (in HITL, also while "flying")
PARAM_BATCH = 20                # PARAM_REQUEST_READ in flight at once
PARAM_ROUNDS = 5                # rounds of asking again for what did not answer
PARAM_QUIET_S = 0.5             # a batch (or the list stream) is over after this long without a PARAM_VALUE
PARAM_NO_PROGRESS_S = 15.0      # no PARAM_VALUE at all this long after the list request: give up
PARAM_SET_TRIES = 3
PARAM_SET_WAIT_S = 2.0
PARAM_SAVE_WAIT_S = 3.0         # after the last write, before a reboot: PX4 autosaves >= 300 ms later, at most every 2 s
RECONNECT_S = 45.0              # a reboot: the USB port back and a heartbeat
FTP_WAIT_S = 1.5                # one FTP request: the reply within this long, or the same request again
FTP_TRIES = 3
FTP_SESSION_TRIES = 3           # PX4 has one FTP session for every client of a link: busy -> start the step again
LOG_CHUNK = 90


class FCError(RuntimeError):
    pass


class FTPBusy(FCError):
    """PX4's only FTP session is held by another client (QGC), or was closed under us."""


# -- the value bytes of PARAM_VALUE / PARAM_SET ----------------------------------------------------------------------
def _payload_start(buf):
    return 10 if buf[:1] == b'\xfd' else 6   # MAVLink 2 / MAVLink 1 header


def param_bits(message):
    """The 4 value bytes of a parsed PARAM_VALUE or PARAM_SET, from the packet (MAVLink 2 truncates trailing zero
    bytes of a payload: a short one is padded with zeros)."""
    buf = bytes(message.get_msgbuf())
    start = _payload_start(buf)
    return buf[start:start + buf[1]][:4].ljust(4, b'\0')


def with_bits(packet, bits, crc_extra):
    """An unsigned packed PARAM_SET with its value bytes replaced and the CRC recomputed."""
    buf = bytearray(packet)
    if buf[:1] == b'\xfd' and buf[2] & 1:
        raise ValueError('signed MAVLink packets are not rewritten')
    start, length = _payload_start(buf), buf[1]
    if length < 4:
        raise ValueError('payload shorter than the value field')
    buf[start:start + 4] = bits
    crc = x25crc(bytes(buf[1:start + length]))
    crc.accumulate(struct.pack('B', crc_extra))
    buf[start + length:start + length + 2] = struct.pack('<H', crc.crc)
    return bytes(buf)


def encode(kind, value):
    """The bits of a value of MAVLink param_type kind (6 Int32, 9 Float)."""
    if kind == 6:
        return struct.pack('<i', int(value))
    if kind == 9:
        return struct.pack('<f', float(value))
    raise ValueError(f'parameter type {kind}: only Int32 (6) and Float (9) are PX4 parameter types')


def decode(kind, bits):
    value = struct.unpack('<i' if kind == 6 else '<f', bits)[0]
    return value if kind == 6 or math.isfinite(value) else None   # JSON has no NaN: the bits keep it


def version_of(m):
    """AUTOPILOT_VERSION as the toolkit records it. PX4 (mavlink_main.cpp) puts the first 5 bytes of its git hash,
    little-endian, in the top 5 bytes of flight_custom_version (the low 3 bytes are the vendor version), and the first
    8 bytes of the NuttX commit, little-endian, in os_custom_version."""
    custom = bytes(m.flight_custom_version)
    sw = m.flight_sw_version
    return {'flight_sw_version': sw, 'px4_version': f'{sw >> 24 & 255}.{sw >> 16 & 255}.{sw >> 8 & 255}',
            'board_version': m.board_version, 'git_hash_prefix': custom[3:][::-1].hex(),
            'os_hash_prefix': bytes(m.os_custom_version)[::-1].hex(), 'vendor_id': m.vendor_id,
            'product_id': m.product_id, 'uid': m.uid}


def consistency(stream, count):
    """Problems of a readback's PARAM_VALUE stream (name, index, count, type, bits per message): one name per used
    index, below count; a name keeps one index (-1 = unused), type and value; count does not change."""
    problems = []
    counts = sorted({e[2] for e in stream})
    if len(counts) > 1:
        problems.append({'problem': 'count changed', 'counts': counts})
    names_at, index_of, value_of = {}, {}, {}
    for name, index, _, kind, bits in stream:
        if index >= 0:
            names_at.setdefault(index, set()).add(name)
        index_of.setdefault(name, set()).add(index)
        value_of.setdefault(name, set()).add((kind, bits))
    for index, names in sorted(names_at.items()):
        if len(names) > 1:
            problems.append({'problem': 'index conflict', 'index': index, 'names': sorted(names)})
        if count is None or index >= count:
            problems.append({'problem': 'index out of range', 'index': index, 'count': count})
    for name in sorted(index_of):
        if len(index_of[name]) > 1:
            problems.append({'problem': 'name index conflict', 'name': name, 'indices': sorted(index_of[name])})
        if len(value_of[name]) > 1:   # e.g. changed by QGC during the readback
            problems.append({'problem': 'value changed', 'name': name, 'seen': sorted(value_of[name])})
    return problems


class FC:
    def __init__(self, link, baud=2000000, log=None):
        self.link, self.baud = link, baud
        self.serial = not link.startswith(('udp', 'tcp'))
        self.log = log                  # a list that collects (time, what, details) of every write and command
        self.m = None
        self.target = None              # (system, component) of the autopilot
        self.heartbeat_at = None
        self.armed = None
        self.version = None
        self._sent_heartbeat = 0.0
        self._ftp_seq = int.from_bytes(hashlib.sha256(str(time.time()).encode()).digest()[:2], 'little') & 0x7FFF

    # -- the link ------------------------------------------------------------------------------------------------------
    def connect(self, timeout=30.0):
        """Open the link and wait for the autopilot's heartbeat (a port that is not there yet is tried again)."""
        end = time.monotonic() + timeout
        last = None
        while time.monotonic() < end:
            try:
                self.m = mavutil.mavlink_connection(self.link, baud=self.baud, source_system=SOURCE[0],
                                                    source_component=SOURCE[1], autoreconnect=False)
                self.m.mav.robust_parsing = True
                got = self.wait(lambda msg: msg.get_type() == 'HEARTBEAT' and msg.autopilot == mav.MAV_AUTOPILOT_PX4,
                                min(5.0, max(0.5, end - time.monotonic())), any_source=True)
                if got:
                    self.target = (got.get_srcSystem(), got.get_srcComponent())
                    self._note(got)
                    return self
                self.close()
            except (OSError, ValueError) as exc:  # the port is not back yet after a reboot
                last = exc
                self.close()
            time.sleep(1.0)
        raise FCError(f'no PX4 heartbeat on {self.link} within {timeout:.0f} s' + (f' ({last})' if last else ''))

    def close(self):
        if self.m is not None:
            try:
                self.m.close()
            except Exception:  # noqa: BLE001
                pass
        self.m = None

    def _note(self, msg):
        if (msg.get_type() == 'HEARTBEAT' and self.target and (msg.get_srcSystem(), msg.get_srcComponent()) == self.target):
            self.heartbeat_at = time.monotonic()
            self.armed = bool(msg.base_mode & mav.MAV_MODE_FLAG_SAFETY_ARMED)

    def _recv(self, timeout):
        now = time.monotonic()
        if now - self._sent_heartbeat > 1.0:
            self._sent_heartbeat = now
            self.m.mav.heartbeat_send(mav.MAV_TYPE_GCS, mav.MAV_AUTOPILOT_INVALID, 0, 0, 0)
        msg = self.m.recv_match(blocking=True, timeout=timeout)
        if msg is None or msg.get_type() == 'BAD_DATA':
            return None
        self._note(msg)
        return msg

    def wait(self, match, timeout, any_source=False):
        """The first message for which match(msg) is true, within timeout seconds, or None. Messages from other systems
        than the autopilot are skipped (any_source: not)."""
        end = time.monotonic() + timeout
        while True:
            left = end - time.monotonic()
            if left <= 0:
                return None
            msg = self._recv(min(left, 0.2))
            if msg is None:
                continue
            if not any_source and self.target and msg.get_srcSystem() != self.target[0]:
                continue
            if match(msg):
                return msg

    def drain(self, seconds):
        self.wait(lambda msg: False, seconds)

    def record(self, what, **details):
        if self.log is not None:
            self.log.append(dict({'time_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'what': what}, **details))

    # -- identity and commands -----------------------------------------------------------------------------------------
    def identity(self, tries=3):
        """A fresh AUTOPILOT_VERSION (version_of) and the armed state of the last heartbeat."""
        for _ in range(tries):
            self.m.mav.command_long_send(*self.target, mav.MAV_CMD_REQUEST_MESSAGE, 0,
                                         mav.MAVLINK_MSG_ID_AUTOPILOT_VERSION, 0, 0, 0, 0, 0, 0)
            got = self.wait(lambda msg: msg.get_type() == 'AUTOPILOT_VERSION', 2.0)
            if got:
                self.version = version_of(got)
                if self.heartbeat_at is None or time.monotonic() - self.heartbeat_at > 3:
                    self.wait(lambda msg: msg.get_type() == 'HEARTBEAT' and
                              (msg.get_srcSystem(), msg.get_srcComponent()) == self.target, 3.0)
                return dict(self.version, armed=self.armed)
        raise FCError('the FC did not answer AUTOPILOT_VERSION')

    def command(self, cmd, *params, wait=3.0, tries=2):
        """COMMAND_LONG; the MAV_RESULT of its COMMAND_ACK (None: no answer)."""
        params = list(params) + [0] * (7 - len(params))
        result = None
        for attempt in range(tries):
            self.m.mav.command_long_send(*self.target, cmd, attempt, *params)
            ack = self.wait(lambda msg: msg.get_type() == 'COMMAND_ACK' and msg.command == cmd, wait)
            if ack is not None:
                result = ack.result
                if result != mav.MAV_RESULT_IN_PROGRESS:
                    break
        self.record('command', command=cmd, params=params, result=result)
        return result

    def fresh_heartbeat(self, after, timeout=5.0):
        """A heartbeat of the autopilot later than monotonic time after; its armed state."""
        got = self.wait(lambda msg: msg.get_type() == 'HEARTBEAT' and (msg.get_srcSystem(), msg.get_srcComponent()) ==
                        self.target and time.monotonic() > after, timeout)
        if got is None:
            raise FCError('no fresh heartbeat')
        return self.armed

    def disarm(self, force=False):
        """Disarm; force: PX4's force disarm (only after a normal disarm was refused). Returns what was done."""
        if self.armed is False:
            return {'disarm': 'already disarmed'}
        sent = time.monotonic()
        result = self.command(mav.MAV_CMD_COMPONENT_ARM_DISARM, 0)
        if result == mav.MAV_RESULT_ACCEPTED and self.fresh_heartbeat(sent) is False:
            return {'disarm': 'disarmed'}
        if not force:
            raise FCError(f'disarm refused (result {result}); force disarm not allowed')
        sent = time.monotonic()
        forced = self.command(mav.MAV_CMD_COMPONENT_ARM_DISARM, 0, FORCE_DISARM)
        if forced != mav.MAV_RESULT_ACCEPTED or self.fresh_heartbeat(sent) is not False:
            raise FCError(f'force disarm failed (result {forced}, armed {self.armed})')
        return {'disarm': 'force disarmed', 'normal_result': result}

    def boot_ms(self):
        """The FC's time since boot (SYSTEM_TIME.time_boot_ms, asked for), or None when it does not answer."""
        for _ in range(3):
            self.m.mav.command_long_send(*self.target, mav.MAV_CMD_REQUEST_MESSAGE, 0, mav.MAVLINK_MSG_ID_SYSTEM_TIME,
                                         0, 0, 0, 0, 0, 0)
            got = self.wait(lambda msg: msg.get_type() == 'SYSTEM_TIME', 2.0)
            if got is not None:
                return int(got.time_boot_ms)
        return None

    def reboot(self, wait_save=True):
        """Reboot (a serial FC: the USB port goes away and comes back) and connect again; the same board (uid) must
        answer, and it must have rebooted: an explicit refusal fails, and its time since boot must have started again
        (or, if the FC gives no boot time, the command must have been accepted). wait_save: wait PARAM_SAVE_WAIT_S first,
        so PX4 has saved the last parameter change."""
        if not self.serial:
            raise FCError('reboot over a UDP link: a SITL FC is restarted by tools/sitl_fc.py instead')
        if self.armed is not False:
            raise FCError('refusing to reboot an armed FC')
        uid = (self.version or self.identity())['uid']
        if wait_save:
            self.drain(PARAM_SAVE_WAIT_S)
        before = self.boot_ms()
        result = self.command(mav.MAV_CMD_PREFLIGHT_REBOOT_SHUTDOWN, 1, wait=2.0, tries=1)
        self.record('reboot', result=result, boot_ms_before=before)
        if result not in (None, mav.MAV_RESULT_ACCEPTED, mav.MAV_RESULT_IN_PROGRESS):
            raise FCError(f'the FC refused the reboot (MAV_RESULT {result})')
        self.close()
        time.sleep(3.0)
        self.connect(RECONNECT_S)
        now = self.identity()
        if now['uid'] != uid:
            raise FCError(f'after the reboot another board answers (uid {now["uid"]}, was {uid})')
        if now['armed'] is not False:
            raise FCError('armed after the reboot')
        after = self.boot_ms()
        self.record('rebooted', boot_ms_before=before, boot_ms_after=after)
        if before is not None and after is not None:
            if after >= before:
                raise FCError(f'the FC did not reboot: its time since boot went on ({before} ms, then {after} ms)')
        elif result != mav.MAV_RESULT_ACCEPTED:
            raise FCError('no evidence of a reboot: the command was not acknowledged and the FC gives no boot time')
        return dict(now, boot_ms_before=before, boot_ms_after=after)

    def recover(self, force_disarm=False, expect_hitl=None):
        """The standard recover: disarm (force only if allowed and a normal disarm was refused), reboot, and the FC
        back unarmed (with SYS_HITL as expected, when given)."""
        if self.heartbeat_at is None or time.monotonic() - self.heartbeat_at > 3:
            self.fresh_heartbeat(time.monotonic() - 3)
        if expect_hitl is not None and self.get('SYS_HITL') != expect_hitl:
            raise FCError(f'SYS_HITL is not {expect_hitl}: not the FC state this recover is for')
        done = self.disarm(force=force_disarm)
        done['after_reboot'] = self.reboot(wait_save=False)
        if expect_hitl is not None:
            hitl = self.get('SYS_HITL')
            if hitl != expect_hitl:
                raise FCError(f'SYS_HITL {hitl} after the reboot, expected {expect_hitl}')
            done['SYS_HITL'] = hitl
        done['recover'] = 'complete'
        return done

    # -- parameters ----------------------------------------------------------------------------------------------------
    def _param_value(self, msg, name=None):
        return msg.get_type() == 'PARAM_VALUE' and (name is None or msg.param_id == name)

    def read(self, name, tries=PARAM_SET_TRIES):
        """(type, bits) of one parameter, asked by name."""
        for _ in range(tries):
            self.m.mav.param_request_read_send(*self.target, name.encode(), -1)
            got = self.wait(lambda msg: self._param_value(msg, name), PARAM_SET_WAIT_S)
            if got:
                return got.param_type, param_bits(got)
        raise FCError(f'{name}: no PARAM_VALUE')

    def get(self, name):
        kind, bits = self.read(name)
        return decode(kind, bits)

    def set(self, name, kind, value):
        """PARAM_SET with the exact bytes; returns when the FC answers with the same name, type and bytes. That says
        the value is in RAM: a reboot and a readback prove it was saved."""
        return self.set_bits(name, kind, encode(kind, value), value)

    def set_bits(self, name, kind, bits, value=None):
        """PARAM_SET of these 4 value bytes (see set)."""
        message = mav.MAVLink_param_set_message(*self.target, name.encode(), 0.0, kind)
        answers = []
        for _ in range(PARAM_SET_TRIES):
            raw = message.pack(self.m.mav)
            self.m.mav.seq = (self.m.mav.seq + 1) % 256
            self.m.write(with_bits(raw, bits, message.crc_extra))
            end = time.monotonic() + PARAM_SET_WAIT_S
            while time.monotonic() < end:
                got = self.wait(lambda msg: self._param_value(msg, name), end - time.monotonic())
                if got is None:
                    break
                answers.append((got.param_type, param_bits(got).hex()))
                if got.param_type == kind and param_bits(got) == bits:
                    self.record('param set', name=name, type=kind, value=value if value is not None else decode(kind, bits),
                                bits=bits.hex())
                    return answers
        raise FCError(f'{name}: no matching PARAM_VALUE after {PARAM_SET_TRIES} PARAM_SET (sent {bits.hex()}, '
                      f'answers {answers[-3:]})')

    def read_all(self, firmware_names=()):
        """Every parameter: the list, then the missing indices, then every name of firmware_names that did not come.
        Returns the readback (the format tools/recipe.py Recipe.check takes)."""
        started = time.monotonic()
        values, by_index, stream = {}, {}, []
        state = {'count': None, 'last': started, 'version': None}
        requests = 0

        def take(msg):
            t = msg.get_type()
            if t == 'AUTOPILOT_VERSION':
                state['version'] = version_of(msg)
            elif t == 'PARAM_VALUE' and not msg.param_id.startswith('_'):   # _HASH_CHECK is not a parameter
                bits = param_bits(msg)
                name = msg.param_id
                index = -1 if msg.param_index == 0xFFFF else msg.param_index   # -1 (unused) is 65535 on the wire
                values[name] = {'name': name, 'type': msg.param_type, 'value': decode(msg.param_type, bits),
                                'bits': bits.hex(), 'index': index}
                if index >= 0:
                    by_index[index] = name
                stream.append((name, index, msg.param_count, msg.param_type, bits.hex()))
                state['count'] = msg.param_count
                state['last'] = time.monotonic()
            return False

        def pump(done, limit):
            end = time.monotonic() + limit
            while time.monotonic() < end and not done() and time.monotonic() - state['last'] < PARAM_QUIET_S:
                self.wait(take, 0.05)

        def rounds(pending, send):
            nonlocal requests
            for _ in range(PARAM_ROUNDS):
                todo = pending()
                if not todo:
                    return
                before = len(stream)
                for start in range(0, len(todo), PARAM_BATCH):
                    batch = set(todo[start:start + PARAM_BATCH])
                    state['last'] = time.monotonic()
                    for item in todo[start:start + PARAM_BATCH]:
                        send(item)
                        requests += 1
                    pump(lambda: not (batch & set(pending())), 2.0)
                if len(stream) == before:
                    return

        self.m.mav.command_long_send(*self.target, mav.MAV_CMD_REQUEST_MESSAGE, 0,
                                     mav.MAVLINK_MSG_ID_AUTOPILOT_VERSION, 0, 0, 0, 0, 0, 0)
        self.m.mav.param_request_list_send(*self.target)
        requests += 1
        end = started + 120
        while time.monotonic() < end:
            self.wait(take, 0.05)
            now = time.monotonic()
            if state['count'] is not None and (len(by_index) >= state['count'] or now - state['last'] > PARAM_QUIET_S * 2):
                break
            if state['count'] is None and now - started > PARAM_NO_PROGRESS_S:
                raise FCError(f'no PARAM_VALUE within {PARAM_NO_PROGRESS_S:.0f} s of the list request')
        names = sorted(firmware_names)
        rounds(lambda: [i for i in range(state['count'] or 0) if i not in by_index],
               lambda i: self.m.mav.param_request_read_send(*self.target, b'', i))
        rounds(lambda: [n for n in names if n not in values],
               lambda n: self.m.mav.param_request_read_send(*self.target, n.encode(), -1))
        if state['version'] is None:
            state['last'] = time.monotonic()
            self.m.mav.command_long_send(*self.target, mav.MAV_CMD_REQUEST_MESSAGE, 0,
                                         mav.MAVLINK_MSG_ID_AUTOPILOT_VERSION, 0, 0, 0, 0, 0, 0)
            pump(lambda: state['version'] is not None, 2.0)
        count = state['count']
        missing_indices = [i for i in range(count or 0) if i not in by_index]
        problems = consistency(stream, count)
        return {'created_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()), 'link': self.link,
                'autopilot_version': state['version'],
                'complete': count is not None and not missing_indices and not problems,
                'param_count_used': count, 'missing_indices': missing_indices,
                'missing_names': [n for n in names if n not in values], 'consistency': problems,
                'seconds': round(time.monotonic() - started, 2), 'requests': requests,
                'parameters': [values[k] for k in sorted(values)]}

    # -- SD card (MAVLink FTP) -----------------------------------------------------------------------------------------
    def _ftp(self, opcode, path=None, data=b'', session=0, offset=0, size=None, allow=()):
        """One FTP request and its reply (ACK, or a NAK whose code, or (code, errno), is in allow). No reply: the same
        request (same seq) again, at most FTP_TRIES."""
        if path is not None:
            data = mavftp.path_data(*([path] if isinstance(path, str) else path))
        seq = self._ftp_seq
        payload = mavftp.pack(seq, opcode, session=session, offset=offset, data=data, size=size)
        for _ in range(FTP_TRIES):
            self.m.mav.file_transfer_protocol_send(0, *self.target, payload)

            def ours(msg):
                if msg.get_type() != 'FILE_TRANSFER_PROTOCOL' or (msg.target_system, msg.target_component) not in \
                        ((SOURCE[0], SOURCE[1]), (0, 0)):
                    return False
                r = mavftp.unpack(msg.payload)
                return r['seq'] == (seq + 1) & 0xFFFF and r['req_opcode'] == opcode and r['opcode'] in (mavftp.ACK, mavftp.NAK)

            got = self.wait(ours, FTP_WAIT_S)
            if got is None:
                continue
            self._ftp_seq = (seq + 2) & 0xFFFF
            reply = mavftp.unpack(got.payload)
            if reply['opcode'] == mavftp.NAK:
                code, errno = mavftp.nak_code(reply)
                if code in allow or (code, errno) in allow:
                    return reply
                if code in (mavftp.NO_SESSIONS, mavftp.INVALID_SESSION):
                    raise FTPBusy(f'FTP {opcode}: {mavftp.nak_text(reply)} (another FTP client on this link?)')
                raise FCError(f'FTP {opcode} {path or ""}: {mavftp.nak_text(reply)}')
            return reply
        raise FCError(f'FTP {opcode} {path or ""}: no reply after {FTP_TRIES} tries')

    def _session(self, step):
        for attempt in range(FTP_SESSION_TRIES):
            try:
                return step()
            except FTPBusy:
                if attempt == FTP_SESSION_TRIES - 1:
                    raise
                time.sleep(1.0)

    def _close_session(self):
        try:
            self._ftp(mavftp.TERMINATE, allow=(mavftp.INVALID_SESSION,))
        except FCError:
            pass

    def sd_list(self, path):
        """[{'type': 'file'|'dir', 'name', 'size'}] of a directory, or None when it does not exist."""
        path = mavftp.sd_path(path)
        entries, offset = [], 0
        while True:
            reply = self._ftp(mavftp.LIST, path, offset=offset, allow=(mavftp.EOF, *mavftp.ABSENT))
            if reply['opcode'] == mavftp.NAK:
                if mavftp.nak_code(reply)[0] != mavftp.EOF:
                    return None
                break
            got = mavftp.parse_list(reply['data'])
            if not got:
                break
            offset += len(got)   # PX4 counts every entry, skipped ones too
            entries += [e for e in got if e['type'] != 'skip']
            if len(entries) > 500:
                raise FCError(f'{path} has more than 500 entries')
        return sorted(entries, key=lambda e: (e['type'], e['name']))

    def sd_read(self, path, limit=mavftp.GET_MAX):
        """The bytes of a file, or None when it does not exist."""
        path = mavftp.sd_path(path)

        def step():
            reply = self._ftp(mavftp.OPEN_RO, path, allow=mavftp.ABSENT)
            if reply['opcode'] == mavftp.NAK:
                return None
            try:
                size = int.from_bytes(reply['data'][:4], 'little')
                if size > limit:
                    raise FCError(f'{path} is {size} bytes, more than {limit}')
                data = bytearray()
                while len(data) < size:
                    got = self._ftp(mavftp.READ, offset=len(data), size=mavftp.DATA_MAX)
                    if not got['data']:
                        raise FCError(f'{path}: empty read at {len(data)} of {size} bytes')
                    data += got['data']
                if len(data) != size:
                    raise FCError(f'{path}: read {len(data)} bytes, the FC said {size}')
                return bytes(data)
            finally:
                self._close_session()

        return self._session(step)

    def _sd_write(self, path, data):
        def step():
            self._ftp(mavftp.CREATE, path)
            try:
                for offset in range(0, len(data), mavftp.DATA_MAX):
                    piece = data[offset:offset + mavftp.DATA_MAX]
                    reply = self._ftp(mavftp.WRITE, offset=offset, data=piece)
                    if int.from_bytes(reply['data'][:4], 'little') != len(piece):
                        raise FCError(f'{path}: the FC wrote fewer bytes than sent at offset {offset}')
            finally:
                self._close_session()

        self._session(step)

    def _sd_entry(self, path):
        listing = self.sd_list(str(PurePosixPath(path).parent))
        return next((e for e in listing or [] if e['name'] == PurePosixPath(path).name), None)

    def sd_verify(self, path, data):
        """path holds exactly data (None: absent), its listing agrees, and no temporary file is left."""
        now = self.sd_read(path, mavftp.PUT_MAX)
        entry = self._sd_entry(path)
        problems = []
        if now != data:
            problems.append(f'{path}: ' + ('absent' if now is None else f'{len(now)} bytes, sha256 '
                            f'{hashlib.sha256(now).hexdigest()[:12]}') + ', intended ' +
                            ('absent' if data is None else f'{len(data)} bytes, sha256 {hashlib.sha256(data).hexdigest()[:12]}'))
        if (entry is None) != (data is None) or (entry and entry.get('size') != len(data)):
            problems.append(f'{path}: listing {entry}')
        if self._sd_entry(mavftp.temp_path(path)) is not None:
            problems.append(f'{mavftp.temp_path(path)} is left on the card')
        if problems:
            raise FCError('SD verification: ' + '; '.join(problems))

    def sd_replace(self, path, data):
        """Make one of the writable SD files hold data (None: remove it). The new content goes to a temporary file in
        the same directory first and is read back; only then is the old file removed and the temporary one renamed.
        Between the two the file is missing (PX4 would then boot without it). Returns the steps taken. The caller
        reboots and verifies again: PX4 reads both files at boot."""
        path = mavftp.sd_path(path, writable=True)
        steps = []
        if data is not None:
            if len(data) > mavftp.PUT_MAX:
                raise FCError(f'{len(data)} bytes, more than {mavftp.PUT_MAX}')
            problems = mavftp.WRITABLE[path](data)
            if problems:
                raise FCError(f'{path}: ' + '; '.join(problems))
            folders, parent = [], str(PurePosixPath(path).parent)
            while parent != mavftp.SD_ROOT:
                folders.insert(0, parent)
                parent = str(PurePosixPath(parent).parent)
            for folder in folders:
                if self.sd_list(folder) is None:
                    steps.append('mkdir ' + folder)
                    self._ftp(mavftp.MKDIR, folder, allow=(mavftp.FILE_EXISTS,))
            temp = mavftp.temp_path(path)
            steps.append('write ' + temp)
            self._sd_write(temp, data)
            if self.sd_read(temp, mavftp.PUT_MAX) != data:
                raise FCError(f'{temp}: read back differs from what was written')
            steps.append('remove ' + path)
            self._ftp(mavftp.REMOVE, path, allow=mavftp.ABSENT)
            steps.append(f'rename {temp} -> {path}')
            self._ftp(mavftp.RENAME, (temp, path))
        else:
            steps.append('remove ' + path)
            self._ftp(mavftp.REMOVE, path, allow=mavftp.ABSENT)
        self.sd_verify(path, data)
        self.record('sd replace', path=path, sha256=data and hashlib.sha256(data).hexdigest(), steps=steps)
        return steps

    # -- logs ----------------------------------------------------------------------------------------------------------
    def logs(self):
        """{id: {'id', 'size', 'time_utc'}} of the logs on the FC."""
        for _ in range(3):
            self.m.mav.log_request_list_send(*self.target, 0, 0xFFFF)
            logs, end = {}, time.monotonic() + 5
            while time.monotonic() < end:
                e = self.wait(lambda msg: msg.get_type() == 'LOG_ENTRY', 1.0)
                if e is None:
                    if logs:
                        break
                    continue
                if e.num_logs == 0:
                    return {}
                logs[e.id] = {'id': e.id, 'size': e.size, 'time_utc': e.time_utc}
                if len(logs) >= e.num_logs:
                    return logs
            if logs:
                return logs
        raise FCError('no LOG_ENTRY answer')

    def _fetch(self, log_id, size, limit_s=900):
        data, have = bytearray(size), bytearray(-(-size // LOG_CHUNK))
        start = time.monotonic()
        while not all(have) and time.monotonic() - start < limit_s:
            first = have.index(0)
            last = first
            while last + 1 < len(have) and not have[last + 1]:
                last += 1
            self.m.mav.log_request_data_send(*self.target, log_id, first * LOG_CHUNK, (last - first + 1) * LOG_CHUNK)
            idle = time.monotonic()
            while time.monotonic() - idle < 1.0:
                d = self.wait(lambda msg: msg.get_type() == 'LOG_DATA', 0.2)
                if d is None or d.id != log_id:
                    continue
                idle = time.monotonic()
                k = d.ofs // LOG_CHUNK
                if k < len(have) and not have[k]:
                    data[d.ofs:d.ofs + d.count] = bytes(d.data[:d.count])
                    have[k] = 1
                if k >= last:
                    break
        self.m.mav.log_request_end_send(*self.target)
        if not all(have):
            raise FCError(f'log {log_id}: {have.count(0)} chunks missing after {limit_s} s')
        return bytes(data)

    def log_download(self, log_id, out, twice=True):
        """Download a log to out; twice: read it a second time and compare, so a corrupt transfer is not mistaken
        for a good one."""
        logs = self.logs()
        if log_id not in logs:
            raise FCError(f'log {log_id} not on the FC (has {sorted(logs)[-5:]})')
        entry = logs[log_id]
        t0 = time.monotonic()
        first = self._fetch(log_id, entry['size'])
        same = True
        if twice:
            same = first == self._fetch(log_id, entry['size'])
        if not same:
            raise FCError(f'log {log_id}: two downloads differ')
        Path(out).parent.mkdir(parents=True, exist_ok=True)
        Path(out).write_bytes(first)
        return dict(entry, file=str(out), sha256=hashlib.sha256(first).hexdigest(), read_twice_identical=twice and same,
                    seconds=round(time.monotonic() - t0, 1), logs_on_fc=len(logs))


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('--link', required=True)
    p.add_argument('--baud', type=int, default=2000000)
    sub = p.add_subparsers(dest='action', required=True)
    sub.add_parser('identity')
    r = sub.add_parser('params-read')
    r.add_argument('--firmware-params', help="the firmware's parameters.json(.xz): its names are asked for by name")
    r.add_argument('--out', required=True)
    s = sub.add_parser('sd-list')
    s.add_argument('path', nargs='?', default='/fs/microsd/etc')
    s = sub.add_parser('sd-get')
    s.add_argument('path')
    s.add_argument('--out', required=True)
    s = sub.add_parser('sd-put')
    s.add_argument('path')
    s.add_argument('file')
    s = sub.add_parser('sd-rm')
    s.add_argument('path')
    sub.add_parser('logs')
    s = sub.add_parser('log-get')
    s.add_argument('--id', type=int)
    s.add_argument('--out', required=True)
    s.add_argument('--once', action='store_true', help='read it once (no second read to compare)')
    s = sub.add_parser('board-role')
    s.add_argument('--role', choices=['hitl', 'aircraft'], help='set the role (a person\'s decision); without: show it')
    s = sub.add_parser('params-restore')
    s.add_argument('--from', dest='source', required=True, help='a readback file (params-read, or a deploy report\'s params_before.json)')
    s.add_argument('--other-board', action='store_true', help='the readback is of another board (a person\'s decision)')
    s.add_argument('--allow-hitl-change', action='store_true', help='SYS_HITL may change: a person has made the aircraft safe')
    s = sub.add_parser('recover')
    s.add_argument('--force-disarm', action='store_true')
    s.add_argument('--expect-hitl', type=int, choices=[0, 1])
    a = p.parse_args()
    fc = FC(a.link, a.baud).connect()
    out = None
    if a.action == 'identity':
        out = fc.identity()
    elif a.action == 'params-read':
        names = ()
        if a.firmware_params:
            from recipe import load_firmware_params
            names = load_firmware_params(a.firmware_params)
        rb = fc.read_all(names)
        Path(a.out).write_text(json.dumps(rb, indent=1) + '\n')
        out = {k: v for k, v in rb.items() if k != 'parameters'} | {'received': len(rb['parameters']), 'file': a.out}
        out['missing_names'] = out['missing_names'][:20]
    elif a.action == 'sd-list':
        out = {'path': a.path, 'entries': fc.sd_list(a.path)}
    elif a.action == 'sd-get':
        data = fc.sd_read(a.path)
        out = {'path': a.path, 'exists': data is not None}
        if data is not None:
            target = Path(a.out) / PurePosixPath(a.path).name
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_bytes(data)
            out.update(file=str(target), size=len(data), sha256=hashlib.sha256(data).hexdigest())
    elif a.action in ('sd-put', 'sd-rm'):
        if fc.identity()['armed'] is not False:
            sys.exit('the FC is armed or silent; refusing')
        data = Path(a.file).read_bytes() if a.action == 'sd-put' else None
        steps = fc.sd_replace(a.path, data)
        fc.reboot()
        fc.sd_verify(a.path, data)
        out = {'path': a.path, 'steps': steps, 'rebooted_and_verified': True}
    elif a.action == 'logs':
        out = {'logs': list(fc.logs().values())}
    elif a.action == 'log-get':
        logs = fc.logs()
        if not logs:
            sys.exit('no logs on the FC')
        out = fc.log_download(a.id if a.id is not None else max(logs), a.out, twice=not a.once)
    elif a.action == 'board-role':
        uid = fc.identity()['uid']
        boards = Path(os.environ.get('XDG_CACHE_HOME') or Path.home() / '.cache') / 'px4-llm-sim2hitl' / 'v2' / 'boards'
        f = boards / f'{uid}.role.json'
        if a.role:
            boards.mkdir(parents=True, exist_ok=True)
            f.write_text(json.dumps({'uid': uid, 'role': a.role, 'set_utc': time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
                                     'by': 'tools/fc.py board-role'}, indent=1) + '\n')
        out = json.loads(f.read_text()) if f.is_file() else {'uid': uid, 'role': None}
    elif a.action == 'params-restore':
        ident = fc.identity()
        if ident['armed'] is not False:
            sys.exit('the FC is armed or silent; refusing')
        source = json.loads(Path(a.source).read_text())
        saved_uid = (source.get('autopilot_version') or {}).get('uid')
        if saved_uid != ident['uid'] and not a.other_board:
            sys.exit(f'the readback is of board {saved_uid}, this FC is {ident["uid"]}: refusing (--other-board when a '
                     'person means to copy parameters onto another board)')
        saved = {e['name']: e for e in source['parameters']}
        now = {e['name']: e for e in fc.read_all(saved)['parameters']}
        todo = [n for n in sorted(saved) if n in now and (saved[n]['type'], saved[n]['bits']) != (now[n]['type'], now[n]['bits'])]
        if 'SYS_HITL' in todo and not a.allow_hitl_change:
            sys.exit('the readback has another SYS_HITL than the FC: refusing (--allow-hitl-change only when a person has '
                     'made the aircraft safe: propellers off)')
        for n in todo:
            fc.set_bits(n, saved[n]['type'], bytes.fromhex(saved[n]['bits']))
        if todo:
            fc.reboot()
        after = {e['name']: e for e in fc.read_all(saved)['parameters']}
        still = [n for n in todo if (after.get(n) or {}).get('bits') != saved[n]['bits']]
        out = {'restored': len(todo) - len(still), 'differed': todo, 'still_different': still,
               'not_on_fc': sorted(n for n in saved if n not in now)}
        print(json.dumps(out, default=str))
        sys.exit(1 if still else 0)
    elif a.action == 'recover':
        out = fc.recover(force_disarm=a.force_disarm, expect_hitl=a.expect_hitl)
    print(json.dumps(out, default=str))


if __name__ == '__main__':
    main()
