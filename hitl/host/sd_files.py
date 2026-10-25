"""FC SD card files over the owner's own link (MAVLink FTP, host/mavftp.py): sd-list, sd-get, sd-put, sd-rm.

A mixin of Core (core.py): it uses Core's link, gate (_param_txn_gate), FC identity (_fc_version,
_param_txn_identify), reboot (recover) and App Nap guard (_transfer).
FC operations through the single owner.

PX4 runs /fs/microsd/etc/extras.txt at the end of its boot (ROMFS init.d/rcS, FEXTRAS): that is how a custom
module outside the PX4 tree starts without changing the tree. sd-put / sd-rm change only the boot files named in
SD_WRITABLE; listing and reading work anywhere under /fs/microsd.
"""

import hashlib, json, os, secrets, shlex, time, uuid
from pathlib import Path, PurePosixPath
from pymavlink.dialects.v20 import common as mav
from . import mavftp
from .errors import PreconditionError, OperationError

SD_ROOT = '/fs/microsd'
SD_BOOT_DIR = '/fs/microsd/etc'
SD_WRITABLE = ['extras.txt']  # boot files sd-put / sd-rm may change (rcS FEXTRAS); config.txt, rc.txt are not
SD_TEMP = '/fs/microsd/etc/sim2hitl.tmp'  # an 8.3 name: written and checked here first, then renamed
SD_PUT_MAX = 16 * 1024
SD_GET_MAX = 256 * 1024
SD_LIST_MAX = 500  # entries of one directory
FTP_WAIT_S = 1.5  # one request: the reply (seq + 1, same req_opcode) within this long, or the same request again
FTP_TRIES = 3
SD_SESSION_TRIES = 3  # PX4 has one FTP session for every client of the link: busy or taken away -> start again
SD_SESSION_WAIT_S = 1.0
# CONFIG_NSH_MAXARGUMENTS of the PX4 NuttX boards (cubeorangeplus nsh defconfig: 15). nsh counts the command
# itself, prints "too many arguments" on the console only, and still runs the line cut to this many words: a
# module then sees an option without its value (2026-10-25 in a derived project: "Task start failed (-1)").
NSH_MAX_WORDS = 15


def boot_file_problems(data):
    """Lines of a boot file that nsh would not run as written: more than NSH_MAX_WORDS words, or unparsable."""
    problems = []
    for number, line in enumerate(data.decode(errors='replace').splitlines(), 1):
        try:
            words = shlex.split(line, comments=True)
        except ValueError as exc:
            problems.append(f'line {number}: {exc}')
            continue
        if len(words) > NSH_MAX_WORDS:
            problems.append(f'line {number}: {len(words)} words, nsh runs at most {NSH_MAX_WORDS} '
                            f'(the command counts) and cuts the rest')
    return problems


class SdBusy(OperationError):
    """PX4's only FTP session is held by another client (QGC), or was closed under us: start the step again."""


