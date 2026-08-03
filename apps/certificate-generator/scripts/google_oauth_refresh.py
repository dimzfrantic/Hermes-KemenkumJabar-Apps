from __future__ import annotations

import argparse
import base64
import hashlib
import json
import os
import secrets
import shutil
import sys
import time
import urllib.parse
import urllib.request
from pathlib import Path

APP_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CLIENT_SECRET_PATH = APP_ROOT / 'instance' / 'google_oauth_client.json'
DEFAULT_TOKEN_PATH = APP_ROOT / 'instance' / 'google_oauth_token.json'
DEFAULT_SESSION_PATH = APP_ROOT / 'instance' / 'google-oauth-refresh-session.json'
DEFAULT_SCOPES = [
    'https://www.googleapis.com/auth/drive.file',
    'https://www.googleapis.com/auth/drive.readonly',
    'https://www.googleapis.com/auth/spreadsheets.readonly',
]
REDIRECT_URI = 'http://localhost'
AUTH_URI = 'https://accounts.google.com/o/oauth2/v2/auth'
TOKEN_URI = 'https://oauth2.googleapis.com/token'


def _b64url(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b'=').decode('ascii')


def _load_client_config(path: Path) -> dict:
    data = json.loads(path.read_text())
    config = data.get('installed') or data.get('web') or {}
    if not config.get('client_id') or not config.get('client_secret'):
        raise RuntimeError(f'Client secret file tidak valid: {path}')
    return config


def _write_private_json(path: Path, payload: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + '.tmp')
    tmp.write_text(json.dumps(payload, indent=2))
    os.chmod(tmp, 0o600)
    tmp.replace(path)
    os.chmod(path, 0o600)


def start_flow(client_secret_path: Path, token_path: Path, session_path: Path, scopes: list[str]):
    config = _load_client_config(client_secret_path)
    state = secrets.token_urlsafe(24)
    code_verifier = _b64url(secrets.token_bytes(64))
    code_challenge = _b64url(hashlib.sha256(code_verifier.encode('ascii')).digest())
    params = {
        'client_id': config['client_id'],
        'redirect_uri': REDIRECT_URI,
        'response_type': 'code',
        'scope': ' '.join(scopes),
        'access_type': 'offline',
        'include_granted_scopes': 'true',
        'prompt': 'consent',
        'state': state,
        'code_challenge': code_challenge,
        'code_challenge_method': 'S256',
    }
    auth_url = AUTH_URI + '?' + urllib.parse.urlencode(params)
    session = {
        'created_at': int(time.time()),
        'state': state,
        'code_verifier': code_verifier,
        'redirect_uri': REDIRECT_URI,
        'client_secret_path': str(client_secret_path),
        'token_path': str(token_path),
        'scopes': scopes,
        'client_id_suffix': config['client_id'][-40:],
    }
    _write_private_json(session_path, session)
    print('SESSION_PATH=' + str(session_path))
    print('TOKEN_PATH=' + str(token_path))
    print('CLIENT_SECRET=' + str(client_secret_path))
    print('AUTH_URL=' + auth_url)
    print('NEXT=Setelah login Google selesai, salin URL lengkap dari address bar yang mengarah ke http://localhost lalu jalankan perintah exchange.')
    return {
        'auth_url': auth_url,
        'session_path': str(session_path),
        'token_path': str(token_path),
    }


def _extract_callback_params(callback_url_or_code: str) -> dict:
    raw = callback_url_or_code.strip()
    if not raw:
        raise RuntimeError('Callback URL / authorization code wajib diisi.')
    if raw.startswith('http://') or raw.startswith('https://'):
        parsed = urllib.parse.urlparse(raw)
        params = urllib.parse.parse_qs(parsed.query)
        if 'error' in params:
            raise RuntimeError('Google OAuth mengembalikan error: ' + params['error'][0])
        if 'code' not in params:
            raise RuntimeError('Authorization code tidak ditemukan pada callback URL.')
        return {
            'code': params['code'][0],
            'state': params.get('state', [''])[0],
        }
    return {'code': raw, 'state': ''}


