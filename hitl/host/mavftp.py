"""MAVLink FTP payloads (FILE_TRANSFER_PROTOCOL), as PX4 v1.18 src/modules/mavlink/mavlink_ftp.{h,cpp} (unchanged from v1.17 for what is used here).

The 251-byte payload is a 12-byte header (seq_number u16, session u8, opcode u8, size u8, req_opcode u8,
burst_complete u8, padding u8, offset u32, little-endian) and up to 239 data bytes. PX4 answers a request
with seq_number + 1, opcode ACK or NAK and req_opcode = the request's opcode; a NAK carries the error code in
data[0] (and errno in data[1] for FAIL_ERRNO). PX4 serves one session at a time for every client on the same
link (QGC included), and replays its last small reply when a request comes again with the same seq_number.
"""

import struct

PAYLOAD_LEN = 251
HEADER = struct.Struct('<HBBBBBBI')
DATA_MAX = PAYLOAD_LEN - HEADER.size  # 239

NONE, TERMINATE, RESET, LIST, OPEN_RO, READ, CREATE, WRITE, REMOVE, MKDIR, RMDIR, OPEN_WO, TRUNCATE, RENAME, CRC32, BURST = range(16)
ACK, NAK = 128, 129

ERRORS = {0: 'NONE', 1: 'FAIL', 2: 'FAIL_ERRNO', 3: 'INVALID_DATA_SIZE', 4: 'INVALID_SESSION',
          5: 'NO_SESSIONS_AVAILABLE', 6: 'EOF', 7: 'UNKNOWN_COMMAND', 8: 'FILE_EXISTS', 9: 'FILE_PROTECTED',
          10: 'FILE_NOT_FOUND'}
EOF, NO_SESSIONS, INVALID_SESSION, NOT_FOUND = 6, 5, 4, 10
# A path with a missing directory on the way (or a file where a directory should be): PX4 answers FAIL_ERRNO with
# NuttX's ENOTDIR (20), not FILE_NOT_FOUND (it converts only ENOENT); seen on the real FC 2026-10-17 for OPEN_RO
# of /fs/microsd/etc/extras.txt without etc/.
NO_DIRECTORY = (2, 20)
ABSENT = (NOT_FOUND, NO_DIRECTORY)


def pack(seq, opcode, session=0, offset=0, data=b'', req_opcode=0, burst_complete=0, size=None):
    """The 251-byte payload list for MAVLink_file_transfer_protocol_message."""
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
            'burst_complete': burst, 'offset': offset,
            'data': raw[HEADER.size:HEADER.size + min(size, DATA_MAX)]}


def nak_text(reply):
    """'FILE_NOT_FOUND', 'FAIL_ERRNO errno 28', ... for a NAK reply."""
    data = reply['data']
    code = data[0] if data else 1
    text = ERRORS.get(code, f'error {code}')
    if code == 2 and len(data) > 1:
        text += f' errno {data[1]}'
    return text


def path_data(*paths):
    """A path (or, for RENAME, two paths) as FTP data: each NUL-terminated, as PX4 reads them."""
    data = b''.join(p.encode() + b'\0' for p in paths)
    if len(data) > DATA_MAX:
        raise ValueError('FTP path too long')
    return data


def parse_list(data):
    """Entries of one LIST reply: PX4 sends 'F<name>\\t<size>\\0', 'D<name>\\0' or 'S\\0' (skipped, still
    counted by the offset of the next LIST)."""
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
