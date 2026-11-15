"""Create and explicitly send a bounded, reviewable log snapshot."""
from pathlib import Path
import re
import time
import uuid
from remote_logging import ENDPOINT, RemoteLoggingHandler

MAX_BYTES = 32768

def snapshot_lines(root, token=''):
    path = Path(root) / 'macro.log'
    with path.open('rb') as stream:
        stream.seek(0, 2)
        size = stream.tell()
        stream.seek(max(0, size - MAX_BYTES))
        data = stream.read(MAX_BYTES).decode('utf-8', errors='replace')
    if not data.strip():
        raise ValueError('The log is empty')
    if token:
        data = data.replace(token, '[redacted]')
    data = re.sub(r'(?i)\b[a-z]:[\\/][^\r\n"\']+', '[path]', data)
    data = re.sub(r'(?i)(token|authorization|api[_-]?key|password|secret)(\s*[:=]\s*)(?:bearer\s+)?[^\s,;]+', r'\1\2[redacted]', data)
    data = re.sub(r'(?i)\bbearer\s+\S+', 'Bearer [redacted]', data)
    data = ''.join(c if c >= ' ' or c in '\n\t' else ' ' for c in data)
    return [data[i:i+400] for i in range(0, len(data), 400)]

def send_snapshot(root, token, lines=None):
    try:
        lines = snapshot_lines(root, token) if lines is None else lines
        if not lines:
            return False, 'Log is empty.'
        client = RemoteLoggingHandler(ENDPOINT, token)
    except (OSError, ValueError) as exc:
        return False, 'Could not prepare log: ' + str(exc)
    upload_id = uuid.uuid4().hex[:12]
    try:
        if not client._post([f'log_upload_begin {upload_id} parts={len(lines)}']):
            return False, 'Upload failed: pairing code or connection rejected.'
        for offset in range(0, len(lines), 5):
            time.sleep(1.1)
            batch = [f'log {upload_id} {i+1}/{len(lines)} {line}' for i, line in enumerate(lines[offset:offset+5], offset)]
            if not client._post(batch):
                return False, f'Upload failed after {offset} of {len(lines)} parts. Try again.'
        time.sleep(1.1)
        if not client._post([f'log_upload_end {upload_id}']):
            return False, 'Upload failed before completion was confirmed.'
        return True, f'Log sent successfully (ID {upload_id}).'
    finally:
        client.close()