def exchange_code(session_path: Path, callback_url_or_code: str):
    if not session_path.exists():
        raise RuntimeError(f'Session file tidak ditemukan: {session_path}. Jalankan start terlebih dahulu.')
    session = json.loads(session_path.read_text())
    config = _load_client_config(Path(session['client_secret_path']))
    extracted = _extract_callback_params(callback_url_or_code)
    expected_state = session.get('state') or ''
    received_state = extracted.get('state') or ''
    if expected_state and received_state and received_state != expected_state:
        raise RuntimeError('State OAuth tidak cocok. Ulangi proses start untuk keamanan.')

    post_data = urllib.parse.urlencode({
        'client_id': config['client_id'],
        'client_secret': config['client_secret'],
        'code': extracted['code'],
        'code_verifier': session['code_verifier'],
        'grant_type': 'authorization_code',
        'redirect_uri': session['redirect_uri'],
    }).encode('utf-8')
    req = urllib.request.Request(TOKEN_URI, data=post_data, headers={'Content-Type': 'application/x-www-form-urlencoded'})
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            token_data = json.loads(resp.read().decode('utf-8'))
    except urllib.error.HTTPError as exc:
        body = exc.read().decode('utf-8', errors='ignore')
        raise RuntimeError(f'Pertukaran token gagal: HTTP {exc.code} {body}') from exc

    if 'refresh_token' not in token_data:
        raise RuntimeError('Google tidak mengembalikan refresh_token baru. Pastikan login memakai prompt consent.')

    payload = {
        'token': token_data.get('access_token', ''),
        'refresh_token': token_data['refresh_token'],
        'token_uri': TOKEN_URI,
        'client_id': config['client_id'],
        'client_secret': config['client_secret'],
        'scopes': session['scopes'],
    }
    if token_data.get('expiry_date'):
        payload['expiry'] = token_data['expiry_date']
    elif token_data.get('expires_in'):
        payload['expiry'] = time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime(time.time() + int(token_data['expires_in'])))

    token_path = Path(session['token_path'])
    backup_path = None
    if token_path.exists():
        backup_path = token_path.with_name(token_path.name + '.bak-' + time.strftime('%Y%m%d_%H%M%S'))
        shutil.copy2(token_path, backup_path)
        os.chmod(backup_path, 0o600)
        print('BACKUP_TOKEN=' + str(backup_path))
    _write_private_json(token_path, payload)
    print('NEW_TOKEN=' + str(token_path))
    print('SCOPES=' + ', '.join(payload['scopes']))
    return {
        'token_path': str(token_path),
        'backup_path': str(backup_path) if backup_path else '',
        'scopes': list(payload['scopes']),
    }


def main():
    parser = argparse.ArgumentParser(description='Refresh Google OAuth token for certificate-generator')
    sub = parser.add_subparsers(dest='command', required=True)

    start = sub.add_parser('start')
    start.add_argument('--client-secret', default=str(DEFAULT_CLIENT_SECRET_PATH))
    start.add_argument('--token-path', default=str(DEFAULT_TOKEN_PATH))
    start.add_argument('--session-path', default=str(DEFAULT_SESSION_PATH))
    start.add_argument('--scope', action='append', dest='scopes')

    exchange = sub.add_parser('exchange')
    exchange.add_argument('callback')
    exchange.add_argument('--session-path', default=str(DEFAULT_SESSION_PATH))

    args = parser.parse_args()
    if args.command == 'start':
        scopes = args.scopes or list(DEFAULT_SCOPES)
        start_flow(Path(args.client_secret), Path(args.token_path), Path(args.session_path), scopes)
        return
    if args.command == 'exchange':
        exchange_code(Path(args.session_path), args.callback)
        return
    raise SystemExit(1)


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'ERROR: {exc}', file=sys.stderr)
        raise
