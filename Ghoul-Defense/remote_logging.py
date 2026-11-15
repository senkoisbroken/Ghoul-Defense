"""Opt-in, bounded remote diagnostics without blocking game automation."""

import json
import http.client
import logging
import base64
import ctypes
from ctypes import wintypes
from pathlib import Path
import queue
import re
import threading
import urllib.error
import urllib.parse
import urllib.request
import uuid


ENDPOINT = 'https://zx9kgh0wp5.execute-api.us-east-2.amazonaws.com/logs'


def _dpapi(data, *, decrypt=False):
    class Blob(ctypes.Structure):
        _fields_ = [('length', wintypes.DWORD), ('data', ctypes.POINTER(ctypes.c_ubyte))]

    source = (ctypes.c_ubyte * len(data)).from_buffer_copy(data)
    source_blob = Blob(len(data), source)
    output = Blob()
    crypt = ctypes.WinDLL('crypt32', use_last_error=True)
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.LocalFree.argtypes = [ctypes.c_void_p]
    operation = crypt.CryptUnprotectData if decrypt else crypt.CryptProtectData
    ok = operation(ctypes.byref(source_blob), None, None, None, None, 1, ctypes.byref(output))
    if not ok:
        raise ctypes.WinError(ctypes.get_last_error())
    try:
        return ctypes.string_at(output.data, output.length)
    finally:
        kernel.LocalFree(output.data)


def save_token(root, token):
    path = Path(root) / 'remote_settings.json'
    protected = base64.b64encode(_dpapi(token.encode('ascii'))).decode('ascii')
    temporary = path.with_suffix('.tmp')
    temporary.write_text(json.dumps({'protected_token': protected}), encoding='utf-8')
    temporary.replace(path)


def load_token(root):
    path = Path(root) / 'remote_settings.json'
    if not path.exists():
        return None
    try:
        content = json.loads(path.read_text(encoding='utf-8'))
        return _dpapi(base64.b64decode(content['protected_token'], validate=True), decrypt=True).decode('ascii')
    except (OSError, ValueError, KeyError, TypeError, UnicodeError):
        return None


def forget_token(root):
    (Path(root) / 'remote_settings.json').unlink(missing_ok=True)


class RemoteLoggingHandler(logging.Handler):
    def __init__(self, endpoint, token, client_id=None):
        super().__init__()
        parsed = urllib.parse.urlsplit(endpoint)
        if (parsed.scheme != 'https' or not parsed.hostname
                or not parsed.hostname.endswith('.execute-api.us-east-2.amazonaws.com')
                or parsed.username or parsed.password or parsed.port not in (None, 443)
                or parsed.path != '/logs' or parsed.query or parsed.fragment):
            raise ValueError('Invalid diagnostics endpoint')
        if not re.fullmatch(r'[A-Za-z0-9_-]{32,128}', token):
            raise ValueError('Invalid diagnostics token')
        self.endpoint = endpoint
        self.token = token
        self.client_id = client_id or uuid.uuid4().hex
        self.pending = queue.Queue(maxsize=128)
        self.stopping = threading.Event()
        self.worker = threading.Thread(target=self._run, name='remote-diagnostics', daemon=True)
        self.worker.start()

    def verify(self):
        """Confirm the receiver accepts this pairing code."""
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None

        body = json.dumps({'client_id': self.client_id, 'lines': ['connection_check']}).encode('utf-8')
        request = urllib.request.Request(self.endpoint, body,
            {'Authorization': 'Bearer ' + self.token, 'Content-Type': 'application/json'}, method='POST')
        try:
            with urllib.request.build_opener(NoRedirect).open(request, timeout=5) as response:
                return response.status == 200 and json.loads(response.read(1024)).get('ok') is True
        except (OSError, ValueError, AttributeError, http.client.HTTPException, urllib.error.URLError):
            return False

    def emit(self, record):
        try:
            message = record.getMessage()
            if message.startswith('action '):
                data = json.loads(message[7:])
                safe = {name: data[name] for name in ('kind', 'chosen', 'offered', 'accepted') if name in data}
                line = 'action ' + json.dumps(safe, ensure_ascii=True)
            elif message.startswith(('running_changed ', 'movement_gate ', 'Started paused build=')):
                line = message
            elif record.levelno >= logging.ERROR:
                line = 'error ' + record.name
            else:
                return
            self.pending.put_nowait(line[:512])
        except (ValueError, TypeError, queue.Full):
            pass

    def _run(self):
        class NoRedirect(urllib.request.HTTPRedirectHandler):
            def redirect_request(self, *args, **kwargs):
                return None

        opener = urllib.request.build_opener(NoRedirect)
        while not self.stopping.is_set():
            try:
                first = self.pending.get(timeout=.5)
            except queue.Empty:
                continue
            if self.stopping.wait(2):
                break
            batch = [first]
            while len(batch) < 32:
                try:
                    batch.append(self.pending.get_nowait())
                except queue.Empty:
                    break
            body = json.dumps({'client_id': self.client_id, 'lines': batch}).encode('utf-8')
            request = urllib.request.Request(
                self.endpoint, body,
                {'Authorization': 'Bearer ' + self.token, 'Content-Type': 'application/json'},
                method='POST',
            )
            try:
                with opener.open(request, timeout=5) as response:
                    response.read(1024)
            except (OSError, http.client.HTTPException, urllib.error.URLError):
                # The local log remains the source of truth if the network fails.
                pass

    def close(self):
        self.stopping.set()
        self.worker.join(timeout=1)
        super().close()