class SdFiles:
    # ---- the wire: one request, its reply ----

    def _ftp(self, txn, opcode, path=None, data=b'', session=0, offset=0, size=None, allow=()):
        """Send one FTP request and return its reply (ACK, or a NAK whose error code is in allow). The reply is
        the one with seq + 1 and the same req_opcode, addressed to the owner (_receive drops replies to other
        clients). No reply: the same request (same seq) again, as PX4 replays its last small reply; at most
        FTP_TRIES. Before every send the transaction's gate (writes) or the link check (reads). allow holds error
        codes, or (code, errno) pairs for FAIL_ERRNO (e.g. mavftp.NO_DIRECTORY)."""
        if path is not None:
            data = mavftp.path_data(*([path] if isinstance(path, str) else path))
        seq = txn['seq']
        payload = mavftp.pack(seq, opcode, session=session, offset=offset, data=data, size=size)
        for _ in range(FTP_TRIES):
            self._sd_gate(txn)
            with self.fc_lock:
                self.ftp = {'replies': []}
            try:
                self._send_message(mav.MAVLink_file_transfer_protocol_message(0, *txn['identity'], payload))
                end = time.monotonic() + FTP_WAIT_S
                while time.monotonic() < end:
                    with self.fc_lock:
                        reply = next((r for r in self.ftp['replies'] if r['seq'] == (seq + 1) & 0xFFFF
                                      and r['req_opcode'] == opcode and r['opcode'] in [mavftp.ACK, mavftp.NAK]),
                                     None)
                    if reply:
                        txn['seq'] = (seq + 2) & 0xFFFF
                        txn['requests'] = txn.get('requests', 0) + 1
                        if reply['opcode'] == mavftp.NAK:
                            code = reply['data'][0] if reply['data'] else 1
                            errno = reply['data'][1] if code == 2 and len(reply['data']) > 1 else None
                            if code in allow or (code, errno) in allow:
                                return reply
                            if code in [mavftp.NO_SESSIONS, mavftp.INVALID_SESSION]:
                                raise SdBusy(f'FTP {opcode}: {mavftp.nak_text(reply)} (another FTP client such as '
                                             'QGC on the same link?)')
                            raise OperationError(f'FTP {opcode} {path or ""}: {mavftp.nak_text(reply)}')
                        return reply
                    time.sleep(0.01)
                txn['resends'] = txn.get('resends', 0) + 1
            finally:
                with self.fc_lock:
                    self.ftp = None
        raise OperationError(f'FTP {opcode} {path or ""}: no reply after {FTP_TRIES} tries')

    def _sd_gate(self, txn):
        """Writes: the parameter deploy's gate (same FC link and generation, fresh heartbeat, unarmed, SYS_HITL=1,
        model stopped, no recovery, no pilot). Reads: the model stopped and the same connection generation."""
        if txn.get('what'):
            self._param_txn_gate(txn)
            return
        if self.state == 'running':
            raise PreconditionError('Model running; stop the model before using the FC SD card')
        if self.fc_generation != txn['generation'] or tuple(self.fc['identity'] or ()) != txn['identity']:
            raise OperationError('FC connection changed during the SD card access')

    def _sd_session(self, txn, step):
        """step() again when PX4's single session was busy or taken away (SdBusy), at most SD_SESSION_TRIES. A step
        closes the session it opened (TERMINATE); RESET is never sent, it would cut another client's session."""
        for attempt in range(SD_SESSION_TRIES):
            try:
                return step()
            except SdBusy:
                if attempt == SD_SESSION_TRIES - 1:
                    raise
                txn['session_restarts'] = txn.get('session_restarts', 0) + 1
                time.sleep(SD_SESSION_WAIT_S)

    # ---- file steps ----

    def _sd_list(self, txn, path):
        """[{'type': 'file'|'dir', 'name', 'size'}] of a directory, or None when it does not exist."""
        entries, offset = [], 0
        while True:
            reply = self._ftp(txn, mavftp.LIST, path, offset=offset, allow=(mavftp.EOF, mavftp.NOT_FOUND))
            if reply['opcode'] == mavftp.NAK:
                if reply['data'][0] == mavftp.NOT_FOUND:
                    return None
                break  # EOF: no more entries
            got = mavftp.parse_list(reply['data'])
            if not got:
                break
            offset += len(got)  # PX4 counts every directory entry, skipped ones too
            entries += [e for e in got if e['type'] != 'skip']
            if len(entries) > SD_LIST_MAX:
                raise OperationError(f'{path} has more than {SD_LIST_MAX} entries')
        return sorted(entries, key=lambda e: (e['type'], e['name']))

    def _sd_read(self, txn, path, limit):
        """The bytes of a file, or None when it does not exist (a session of its own, closed again)."""

        def step():
            reply = self._ftp(txn, mavftp.OPEN_RO, path, allow=mavftp.ABSENT)  # no such file, or no such directory
            if reply['opcode'] == mavftp.NAK:
                return None
            try:
                size = int.from_bytes(reply['data'][:4], 'little')
                if size > limit:
                    raise OperationError(f'{path} is {size} bytes, more than {limit}')
                data = bytearray()
                while len(data) < size:
                    got = self._ftp(txn, mavftp.READ, offset=len(data), size=mavftp.DATA_MAX)
                    if not got['data']:
                        raise OperationError(f'{path}: empty read at {len(data)} of {size} bytes')
                    data += got['data']
                if len(data) != size:
                    raise OperationError(f'{path}: read {len(data)} bytes, the FC said {size}')
                return bytes(data)
            finally:
                self._sd_close(txn)

        return self._sd_session(txn, step)

    def _sd_close(self, txn):
        try:
            self._ftp(txn, mavftp.TERMINATE, allow=(mavftp.INVALID_SESSION,))
        except OperationError:
            pass  # the step itself reports what went wrong

    def _sd_write(self, txn, path, data):
        """Create (truncate) path and write data, in 239-byte pieces; every piece must be acknowledged with its
        full length. Proven only by reading it back (_sd_replace)."""

        def step():
            self._ftp(txn, mavftp.CREATE, path)
            try:
                for offset in range(0, len(data), mavftp.DATA_MAX):
                    piece = data[offset:offset + mavftp.DATA_MAX]
                    reply = self._ftp(txn, mavftp.WRITE, offset=offset, data=piece)
                    if int.from_bytes(reply['data'][:4], 'little') != len(piece):
                        raise OperationError(f'{path}: FC wrote fewer bytes than sent at offset {offset}')
            finally:
                self._sd_close(txn)

        self._sd_session(txn, step)

    def _sd_remove(self, txn, path):
        """Remove a file; False when it was not there."""
        reply = self._ftp(txn, mavftp.REMOVE, path, allow=mavftp.ABSENT)
        return reply['opcode'] == mavftp.ACK

    def _sd_entry(self, txn, path):
        """The listing entry of path in its directory (None: absent)."""
        parent = str(PurePosixPath(path).parent)
        name = PurePosixPath(path).name
        listing = self._sd_list(txn, parent)
        return next((e for e in listing or [] if e['name'] == name), None)

    def _sd_replace(self, txn, path, data, log):
        """Make path hold data (None: no file). The new content goes to SD_TEMP first and is read back; only then
        is the old file removed and the temporary one renamed (NuttX's VFS rename would remove an existing regular
        file itself, fs/vfs/fs_rename.c; removing it here keeps that step in our own log). Between the two, the
        boot file is missing: PX4 then boots without it, i.e. as native PX4. The result is read back and the
        listing checked (the file, its size, no temporary file left). log: a list of step names."""
        if data is None:
            txn['final_touched'] = True
            log.append('remove ' + path)
            self._sd_remove(txn, path)
        else:
            if self._sd_list(txn, SD_BOOT_DIR) is None:
                log.append('mkdir ' + SD_BOOT_DIR)
                self._ftp(txn, mavftp.MKDIR, SD_BOOT_DIR, allow=(8,))  # 8: FILE_EXISTS
            log.append('write ' + SD_TEMP)
            self._sd_write(txn, SD_TEMP, data)
            if self._sd_read(txn, SD_TEMP, SD_PUT_MAX) != data:
                raise OperationError(f'{SD_TEMP} read back differs from what was written')
            txn['final_touched'] = True
            log.append('remove ' + path)
            self._sd_remove(txn, path)
            log.append('rename ' + SD_TEMP + ' -> ' + path)
            self._ftp(txn, mavftp.RENAME, (SD_TEMP, path))
        self._sd_verify(txn, path, data)

    def _sd_verify(self, txn, path, data):
        """path holds exactly data (None: absent), and no temporary file is left."""
        now = self._sd_read(txn, path, SD_PUT_MAX)
        entry = self._sd_entry(txn, path)
        temp = self._sd_entry(txn, SD_TEMP)
        problems = []
        if now != data:
            problems.append(f'{path}: ' + ('absent' if now is None else f'{len(now)} bytes sha256 '
                            f'{hashlib.sha256(now).hexdigest()[:12]}') + ', intended ' + (
                            'absent' if data is None else f'{len(data)} bytes sha256 '
                            f'{hashlib.sha256(data).hexdigest()[:12]}'))
        if (entry is None) != (data is None) or (entry and entry.get('size') != len(data)):
            problems.append(f'{path}: listing {entry}')
        if temp is not None:
            problems.append(f'{SD_TEMP} is left on the card')
        if problems:
            raise OperationError('verification: ' + '; '.join(problems))
        return now

    # ---- operations ----

    @staticmethod
    def _sd_path(path, writable=False):
        """An absolute path under /fs/microsd without '..' (PX4 refuses those too); writable: one of the boot
        files in SD_WRITABLE."""
        if not isinstance(path, str) or not path or len(path) > 200 or not path.isascii() or not path.isprintable():
            raise ValueError('SD path must be a printable ASCII string of at most 200 characters')
        parts = path.split('/')  # as sent to PX4: PurePosixPath would drop '.' before the check
        if '..' in parts or '.' in parts or (path != SD_ROOT and not path.startswith(SD_ROOT + '/')) \
                or '\t' in path or '//' in path:
            raise ValueError(f'SD path must be {SD_ROOT} or below it, without . or .. ({path})')
        if writable and (str(PurePosixPath(path).parent) != SD_BOOT_DIR
                         or PurePosixPath(path).name not in SD_WRITABLE):
            raise ValueError(f'sd-put / sd-rm change only {[SD_BOOT_DIR + "/" + n for n in SD_WRITABLE]} ({path})')
        return path.rstrip('/') if path != '/' else path

    def _sd_read_txn(self):
        if self.state == 'running':
            raise PreconditionError('Model running; stop the model before using the FC SD card')
        if self.fc['state'] != 'verified' or not self.fc['identity']:
            raise PreconditionError('No verified FC for the SD card')
        return {'identity': tuple(self.fc['identity']), 'generation': self.fc_generation,
                'seq': secrets.randbelow(0xFFF0)}

    def sd_list(self, path=SD_BOOT_DIR):
        """The entries of one SD directory (read-only)."""
        path = self._sd_path(path)
        with self.operation_lock:
            def run():
                txn = self._sd_read_txn()
                entries = self._sd_list(txn, path)
                return {'path': path, 'exists': entries is not None, 'entries': entries or [],
                        'requests': txn.get('requests', 0), 'resends': txn.get('resends', 0)}
            return self._transfer(run)

    def sd_get(self, path, out):
        """Download one SD file (at most SD_GET_MAX bytes) into directory out (read-only)."""
        path = self._sd_path(path)
        with self.operation_lock:
            def run():
                txn = self._sd_read_txn()
                data = self._sd_read(txn, path, SD_GET_MAX)
                result = {'path': path, 'exists': data is not None}
                if data is not None:
                    target = Path(out)
                    target.mkdir(parents=True, exist_ok=True)
                    target = target / PurePosixPath(path).name
                    target.write_bytes(data)
                    result.update(file=str(target), size=len(data), sha256=hashlib.sha256(data).hexdigest())
                return result
            return self._transfer(run)

    def sd_put(self, local, path, out):
        """Make the SD boot file path hold the bytes of the local file. See _sd_change."""
        path = self._sd_path(path, writable=True)
        data = Path(local).read_bytes()
        if len(data) > SD_PUT_MAX:
            raise ValueError(f'{local} is {len(data)} bytes, more than {SD_PUT_MAX}')
        problems = boot_file_problems(data)
        if problems:
            raise ValueError(f'{local}: ' + '; '.join(problems))
        with self.operation_lock:
            return self._transfer(self._sd_change, path, data, out, 'sdput', str(Path(local).resolve()))

    def sd_remove(self, path, out):
        """Remove the SD boot file path. See _sd_change."""
        path = self._sd_path(path, writable=True)
        with self.operation_lock:
            return self._transfer(self._sd_change, path, None, out, 'sdrm', None)

    def _sd_plan_ready(self, path, old, new, version, journal_path):
        """The change is final; the write starts right after this. Nothing to do: consent is given in the
        conversation (user 2026-10-17). Tests use this point to change the FC between the plan and the write."""

    def _sd_reboot(self, txn):
        """Reboot (recover), then the same FC again (uid, board, git)."""
        txn['rebooting'] = True  # only this reboot may change the connection generation
        self.recover()
        self._param_txn_identify(txn)
        txn['rebooting'] = False

    def _sd_change(self, path, data, out, action, local):
        """sd-put (data) / sd-rm (data None), in a new <out>/<action>_<UTC>_<id>/ directory:
        preconditions and the FC's identity (as param-deploy) -> the old file (before/) -> nothing to change:
        PASS, no write, no reboot -> the same FC again -> _sd_replace (temporary file, read back,
        remove, rename, read back and listing) -> reboot (recover), the same FC -> read back and listing again
        (after/): PASS. A failure puts the old file back the same way (with a reboot when the boot file had
        been touched) and reports FAIL. A failed gate or another FC stops at once (OperationError): nothing more
        is sent, the journal says where it stopped. journal.json is rewritten at every stage (reading, writing,
        rebooting, verifying, rolling back, the end); the FTP steps of a stage are kept in 'steps' until then."""
        out = Path(out) / f'{action}_{time.strftime("%Y%m%d_%H%M%SZ", time.gmtime())}_{uuid.uuid4().hex[:8]}'
        out.mkdir(parents=True)
        what = 'SD file change'
        self._param_deploy_preconditions(what)
        txn = {'identity': tuple(self.fc['identity']), 'generation': self.fc_generation, 'what': what,
               'seq': secrets.randbelow(0xFFF0)}
        version = self._fc_version(txn['identity'])
        if not version:
            raise OperationError('The FC did not answer AUTOPILOT_VERSION (needed to name the FC)')
        txn['version'] = version
        name = PurePosixPath(path).name
        journal = {'schema_version': 1, 'transaction': out.name, 'action': action, 'path': path, 'local': local,
                   'new_sha256': data and hashlib.sha256(data).hexdigest(), 'new_size': data and len(data),
                   'fc_version': version, 'runtime_source_id': self.runtime_identity.get('source_id'),
                   'state': 'reading', 'steps': []}
        journal_path = out / 'journal.json'

        def save():
            temp = journal_path.with_suffix('.tmp')
            temp.write_text(json.dumps(journal, indent=1, allow_nan=False) + '\n')
            os.replace(temp, journal_path)

        def keep(folder, content, listing):
            folder = out / folder
            folder.mkdir()
            (folder / 'listing.json').write_text(json.dumps(listing, indent=1) + '\n')
            if content is not None:
                (folder / name).write_bytes(content)

        save()
        if data is not None:
            (out / ('new_' + name)).write_bytes(data)
        try:
            listing = self._sd_list(txn, SD_BOOT_DIR)
            old = self._sd_read(txn, path, SD_PUT_MAX) if listing is not None else None
        except OperationError as exc:
            journal.update(state='read_failed', error=str(exc))
            save()
            raise
        keep('before', old, listing)
        journal.update(old_sha256=old and hashlib.sha256(old).hexdigest(), old_size=old and len(old))
        result = {'transaction': str(out), 'journal': str(journal_path), 'path': path,
                  'old_sha256': journal['old_sha256'], 'new_sha256': journal['new_sha256']}
        if old == data:
            journal['state'] = 'no_op'
            save()
            return dict(result, verdict='PASS', changed=False, note='the FC already has this content: no write, no reboot')
        self._sd_plan_ready(path, old, data, version, journal_path)
        self._param_deploy_preconditions(what)  # again, right before the write
        try:
            if self.fc_generation != txn['generation']:
                raise OperationError(what + ' stopped: the FC reconnected after reading the old file')
            self._param_txn_identify(txn)
        except OperationError as exc:
            journal.update(state='stopped_before_writing', error=str(exc))
            save()
            raise
        journal['state'] = 'writing'
        save()
        try:
            self._sd_replace(txn, path, data, journal['steps'])
            journal['state'] = 'rebooting'
            save()
            self._sd_reboot(txn)
            journal['state'] = 'verifying'
            save()
            self._sd_verify(txn, path, data)
            keep('after', data, self._sd_list(txn, SD_BOOT_DIR))
            journal['state'] = 'complete'
            save()
            return dict(result, verdict='PASS', changed=True, steps=journal['steps'],
                        requests=txn.get('requests', 0), resends=txn.get('resends', 0),
                        session_restarts=txn.get('session_restarts', 0))
        except Exception as exc:
            if self._sd_stopped(txn, exc):
                journal.update(state='stopped', error=str(exc))
                save()
                raise OperationError(f'{exc}; nothing more was sent and the old file was not put back. The boot '
                                     f'file may be the old one, the new one or missing: see {journal_path}')
            journal.update(state='rolling_back', error=str(exc), rollback_steps=[])
            save()
            try:
                if txn.get('final_touched'):
                    if txn.get('rebooting'):  # the failure came during this transaction's own reboot
                        self._param_txn_identify(txn)
                        txn['rebooting'] = False
                    self._sd_replace(txn, path, old, journal['rollback_steps'])
                    self._sd_reboot(txn)
                else:  # the boot file was never touched: only the temporary file may be left
                    journal['rollback_steps'].append('remove ' + SD_TEMP)
                    self._sd_remove(txn, SD_TEMP)
                self._sd_verify(txn, path, old)
            except Exception as rollback_exc:
                journal.update(state='rollback_failed', rollback_error=str(rollback_exc))
                save()
                raise OperationError(f'{what} failed ({exc}) and putting the old file back did not finish '
                                     f'({rollback_exc}); see {journal_path}')
            keep('rollback', old, self._sd_list(txn, SD_BOOT_DIR))
            journal['state'] = 'rolled_back'
            save()
            return dict(result, verdict='FAIL', changed=False, error=str(exc), steps=journal['steps'],
                        rollback_steps=journal['rollback_steps'])

    def _sd_stopped(self, txn, exc):
        """Stop without a rollback: the gate failed (ParamTxnStop: armed, another link, a reconnection that was
        not this transaction's reboot, another FC, ...) or no longer holds now."""
        from .core import ParamTxnStop

        if isinstance(exc, ParamTxnStop):
            return True
        if txn.get('rebooting'):
            return False  # the failure came during the transaction's own reboot: the rollback identifies the FC
        try:
            self._param_txn_gate(txn)
            return False
        except ParamTxnStop:
            return True
