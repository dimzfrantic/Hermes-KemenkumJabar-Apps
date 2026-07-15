#!/usr/bin/env python3
"""Manual OAuth reauthorization helper for incident evidence Google Drive.

Usage:
  python reauth_google_drive.py auth-url
  python reauth_google_drive.py exchange 'http://localhost:8089/?code=...&scope=...'

Required env:
  GOOGLE_CLIENT_SECRET_PATH=/path/to/oauth-client-secret.json
Optional env:
  GOOGLE_TOKEN_PATH=/path/to/google_token.json
  GOOGLE_REDIRECT_URI=http://localhost:8089/
"""
import json
import os
import sys
from pathlib import Path

from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

SCOPES = ['https://www.googleapis.com/auth/drive.file']
BASE = Path(__file__).resolve().parent
CLIENT_SECRET = Path(os.environ.get('GOOGLE_CLIENT_SECRET_PATH', str(BASE / 'client_secret.json')))
TOKEN_PATH = Path(os.environ.get('GOOGLE_TOKEN_PATH', str(Path.home() / '.hermes' / 'google_token.json')))
REDIRECT_URI = os.environ.get('GOOGLE_REDIRECT_URI', 'http://localhost:8089/')
STATE_PATH = BASE / '.google_oauth_state.json'


def make_flow(code_verifier=None):
    if not CLIENT_SECRET.exists():
        raise FileNotFoundError(
            f'Google OAuth client secret tidak ditemukan: {CLIENT_SECRET}. '
            'Set env GOOGLE_CLIENT_SECRET_PATH ke file client secret yang benar.'
        )
    kwargs = {}
    if code_verifier:
        kwargs['code_verifier'] = code_verifier
        kwargs['autogenerate_code_verifier'] = False
    flow = InstalledAppFlow.from_client_secrets_file(str(CLIENT_SECRET), SCOPES, **kwargs)
    flow.redirect_uri = REDIRECT_URI
    return flow


def auth_url():
    flow = make_flow()
    url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true',
        prompt='consent',
    )
    state_info = {
        'state': state,
        'code_verifier': getattr(flow, 'code_verifier', None),
        'redirect_uri': REDIRECT_URI,
    }
    STATE_PATH.write_text(json.dumps(state_info, indent=2))
    os.chmod(STATE_PATH, 0o600)
    print(url)


def exchange(callback_url):
    state_info = json.loads(STATE_PATH.read_text()) if STATE_PATH.exists() else {}
    flow = make_flow(code_verifier=state_info.get('code_verifier'))
    flow.fetch_token(authorization_response=callback_url)
    creds = flow.credentials
    token_info = {
        'token': creds.token,
        'refresh_token': creds.refresh_token,
        'token_uri': creds.token_uri,
        'client_id': creds.client_id,
        'client_secret': creds.client_secret,
        'scopes': list(creds.scopes) if creds.scopes else SCOPES,
        'universe_domain': getattr(creds, 'universe_domain', 'googleapis.com'),
        'expiry': creds.expiry.isoformat() if creds.expiry else None,
    }
    TOKEN_PATH.parent.mkdir(parents=True, exist_ok=True)
    tmp = TOKEN_PATH.with_suffix(TOKEN_PATH.suffix + '.tmp')
    tmp.write_text(json.dumps(token_info, indent=2))
    os.chmod(tmp, 0o600)
    tmp.replace(TOKEN_PATH)
    os.chmod(TOKEN_PATH, 0o600)
    if STATE_PATH.exists():
        STATE_PATH.unlink()

    service = build('drive', 'v3', credentials=creds)
    about = service.about().get(fields='user(emailAddress,displayName)').execute()
    user = about.get('user', {})
    print('TOKEN_OK')
    print('ACCOUNT:', user.get('emailAddress', '[unknown]'))


def main():
    if len(sys.argv) < 2 or sys.argv[1] not in {'auth-url', 'exchange'}:
        print('Usage: reauth_google_drive.py auth-url|exchange <callback_url>', file=sys.stderr)
        sys.exit(2)
    if sys.argv[1] == 'auth-url':
        auth_url()
    else:
        if len(sys.argv) < 3:
            print('callback_url is required', file=sys.stderr)
            sys.exit(2)
        exchange(sys.argv[2])


if __name__ == '__main__':
    main()
