"""MAVLink FTP payloads (FILE_TRANSFER_PROTOCOL) as PX4 v1.18 serves them (src/modules/mavlink/mavlink_ftp.{h,cpp}),
and the rules of the two SD card files a recipe may put on a flight controller.

The 251-byte payload is a 12-byte header (seq_number u16, session u8, opcode u8, size u8, req_opcode u8,
burst_complete u8, padding u8, offset u32, little-endian) and up to 239 data bytes. PX4 answers a request with
seq_number + 1, opcode ACK or NAK and req_opcode = the request's opcode; a NAK carries the error code in data[0] (and
errno in data[1] for FAIL_ERRNO). PX4 serves one session at a time for every client on a link (QGC included), and
replays its last small reply when a request comes again with the same seq_number.
"""
import shlex
import struct
from pathlib import PurePosixPath

PAYLOAD_LEN = 251
HEADER = struct.Struct('<HBBBBBBI')
DATA_MAX = PAYLOAD_LEN - HEADER.size  # 239

(NONE, TERMINATE, RESET, LIST, OPEN_RO, READ, CREATE, WRITE, REMOVE, MKDIR, RMDIR, OPEN_WO, TRUNCATE, RENAME, CRC32,
 BURST) = range(16)
ACK, NAK = 128, 129

ERRORS = {0: 'NONE', 1: 'FAIL', 2: 'FAIL_ERRNO', 3: 'INVALID_DATA_SIZE', 4: 'INVALID_SESSION',
          5: 'NO_SESSIONS_AVAILABLE', 6: 'EOF', 7: 'UNKNOWN_COMMAND', 8: 'FILE_EXISTS', 9: 'FILE_PROTECTED',
          10: 'FILE_NOT_FOUND'}
EOF, NO_SESSIONS, INVALID_SESSION, FILE_EXISTS, NOT_FOUND = 6, 5, 4, 8, 10
# A path with a missing directory on the way: PX4 answers FAIL_ERRNO with NuttX's ENOTDIR (20), not FILE_NOT_FOUND
# (it converts only ENOENT); seen on a Cube Orange+ for OPEN_RO of /fs/microsd/etc/extras.txt without etc/.
NO_DIRECTORY = (2, 20)
ABSENT = (NOT_FOUND, NO_DIRECTORY)


def pack(seq, opcode, session=0, offset=0, data=b'', req_opcode=0, burst_complete=0, size=None):
    """The 251-byte payload (a list of ints) of a FILE_TRANSFER_PROTOCOL message."""
    data = bytes(data)
    if len(data) > DATA_MAX:
        raise ValueError(f'FTP data longer than {DATA_MAX} bytes')
    head = HEADER.pack(seq & 0xFFFF, session, opcode, len(data) if size is None else size, req_opcode,
                       burst_complete, 0, offset)
    return list((head + data).ljust(PAYLOAD_LEN, b'\0'))


def unpack(payload):
    """dict(seq, session, opcode, size, req_opcode, burst_complete, offset, data) of a received payload."""
    raw = bytes(payload).ljust(PAYLOAD_LEN, b'\0')
    seq, session, opcode, size, req_opcode, burst, _, offset = HEADER.unpack_from(raw)
    return {'seq': seq, 'session': session, 'opcode': opcode, 'size': size, 'req_opcode': req_opcode,
            'burst_complete': burst, 'offset': offset, 'data': raw[HEADER.size:HEADER.size + min(size, DATA_MAX)]}


def nak_code(reply):
    """(code, errno or None) of a NAK reply."""
    data = reply['data']
    code = data[0] if data else 1
    return code, (data[1] if code == 2 and len(data) > 1 else None)


def nak_text(reply):
    """'FILE_NOT_FOUND', 'FAIL_ERRNO errno 28', ... for a NAK reply."""
    code, errno = nak_code(reply)
    return ERRORS.get(code, f'error {code}') + (f' errno {errno}' if errno is not None else '')


def path_data(*paths):
    """A path (or, for RENAME, two paths) as FTP data: each NUL-terminated, as PX4 reads them."""
    data = b''.join(p.encode() + b'\0' for p in paths)
    if len(data) > DATA_MAX:
        raise ValueError('FTP path too long')
    return data


def parse_list(data):
    """Entries of one LIST reply: PX4 sends 'F<name>\\t<size>\\0', 'D<name>\\0' or 'S\\0' (skipped, still counted by
    the offset of the next LIST)."""
    entries = []
    for item in bytes(data).split(b'\0'):
        if not item:
            continue
        kind, text = chr(item[0]), item[1:].decode(errors='replace')
        if kind == 'F':
            name, _, size = text.partition('\t')
            entries.append({'type': 'file', 'name': name, 'size': int(size) if size.isdigit() else None})
        elif kind == 'D':
            entries.append({'type': 'dir', 'name': text})
        else:
            entries.append({'type': 'skip', 'name': text})
    return entries


# -- the SD card files a recipe may change ---------------------------------------------------------------------------
SD_ROOT = '/fs/microsd'
BOOT_FILE = '/fs/microsd/etc/extras.txt'
LOGGER_TOPICS = '/fs/microsd/etc/logging/logger_topics.txt'
TEMP_NAME = 'sim2hitl.tmp'   # an 8.3 name in the target's own directory: written, read back, then renamed
PUT_MAX = 16 * 1024
GET_MAX = 256 * 1024

