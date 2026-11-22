import importlib.util, sys, time, struct, json, lzma, math, hashlib
from pathlib import Path
import serial
from pymavlink.dialects.v20 import common as mav
from .param_wire import param_bits, with_bits, encode, decode
from . import mavftp, serial_helpers


def load_helpers(project):
    """Serial-device and frame helpers (host/serial_helpers.py); a function so tests can replace them."""
    return serial_helpers


class SerialTransport:
    fake = False

    def __init__(self, project, port='auto'):
        self.helpers = load_helpers(project)
        self.requested = port
        self.port = None
        self.path = None
        self.preferred = None
        self.link_info = {'state': 'unknown', 'path': None, 'label': None}
        self.link_events = []
        self.last_inspection = 0

    def inspect_link(self, force=False):
        now = time.monotonic()
        if not force and now - self.last_inspection < 0.1:
            return self.link_info['state']
        self.last_inspection = now
        found = self.helpers.devices()
        selected = self.helpers.choose_device(found, self.preferred, self.requested)
        # A bootloader may use a different VID/PID at the same explicitly selected path.
        # It is diagnostic only; never replace the remembered application identity.
        observed = selected or next(
            (d for d in found if d.path == (self.path or self.requested)), None
        )
        label = observed.label if observed else None
        boot = bool(label and serial_helpers.BOOTLOADER_LABEL.search(label))
        unknown = (
            selected is not None
            and selected.identity.startswith('path:')
            and selected.label == selected.path
        )
        state = (
            'bootloader'
            if boot
            else 'enumerating' if unknown else 'application' if selected is not None else 'absent'
        )
        info = {'state': state, 'path': observed.path if observed else None, 'label': label}
        if info != self.link_info:
            self.link_events.append(dict(info, monotonic_s=now))
            self.link_events = self.link_events[-64:]
        self.link_info = info
        self._candidate = selected
        return state

    def link_diagnostics(self):
        return dict(self.link_info, events=list(self.link_events))

    def open(self):
        if self.port:
            return True
        if self.inspect_link(force=True) != 'application':
            return False
        selected = self._candidate
        posix = sys.platform != 'win32'
        if posix and self.helpers.serial_owner(selected.path):
            raise OSError('Serial port already has an owner')
        self.port = serial.Serial(
            selected.path,
            115200,
            timeout=0,
            write_timeout=0.1,
            exclusive=True if posix else None,
        )
        self.path = selected.path
        self.preferred = selected
        return True

    @property
    def native_fd(self):
        return self.port.fileno() if self.port else None

    def read(self):
        return (
            self.port.read(32768) if self.port else b''
        )  # timeout=0: poll the FD even when TIOCINQ reports zero

    def write(self, data):
        if not self.port:
            raise OSError('Serial disconnected')
        if self.port.write(data) != len(data):
            raise OSError('Incomplete serial write')

    def close(self):
        if self.port:
            self.port.close()
        self.port = None


class FakeFC:
    fake = True

    def __init__(self, project=None, behavior='success', config_path=None):
        self.path = 'fake://px4'
        self.behavior = behavior
        self.opened = False
        self.armed = False
        self.hitl = 1
        self.next_heartbeat = 0
        self.next_controls = 0
        self.reboot_until = 0
        self.output = bytearray()
        self.counts = {}
        self.command_ids = []
        self.log_pieces_sent = 0
        self.flights = 0  # as PX4 with SDLOG_MODE 0: every arm starts a new log
        self.short_piece_sent = False
        self.heartbeat_pause_until = 0.0
        self.held_log = bytearray()  # LOG_DATA held back during the heartbeat pause
        self.paused_log, self.log_pause_until = bytearray(), 0.0  # log_pause_s: the rest of a range, held back
        self.param_table = None  # name -> [value, MAVLink type]; built on first use by _params()
        self.param_list_pos = None  # next used index of a PARAM_REQUEST_LIST stream, or None
        self.other_writer_done = False  # param_change_on_set applied once
        # px4io_outputs: PX4's px4io (_px4io_check): the channels with a function it has seen (None: its first cycle
        # after boot), when it looks next, whether a parameter changed since it last looked
        self.px4io_seen, self.px4io_next, self.px4io_dirty = None, 0.0, False
        self.sd = None  # SD card: {'dirs': set, 'files': {path: bytes}}; built on first use by _sd()
        self.ftp_session = None  # PX4's single FTP session: {'path', 'size'} or None
        self.ftp_last_reply = None  # PX4 replays its last small reply for a repeated seq_number
        self.ftp_replies = 0
        self.ftp_writes = 0
        self.writer = mav.MAVLink(None, srcSystem=1, srcComponent=1)
        self.parser = mav.MAVLink(None)
        self.config_path = Path(config_path) if config_path else None
        self.config = {}
        self.mode = 4
        self.sub_mode = 0
        self.sticks = [0, 0, 0, 0]
        self.height = 0.0
        self.cas = 0.0
        self.last_tick = time.monotonic()
        self.next_telemetry = 0
        self.last_config = 0
        self.helpers = load_helpers(project) if project else None
        self._config()

    def _config(self):
        if self.config_path:
            self.config = json.loads(self.config_path.read_text())
            self.behavior = self.config.get('behavior', 'success')

    def _event(self, message):
        file = self.config.get('event_log')
        if file:
            with Path(file).open('a') as stream:
                stream.write(
                    json.dumps(
                        {
                            'time': time.monotonic(),
                            'message': message.to_dict(),
                            'system': message.get_srcSystem(),
                            'component': message.get_srcComponent(),
                        }
                    )
                    + '\n'
                )

    def fake_logs(self):
        """Deterministic, well-formed ULog files (sizes from config 'fc_logs', at least 71 bytes); the newest is
        last: header, flag bits, then logged-string messages ('L') whose text differs per log and offset, so a
        byte-exact download also parses strictly (analysis/ulog_strict.py)."""
        logs = []
        for index, size in enumerate(self.config.get('fc_logs', [4000, 50003]) + [30003] * self.flights):
            data = bytearray(b'ULog\x01\x12\x35\x01' + struct.pack('<Q', 1000 + index))
            data += struct.pack('<HB', 40, ord('B')) + bytes(40)
            while len(data) < size:
                remaining = size - len(data)
                take = min(remaining, 3 + 4000)
                if 0 < remaining - take < 12:
                    take = remaining - 12
                text = bytearray()
                while len(text) < take - 12:
                    text += hashlib.sha256(b'fake-ulog-%d-%d-%d' % (index, len(data), len(text))).hexdigest().encode()
                payload = bytes([6]) + struct.pack('<Q', len(data)) + bytes(text[:take - 12])
                data += struct.pack('<HB', len(payload), ord('L')) + payload
            logs.append(bytes(data))
        return logs

    def pack(self, msg):
        data = msg.pack(self.writer)
        self.writer.seq = (self.writer.seq + 1) % 256
        return data

    def open(self):
        self.opened = True

    def _params(self):
        """As PX4: every parameter of the firmware's list exists; only the 'used' ones (here: the names in the
        00_native QGC export) are in PARAM_REQUEST_LIST, in name order. Config faults: param_unknown (names the
        FC does not have: no reply), param_extra ({name: int}, used, not in the firmware list), param_wrong_type,
        param_mute; param_list_drop_every / param_list_drop lose list items in the stream; param_force_index
        ({name: index}) reports a wrong index; no_autopilot_version leaves AUTOPILOT_VERSION unanswered;
        autopilot_uid sets the reported uid; param_save_fail keeps writes from reaching the saved values;
        param_change_after_list ({name: value}) changes a value and announces it once the list is sent."""
        if self.param_table is None:
            root = Path(__file__).resolve().parents[2]
            listing = json.loads(lzma.decompress((root / 'deploy/00_native/firmware/parameters.json.xz').read_bytes()))
            self.param_table = {p['name']: [p.get('default', 0), {'Int32': 6, 'Float': 9}[p['type']]]
                                for p in listing['parameters']}
            export = (root / 'deploy/00_native/fc_params_20261013.params').read_text().splitlines()
            self.param_used_base = [x.split('\t')[2] for x in export if x.strip() and not x.startswith('#')]
            # A correctly deployed FC: the release's airframe / boot / verify_only / set values.
            release = json.loads((root / 'deploy/00_native/params.json').read_text())
            for section in ['airframe', 'boot', 'verify_only', 'set']:
                for name, entry in release.get(section, {}).items():
                    self.param_table[name][0] = entry['value']
            self.param_table['FW_MAN_P_MAX'][0] = 30.0
            # As PX4 (src/lib/parameters/autosave.cpp): RAM values are saved at least 300 ms after a change and at
            # most every 2 s; a reboot reloads the saved values, so an unsaved change is lost.
            self.param_saved = {k: v[0] for k, v in self.param_table.items()}
            self.param_save_at = None
            self.param_last_save = -math.inf
        initial = self.config.get('param_initial', {})  # test setup: values that differ from the release
        if initial and initial != getattr(self, 'param_initial_applied', None):
            self.param_initial_applied = dict(initial)
            for name, value in initial.items():  # in RAM and saved (not set_persistent: that calls _params)
                self.param_table[name][0] = self.param_saved[name] = value
        unknown = set(self.config.get('param_unknown', []))
        extra = self.config.get('param_extra', {})
        table = {k: v for k, v in self.param_table.items() if k not in unknown}
        table.update({k: [v, 6] for k, v in extra.items()})
        table['SYS_HITL'] = [self.hitl, 6]
        used = sorted(n for n in set(self.param_used_base) | set(extra) if n in table)
        return table, used

    def set_persistent(self, name, value):
        """Test setup / another writer: a value that is in RAM and saved (survives a reboot)."""
        self._params()
        self.param_table[name][0] = value
        self.param_saved[name] = value

    def _param_changed(self):
        now = time.monotonic()
        self.px4io_dirty = True  # PX4 publishes parameter_update
        if self.param_save_at is None:
            delay = self.config.get('param_save_delay_s', 0.3)
            self.param_save_at = max(now + delay, self.param_last_save + self.config.get('param_save_rate_s', 2.0))

    def _px4io_check(self):
        """As PX4 v1.17 px4io (PX4IO::update_params; pwm_out does the same for the FMU outputs): it looks at
        parameter changes at most once a second (SubscriptionInterval parameter_update 1_s); while disarmed, a MAIN
        channel whose function went from unset to a servo (201-208) since it last looked gets PWM_MAIN_DISn = 1500,
        to a motor (101-112) PWM_MAIN_MINn = 1100 and PWM_MAIN_MAXn = 1900 (param_set: announced only if it
        changes). The first cycle after boot only notes the set channels. Modelled from the PX4 source, not from
        host/pwm_defaults.py, so the tests check the tools against PX4 rather than against themselves."""
        table, used = self._params()
        funcs = {k[len('PWM_MAIN_FUNC'):]: v[0] for k, v in self.param_table.items()
                 if k.startswith('PWM_MAIN_FUNC') and k[len('PWM_MAIN_FUNC'):].isdigit()}
        if self.px4io_seen is not None and not self.armed:
            for channel, function in sorted(funcs.items()):
                if channel in self.px4io_seen:
                    continue
                values = ({'PWM_MAIN_DIS' + channel: 1500} if 201 <= function <= 208 else
                          {'PWM_MAIN_MIN' + channel: 1100, 'PWM_MAIN_MAX' + channel: 1900} if 101 <= function <= 112
                          else {})
                for name, value in values.items():
                    if name in self.param_table and self.param_table[name][0] != value:
                        self.param_table[name][0] = value
                        self._param_changed()
                        table, used = self._params()
                        self.output.extend(self._param_value(table, used, name))
        self.px4io_seen = {c for c, f in funcs.items() if f != 0}

    def _param_value(self, table, used, name, bits=None):
        value, kind = table[name]
        bits = encode(kind, value) if bits is None else bits
        if name in self.config.get('param_wrong_type', []):
            kind = 15 - kind  # INT32 <-> REAL32
        index = self.config.get('param_force_index', {}).get(name, used.index(name) if name in used else 65535)
        message = mav.MAVLink_param_value_message(name.encode(), 0.0, kind, len(used), index)
        return with_bits(self.pack(message), bits, message.crc_extra)  # the exact bytes, as PX4 sends them

    def _sd(self):
        """The SD card (config sd_initial: {'dirs': [...], 'files': {path: text}}); it keeps its files over a
        reboot (sd_lose_on_reboot: the writes since the last boot are lost)."""
        if self.sd is None:
            initial = self.config.get('sd_initial', {})
            self.sd = {'dirs': set(initial.get('dirs', ['/fs/microsd', '/fs/microsd/log'])),
                       'files': {k: v.encode() for k, v in initial.get('files', {}).items()}}
            self.sd_booted = {'dirs': set(self.sd['dirs']), 'files': dict(self.sd['files'])}
        return self.sd

    def _ftp(self, m):
        """As PX4 v1.17 mavlink_ftp.cpp, for what the owner uses: one session for every client (opened read-only
        or for writing), a repeated seq_number gets the last small reply again (to the client it was for), writes
        only below /fs/microsd/, rename replaces an existing file (NuttX fs/vfs/fs_rename.c unlinks it first).
        ftp_other_client_after_create ({'path', 'mode': 'ro'|'wo'}, once): right after a CREATE, another client
        closes that session and opens its own file (GPT review 16 R16-1). Faults: ftp_mute, ftp_drop_every (every Nth reply lost), ftp_corrupt_write (path: the stored bytes
        differ), ftp_close_after_writes (another client closes the session after N writes, once), ftp_busy (N
        OPEN/CREATE answered NO_SESSIONS: another client holds the session), ftp_nak ({opcode: count}: FAIL),
        ftp_rename_keeps_source (N renames leave the old name too)."""
        req = mavftp.unpack(m.payload)
        if self.config.get('ftp_mute'):
            return
        last = self.ftp_last_reply
        if last is not None and (req['seq'] + 1) & 0xFFFF == last[0]:
            self._ftp_send(m, last[1], last[2])
            return
        sd, op, error, errno, data = self._sd(), req['opcode'], 0, 0, b''
        session, offset = self.ftp_session, req['offset']
        path = req['data'].split(b'\0')[0].decode(errors='replace') if op not in [mavftp.READ, mavftp.WRITE] else ''
        writable = path.startswith('/fs/microsd/')
        parent = path.rsplit('/', 1)[0] if '/' in path else ''
        naks = self.config.get('ftp_nak', {})
        if naks.get(str(op), 0) > 0:
            naks[str(op)] -= 1
            error = 1
        elif op in [mavftp.OPEN_RO, mavftp.CREATE] and self.config.get('ftp_busy', 0) > 0:
            self.config['ftp_busy'] -= 1
            error = mavftp.NO_SESSIONS
        elif '..' in path.split('/'):
            error = 9
        elif op in [mavftp.NONE]:
            pass
        elif op in [mavftp.TERMINATE, mavftp.RESET]:
            if op == mavftp.TERMINATE and session is None:
                error = mavftp.INVALID_SESSION
            self.ftp_session = None
        elif op == mavftp.LIST:
            if path not in sd['dirs']:
                error = mavftp.NOT_FOUND
            else:
                names = sorted({p[len(path) + 1:].split('/')[0] for p in list(sd['dirs']) + list(sd['files'])
                                if p.startswith(path + '/')})
                for name in names[offset:]:
                    full = path + '/' + name
                    item = (b'F' + f'{name}\t{len(sd["files"][full])}'.encode() if full in sd['files']
                            else b'D' + name.encode()) + b'\0'
                    if len(data) + len(item) > mavftp.DATA_MAX:
                        break
                    data += item
                if not data:
                    error = mavftp.EOF
        elif op in [mavftp.OPEN_RO, mavftp.CREATE, mavftp.OPEN_WO]:
            if session is not None:
                error = mavftp.NO_SESSIONS
            elif parent not in sd['dirs']:
                # ENOTDIR, not converted by PX4: seen on the real FC for OPEN_RO (2026-10-17); CREATE/OPEN_WO: NuttX FAT open
                error, errno = 2, 20
            elif op == mavftp.OPEN_RO and path not in sd['files']:
                error, errno = 2, 2  # ENOENT: answered as FILE_NOT_FOUND
            else:
                if op == mavftp.CREATE or path not in sd['files']:
                    sd['files'][path] = b''
                self.ftp_session = {'path': path, 'writes': 0, 'writable': op != mavftp.OPEN_RO}
                data = len(sd['files'][path]).to_bytes(4, 'little')
                other = self.config.get('ftp_other_client_after_create')
                if op == mavftp.CREATE and other:  # another client: TERMINATE/RESET ours, then its own open
                    self.config['ftp_other_client_after_create'] = None
                    sd['files'].setdefault(other['path'], b'')
                    self.ftp_session = {'path': other['path'], 'writes': 0, 'writable': other.get('mode') == 'wo'}
        elif op in [mavftp.READ, mavftp.WRITE]:
            if session is None or req['session'] != 0:
                error = mavftp.INVALID_SESSION
            elif op == mavftp.READ:
                content = sd['files'].get(session['path'], b'')
                if offset >= len(content):
                    error = mavftp.EOF
                else:
                    data = content[offset:offset + req['size']]
            elif not session['path'].startswith('/fs/microsd/'):
                error = 9
            elif not session['writable']:
                error, errno = 2, 9  # EBADF: a read-only fd
            else:
                piece = req['data']
                if session['path'] in self.config.get('ftp_corrupt_write', []):
                    piece = bytes([piece[0] ^ 1]) + piece[1:]
                content = sd['files'][session['path']]
                sd['files'][session['path']] = content[:offset].ljust(offset, b'\0') + piece + content[offset + len(piece):]
                data = len(piece).to_bytes(4, 'little')
                self.ftp_writes += 1
                session['writes'] += 1
                if session['writes'] == self.config.get('ftp_close_after_writes'):
                    self.config['ftp_close_after_writes'] = None
                    self.ftp_session = None  # as another client's TERMINATE / RESET
        elif op == mavftp.REMOVE:
            if not writable:
                error = 9
            elif parent not in sd['dirs']:
                error, errno = 2, 2  # NuttX FAT fat_remove: a failed path lookup is ENOENT (fs_fat32dirent.c)
            elif path not in sd['files']:
                error, errno = 2, 2
            else:
                del sd['files'][path]
        elif op == mavftp.MKDIR:
            if not writable:
                error = 9
            elif path in sd['dirs'] or path in sd['files']:
                error, errno = 2, 17  # EEXIST: answered as FILE_EXISTS
            elif parent not in sd['dirs']:
                error, errno = 2, 2
            else:
                sd['dirs'].add(path)
        elif op == mavftp.RENAME:
            parts = req['data'].split(b'\0')
            new = parts[1].decode(errors='replace') if len(parts) > 1 else ''
            if not new.startswith('/fs/microsd/'):
                error = 9
            elif path not in sd['files']:
                error, errno = 2, 2
            elif new in sd['dirs']:
                error, errno = 2, 17
            elif self.config.get('ftp_rename_keeps_source', 0) > 0:  # fault: a copy, the old name stays
                self.config['ftp_rename_keeps_source'] -= 1
                sd['files'][new] = sd['files'][path]
            else:
                sd['files'][new] = sd['files'].pop(path)
        else:
            error = 7
        if error == 2 and errno == 2:
            error = mavftp.NOT_FOUND
        elif error == 2 and errno == 17:
            error = 8
        if error:
            reply = mavftp.pack(req['seq'] + 1, mavftp.NAK, data=bytes([error, errno] if error == 2 else [error]),
                                req_opcode=op)
        else:
            reply = mavftp.pack(req['seq'] + 1, mavftp.ACK, data=data, req_opcode=op)
        size = mavftp.unpack(reply)['size']
        target = (m.get_srcSystem(), m.get_srcComponent())
        self.ftp_last_reply = (((req['seq'] + 1) & 0xFFFF, reply, target)
                               if size <= 4 and error != mavftp.NO_SESSIONS else None)
        self._ftp_send(m, reply, target)

    def _ftp_send(self, m, reply, target):
        self.ftp_replies += 1
        drop = self.config.get('ftp_drop_every', 0)
        if drop and self.ftp_replies % drop == 0:
            return  # lost reply: the owner sends the same request again
        self.output.extend(self.pack(mav.MAVLink_file_transfer_protocol_message(0, *target, reply)))

    def read(self):
        if not self.opened:
            return b''
        now = time.monotonic()
        if now - self.last_config >= 0.05:
            self._config()
            self.last_config = now
        dt = min(0.1, now - self.last_tick)
        self.last_tick = now
        if self.behavior == 'lost':
            return b''
        if now < self.reboot_until:
            raw = bytes(self.output)
            self.output.clear()
            return raw
        if self.config.get('synthetic_flight') and self.armed and self.sticks[2] > 50:
            self.cas = min(16.0, self.cas + 40 * dt)
            if self.cas >= 12 and self.sticks[0] < -20:
                self.height = min(100.0, self.height + 100 * dt)
        if self.config.get('px4io_outputs') and now >= self.px4io_next and (self.px4io_dirty or self.px4io_seen is None):
            self._px4io_check()
            self.px4io_next, self.px4io_dirty = now + self.config.get('px4io_check_s', 1.0), False
        if self.held_log and now >= self.heartbeat_pause_until:
            self.output.extend(self.held_log)
            self.held_log.clear()
        if self.paused_log and now >= self.log_pause_until:
            self.output.extend(self.paused_log)
            self.paused_log.clear()
        if now >= self.next_heartbeat and self.behavior != 'heartbeat_lost' and now >= self.heartbeat_pause_until:
            self.output.extend(
                self.pack(
                    mav.MAVLink_heartbeat_message(
                        1,
                        12,
                        128 if self.armed else 0,
                        (self.mode << 16) | (self.sub_mode << 24),
                        3,
                        3,
                    )
                )
            )
            self.next_heartbeat = now + 0.1
        if now >= self.next_controls and self.config.get('controls_enabled', True):
            self.output.extend(
                self.pack(
                    mav.MAVLink_hil_actuator_controls_message(
                        int(now * 1e6), [0.0] * 16, 128 if self.armed else 0, 0
                    )
                )
            )
            self.next_controls = now + 0.004
        if now >= self.next_telemetry and self.config.get('telemetry_enabled', True):
            boot = int(now * 1000) & 0xFFFFFFFF
            loiter = self.config.get('synthetic_flight') and self.mode == 4 and self.sub_mode == 3
            angle = now * 0.5 if loiter else 0.0
            north = 50 * math.cos(angle) if loiter else 0.0
            east = 50 * math.sin(angle) if loiter else 0.0
            self.output.extend(
                self.pack(
                    mav.MAVLink_attitude_message(
                        boot,
                        0,
                        math.radians(0.8633 if self.height < 100 else 0),
                        angle + math.pi / 2 if loiter else 0,
                        0,
                        0,
                        0,
                    )
                )
            )
            self.output.extend(
                self.pack(
                    mav.MAVLink_local_position_ned_message(
                        boot, north, east, -self.height, self.cas, 0, 0
                    )
                )
            )
            self.output.extend(
                self.pack(
                    mav.MAVLink_vfr_hud_message(
                        self.cas, self.cas, 0, self.sticks[2] // 10, self.height, 0
                    )
                )
            )
            self.next_telemetry = now + 0.05
        if self.param_table is not None and self.param_save_at is not None and now >= self.param_save_at:
            if not self.config.get('param_save_fail'):  # fault: the save never reaches flash
                self.param_saved = {k: v[0] for k, v in self.param_table.items()}
            self.param_last_save, self.param_save_at = now, None
        if self.param_list_pos is not None:  # stream the list, 60 per read, as PX4 sends it when TX allows
            table, used = self._params()
            drop, dropped = self.config.get('param_list_drop_every', 0), self.config.get('param_list_drop', [])
            for index in range(self.param_list_pos, min(len(used), self.param_list_pos + 60)):
                lost = (drop and index % drop == drop - 1) or used[index] in dropped
                if not lost:  # lost in the stream: re-request by index
                    self.output.extend(self._param_value(table, used, used[index]))
            self.param_list_pos += 60
            if self.param_list_pos >= len(used):
                self.param_list_pos = None
                for name, value in self.config.get('param_change_after_list', {}).items():
                    # As PX4 when a value changes (e.g. QGC writes it): a PARAM_VALUE nobody asked for.
                    self.set_persistent(name, value)
                    self.output.extend(self._param_value(table | {name: [value, table[name][1]]}, used, name))
        raw = bytes(self.output)
        self.output.clear()
        return raw

    def write(self, data):
        for m in self.parser.parse_buffer(data) or []:
            name = m.get_type()
            self.counts[name] = self.counts.get(name, 0) + 1
            self._event(m)
            if name == 'FILE_TRANSFER_PROTOCOL' and m.target_system in [0, 1] and m.target_component in [0, 1]:
                self._ftp(m)
            if name == 'PARAM_REQUEST_READ':
                key = m.param_id.rstrip('\0')
                table, used = self._params()
                if key != 'SYS_HITL' and self.config.get('param_mute'):
                    pass
                elif m.param_index >= 0 and m.param_index < len(used):
                    self.output.extend(self._param_value(table, used, used[m.param_index]))
                elif m.param_index < 0 and key in table:  # an unknown name gets no reply, as PX4
                    self.output.extend(self._param_value(table, used, key))
            if name == 'PARAM_SET':
                # As PX4 (mavlink_parameters.cpp): an unknown name or another type gets no answer; otherwise the
                # value is set and PARAM_VALUE answers. Faults, each for the sent bytes listed per name:
                # param_set_ignore ({name: [hex]}: not set, no answer), param_set_echo_bits ({name: {sent hex:
                # stored hex}}: another value stored and answered), param_change_on_set ({name: value}: another
                # writer, e.g. QGC, changes a parameter at the first PARAM_SET).
                key = m.param_id.rstrip('\0')
                if not self.other_writer_done:
                    for other, value in self.config.get('param_change_on_set', {}).items():
                        self.set_persistent(other, value)
                        self.other_writer_done = True
                    for other, values in self.config.get('param_flap_on_set', {}).items():
                        # Another writer changes a value and changes it back, both announced (A -> B -> A).
                        for value in values:
                            self.set_persistent(other, value)
                            table, used = self._params()
                            self.output.extend(self._param_value(table, used, other))
                        self.other_writer_done = True
                for other, value in self.config.get('param_change_on_set_of', {}).get(key, {}).items():
                    self.set_persistent(other, value)  # another writer, when this name is written
                table, used = self._params()
                sent = param_bits(m)
                ignored = sent.hex() in self.config.get('param_set_ignore', {}).get(key, [])
                if key in table and m.param_type == table[key][1] and not ignored:
                    echo = self.config.get('param_set_echo_bits', {}).get(key, {}).get(sent.hex())
                    bits = bytes.fromhex(echo) if echo else sent
                    self.param_table[key][0] = decode(table[key][1], bits)
                    self._param_changed()
                    table, used = self._params()
                    self.output.extend(self._param_value(table, used, key, bits))
            if name == 'PARAM_REQUEST_LIST' and not self.config.get('param_mute'):
                self.output.extend(self.pack(mav.MAVLink_param_value_message(
                    b'_HASH_CHECK', 0.0, mav.MAV_PARAM_TYPE_UINT32, len(self._params()[1]), 65535)))
                self.param_list_pos = 0
            if name == 'LOG_REQUEST_LIST':
                logs = self.fake_logs()
                listed = logs[:-1] if self.config.get('log_list_drop_newest') else logs
                for index, data in enumerate(listed):
                    self.output.extend(self.pack(mav.MAVLink_log_entry_message(
                        index + 1, len(logs), len(logs), 1_760_000_000 + index, len(data))))
            if name == 'LOG_REQUEST_DATA':
                logs = self.fake_logs()
                gap = self.config.get('log_heartbeat_gap_s', 0)
                if gap and not self.log_pieces_sent:
                    # As PX4 while streaming a log: heartbeats late enough for the owner to mark the FC stale.
                    self.heartbeat_pause_until = time.monotonic() + gap
                # As PX4 (mavlink_log_handler.cpp): a new request replaces the range being sent. log_pause_s: like
                # PX4 at times, the second half of every range comes only after a pause (heartbeats go on).
                self.paused_log.clear()
                pause = self.config.get('log_pause_s', 0)
                if 1 <= m.id <= len(logs) and not self.config.get('log_mute'):  # log_mute: the stream stops
                    data = logs[m.id - 1]
                    drop = self.config.get('log_drop_every', 0)
                    end = min(len(data), m.ofs + m.count)
                    middle = m.ofs + max(1, -(-(end - m.ofs) // 90) // 2) * 90
                    self.log_pause_until = time.monotonic() + pause
                    for ofs in range(m.ofs, end, 90):
                        self.log_pieces_sent += 1
                        if drop and self.log_pieces_sent % drop == 0:
                            continue  # lost piece: the downloader must re-request the gap
                        piece = data[ofs:ofs + 90]
                        count = len(piece)
                        if self.config.get('log_short_piece') and not self.short_piece_sent and ofs == 900:
                            count, self.short_piece_sent = 16, True  # one incomplete piece, once
                        packet = self.pack(mav.MAVLink_log_data_message(
                            m.id, ofs, count, list(piece.ljust(90, b'\0'))))
                        if pause and ofs >= middle:
                            self.paused_log.extend(packet)
                        else:
                            (self.held_log if time.monotonic() < self.heartbeat_pause_until else self.output).extend(packet)
            if name == 'MANUAL_CONTROL':
                self.sticks = [m.x, m.y, m.z, m.r]
            if name == 'COMMAND_LONG':
                self.command_ids.append(m.command)
                rejection = self.config.get('reject_result', 2)
                if self.behavior in ['reject', 'reject_with_heartbeat']:
                    self.output.extend(
                        self.pack(mav.MAVLink_command_ack_message(m.command, rejection))
                    )
                    if self.behavior == 'reject_with_heartbeat':
                        self.output.extend(
                            self.pack(
                                mav.MAVLink_heartbeat_message(1, 12, 0, self.mode << 16, 3, 3)
                            )
                        )
                        self.output.extend(self.pack(mav.MAVLink_command_ack_message(512, 0)))
                    continue
                if self.behavior == 'timeout':
                    continue
                if (
                    m.command == 400
                    and m.param1 == 0
                    and self.armed
                    and (
                        (m.param2 == 0 and self.config.get('reject_normal_disarm'))
                        or (m.param2 == 21196 and self.config.get('reject_force_disarm'))
                    )
                ):
                    self.output.extend(self.pack(mav.MAVLink_command_ack_message(m.command, 2)))
                    continue
                self.output.extend(self.pack(mav.MAVLink_command_ack_message(m.command, 0)))
                if m.command == 512 and int(m.param1) == 148 and not self.config.get('no_autopilot_version'):
                    # As PX4 v1.17.0 (release type 0xFF): git hash & 0xFFFFFFFFFF000000, little-endian.
                    custom = list(struct.pack('<Q', 0xD6F12AD1C4F70AD3 & 0xFFFFFFFFFF000000))
                    # os_custom_version: the first 16 hex digits of the NuttX commit (v1.17.0: fb2fadf6...).
                    os_custom = list(struct.pack('<Q', int(self.config.get('nuttx_hash16', 'fb2fadf6f599c140'), 16)))
                    self.output.extend(self.pack(mav.MAVLink_autopilot_version_message(
                        0, 0x011100FF, 0, 0, 56, custom, [0] * 8, os_custom, 0x3185, 0x0038,
                        self.config.get('autopilot_uid', 0))))
                if m.command == 400:
                    if m.param1 and not self.armed:
                        self.flights += 1
                    self.armed = bool(m.param1)
                    self.next_heartbeat = 0
                if m.command == 176:
                    self.mode = int(m.param2)
                    self.sub_mode = int(m.param3)
                    self.next_heartbeat = 0
                if m.command == 246:
                    self.ftp_session = self.ftp_last_reply = None
                    if self.sd is not None:
                        lose = self.config.get('sd_lose_on_reboot')  # fault: the writes never reached the card
                        if lose:  # True: at every reboot; a number: at that many reboots
                            self.sd = {'dirs': set(self.sd_booted['dirs']), 'files': dict(self.sd_booted['files'])}
                            if lose is not True:
                                self.config['sd_lose_on_reboot'] = lose - 1
                        self.sd_booted = {'dirs': set(self.sd['dirs']), 'files': dict(self.sd['files'])}
                    if self.param_table is not None:  # unsaved RAM values are lost
                        for name, entry in self.param_table.items():
                            entry[0] = self.param_saved.get(name, entry[0])
                        self.param_save_at = None
                    self.reboot_until = time.monotonic() + 2.3
                    self.px4io_seen, self.px4io_next = None, self.reboot_until  # px4io starts again
                    self.next_heartbeat = 0
                    self.armed = False
                    self.height = self.cas = 0
                    self.sticks = [0, 0, 0, 0]

    def close(self):
        self.opened = False


class PeerPump:
    """Bounded, lossless PTY peer used only by offline tests."""

    def __init__(self, master, project):
        import os
        from collections import deque

        self.master = master
        self.fc = FakeFC(project)
        self.fc.open()
        self.pending = bytearray()
        self.os = os
        self.write_master = os.write
        self.stats = {
            'loops': 0,
            'read_bytes': 0,
            'written_bytes': 0,
            'would_block': 0,
            'short_writes': 0,
            'parser_errors': 0,
            'max_pending': 0,
            'max_loop_gap_ns': 0,
            'error': None,
        }
        self.events = deque(maxlen=256)
        self.previous = 0

    def flush(self):
        if not self.pending:
            return
        try:
            n = self.write_master(self.master, self.pending)
        except BlockingIOError:
            self.stats['would_block'] += 1
            return
        if n < len(self.pending):
            self.stats['short_writes'] += 1
        self.stats['written_bytes'] += n
        del self.pending[:n]

    def tick(self):
        now = time.monotonic_ns()
        gap = now - self.previous if self.previous else 0
        self.previous = now
        self.stats['max_loop_gap_ns'] = max(self.stats['max_loop_gap_ns'], gap)
        self.stats['loops'] += 1
        if gap >= 20000000:
            self.events.append({'time_ns': now, 'gap_ns': gap, 'pending': len(self.pending)})
        for _ in range(32):
            try:
                raw = self.os.read(self.master, 32768)
            except BlockingIOError:
                break
            if not raw:
                break
            self.stats['read_bytes'] += len(raw)
            try:
                self.fc.write(raw)
            except mav.MAVError:
                self.stats['parser_errors'] += 1
                raise
        self.flush()
        raw = self.fc.read()
        if len(self.pending) + len(raw) > 65536:
            raise RuntimeError('Fake peer backlog exceeds 64 KiB')
        self.pending.extend(raw)
        self.stats['max_pending'] = max(self.stats['max_pending'], len(self.pending))
        self.flush()

    def snapshot(self):
        return dict(
            self.stats,
            pending_bytes=len(self.pending),
            events=list(self.events),
            counts=dict(self.fc.counts),
        )


class FakePTY:
    fake = True

    def __init__(self, project, peer_mode='thread', diagnostic_path=None):
        import os, threading

        if peer_mode not in ['thread', 'process']:
            raise ValueError('Unknown fake peer mode')
        self.os = os
        self.threading = threading
        self.project = Path(project)
        self.mode = peer_mode
        self.diagnostic_path = Path(diagnostic_path) if diagnostic_path else None
        if self.mode == 'process' and self.diagnostic_path is None:
            raise ValueError('Process peer requires a diagnostic output path')
        self.helpers = load_helpers(project)
        self.port = None
        self.master = self.slave = None
        self.path = 'fake://pty'
        self.quit = threading.Event()
        self.pump = None
        self.process = None
        self.thread = None
        self.final_diagnostics = None

    def open(self):
        import pty, subprocess

        self.quit.clear()
        self.master, self.slave = pty.openpty()
        self.path = self.os.ttyname(self.slave)
        self.os.set_blocking(self.master, False)
        self.port = serial.Serial(self.path, 115200, timeout=0, write_timeout=0.1)
        if self.mode == 'process':
            self.process = subprocess.Popen(
                [
                    sys.executable,
                    '-B',
                    str(Path(__file__).resolve()),
                    '--peer-fd',
                    str(self.master),
                    '--project',
                    str(self.project),
                    '--diagnostics',
                    str(self.diagnostic_path),
                ],
                pass_fds=(self.master,),
                stdin=subprocess.PIPE,
            )
            return
        self.pump = PeerPump(self.master, self.project)
        self.fc = self.pump.fc

        def loop():
            try:
                while not self.quit.is_set():
                    self.pump.tick()
                    time.sleep(0.0005)
            except Exception as exc:
                self.pump.stats['error'] = repr(exc)

        self.thread = self.threading.Thread(target=loop, name='fake-pty-peer', daemon=True)
        self.thread.start()

    def diagnostics(self):
        if self.mode == 'thread':
            value = self.pump.snapshot() if self.pump else {}
            value['alive'] = bool(self.thread and self.thread.is_alive())
        else:
            try:
                value = json.loads(self.diagnostic_path.read_text())
            except (OSError, ValueError):
                value = {}
            value['alive'] = bool(self.process and self.process.poll() is None)
        return dict(value, mode=self.mode)

    @property
    def native_fd(self):
        return self.port.fileno() if self.port else None

    def read(self):
        return self.port.read(min(self.port.in_waiting, 32768))

    def write(self, data):
        if self.port.write(data) != len(data):
            raise OSError('Incomplete fake PTY write')

    def close(self):
        self.quit.set()
        if self.thread:
            self.thread.join(timeout=2)
        if self.process:
            self.process.stdin.close()
            try:
                self.process.wait(timeout=3)
            except __import__('subprocess').TimeoutExpired:
                self.process.terminate()
                self.process.wait(timeout=2)
        self.final_diagnostics = self.diagnostics()
        if self.diagnostic_path and self.mode == 'thread':
            self.diagnostic_path.write_text(json.dumps(self.final_diagnostics, indent=2))
        if self.port:
            self.port.close()
            self.port = None
        for name in ['master', 'slave']:
            fd = getattr(self, name)
            if fd is not None:
                self.os.close(fd)
                setattr(self, name, None)


if __name__ == '__main__':
    import argparse, select

    parser = argparse.ArgumentParser()
    parser.add_argument('--peer-fd', type=int, required=True)
    parser.add_argument('--project', type=Path, required=True)
    parser.add_argument('--diagnostics', type=Path, required=True)
    args = parser.parse_args()
    pump = PeerPump(args.peer_fd, args.project)
    last = 0

    def save():
        temp = args.diagnostics.with_suffix('.tmp')
        temp.write_text(json.dumps(pump.snapshot()))
        temp.replace(args.diagnostics)

    try:
        while not select.select([0], [], [], 0)[0]:
            pump.tick()
            now = time.monotonic()
            if now - last >= 0.5:
                save()
                last = now
            time.sleep(0.0005)
    except Exception as exc:
        pump.stats['error'] = repr(exc)
        raise
    finally:
        save()