# A boot file line as the NuttX of PX4 v1.18 runs it (apps/nshlib nsh_parse.c, nsh_script.c; NSH_MAXARGUMENTS 15 and
# NSH_LINELEN 128 in the Cube Orange+ and Pixhawk 6C defconfigs). Above 15 words, the command counted, nsh prints "too
# many arguments" on the console only and still runs the line; words after the 19th it drops without a word, so a
# module sees an option without its value. It reads a line 127 bytes at a time: the rest of a longer line, a
# comment's too, runs as a line of its own.
NSH_MAX_WORDS = 15
NSH_MAX_LINE_BYTES = 127
# The logger topic list as PX4 v1.18 reads it (src/modules/logger/logged_topics.cpp add_topics_from_file): fgets into
# 80 bytes, so a line (comments too) longer than 78 characters plus its newline goes on as another line; each line
# '<topic>[ <interval ms>[ <instance>]]'; a line without an instance adds every instance (ORB_MULTI_MAX_INSTANCES,
# 10); the logger has MAX_TOPICS_NUM 255 slots, shared with the topics of SDLOG_PROFILE (the list is added after
# them; SDLOG_PROFILE=0 logs the list alone), so the slot count below is a lower bound when SDLOG_PROFILE is not 0.
LOGGER_MAX_LINE_BYTES = 78
LOGGER_MAX_SLOTS = 255
LOGGER_MULTI_INSTANCES = 10


def boot_file_problems(data):
    """Lines of a boot file that nsh would not run as written."""
    problems = []
    for number, line in enumerate(data.split(b'\n'), 1):
        if len(line) > NSH_MAX_LINE_BYTES:
            problems.append(f'line {number}: {len(line)} bytes, nsh reads {NSH_MAX_LINE_BYTES} and runs the rest as '
                            'another line')
            continue
        try:
            words = shlex.split(line.decode(errors='replace'), comments=True)
        except ValueError as exc:
            problems.append(f'line {number}: {exc}')
            continue
        if len(words) > NSH_MAX_WORDS:
            problems.append(f'line {number}: {len(words)} words, more than the {NSH_MAX_WORDS} nsh takes (the '
                            'command counts)')
    return problems


def logger_topics_problems(data):
    """Lines of a logger topic list that PX4's logger would not read as written, and too many topic slots."""
    problems, slots = [], 0
    for number, raw in enumerate(data.split(b'\n'), 1):
        if len(raw) > LOGGER_MAX_LINE_BYTES:
            problems.append(f'line {number}: {len(raw)} bytes, the logger reads {LOGGER_MAX_LINE_BYTES} and the rest '
                            'as another line')
            continue
        line = raw.decode('ascii', errors='replace')
        if len(line) < 2 or line.startswith('#'):
            continue
        words = line.split()
        if (not 1 <= len(words) <= 3 or not all(c.islower() or c.isdigit() or c == '_' for c in words[0].rstrip(','))
                or not all(w.isdigit() for w in words[1:])):
            problems.append(f'line {number}: not "<topic>[ <interval ms>[ <instance>]]" ({line[:40]})')
            continue
        if len(words) > 1 and int(words[1]) > 65535:
            problems.append(f'line {number}: interval {words[1]} ms above 65535')
        if len(words) > 2 and int(words[2]) >= LOGGER_MULTI_INSTANCES:
            problems.append(f'line {number}: instance {words[2]}, at most {LOGGER_MULTI_INSTANCES - 1}')
        slots += 1 if len(words) == 3 else LOGGER_MULTI_INSTANCES
    if slots > LOGGER_MAX_SLOTS:
        problems.append(f'{slots} topic slots (a line without an instance counts {LOGGER_MULTI_INSTANCES}), the logger '
                        f'has {LOGGER_MAX_SLOTS}')
    return problems


# The files a put or remove may change, each with the check of its reader. Listing and reading work anywhere under
# /fs/microsd.
WRITABLE = {BOOT_FILE: boot_file_problems, LOGGER_TOPICS: logger_topics_problems}


def sd_path(path, writable=False):
    """An absolute path under /fs/microsd without '.' or '..' (PX4 refuses those too); writable: one of WRITABLE."""
    if not isinstance(path, str) or not path or len(path) > 200 or not path.isascii() or not path.isprintable():
        raise ValueError('SD path must be a printable ASCII string of at most 200 characters')
    parts = path.split('/')
    if '..' in parts or '.' in parts or (path != SD_ROOT and not path.startswith(SD_ROOT + '/')) \
            or '\t' in path or '//' in path:
        raise ValueError(f'SD path must be {SD_ROOT} or below it, without . or .. ({path})')
    if writable and path not in WRITABLE:
        raise ValueError(f'only {sorted(WRITABLE)} may be changed ({path})')
    return path.rstrip('/')


def temp_path(path):
    """The temporary file of a change of path, in the same directory (a rename stays in its directory)."""
    return str(PurePosixPath(path).parent / TEMP_NAME)
