import json
import re
import subprocess
from urllib import error, parse, request
from flask import current_app



def _extract_link_from_response(label, response_text):
    text = str(response_text or '')
    if not text:
        return ''
    match = re.search(rf'{re.escape(label)}\s*:\s*(https?://\S+)', text)
    return match.group(1).strip() if match else ''


def _build_message(ticket, incident_record=None):
    incident_record = incident_record or {}
    masalah = incident_record.get('masalah') or ticket.problem_summary
    handled_by = ''
    if str(ticket.status_cache or '').upper() != 'OPEN':
        handled_by = str(incident_record.get('ditangani_oleh') or ticket.handled_by_cache or '').strip()
    bukti_awal = str(incident_record.get('bukti_awal') or '').strip() or _extract_link_from_response('Bukti awal', ticket.raw_create_response)
    folder_bukti = str(incident_record.get('folder_bukti') or '').strip() or _extract_link_from_response('Folder bukti', ticket.raw_create_response)

    lines = [
        'Tiket baru dari portal pegawai',
        f'Alias: {ticket.ticket_alias}',
        f'Kode: {ticket.ticket_code}',
        f'Pelapor: {ticket.user.full_name}',
        f'Lokasi: {ticket.location}',
        f'Masalah: {masalah}',
        f'Status: {ticket.status_cache}',
        f'Petugas: {handled_by}',
    ]
    if bukti_awal:
        lines.append(f'Bukti awal: {bukti_awal}')
    if folder_bukti:
        lines.append(f'Folder bukti: {folder_bukti}')
    return '\n'.join(lines)


def _send_via_signal_rpc(http_url, signal_account, signal_group_id, message):
    rpc_url = http_url.rstrip('/') + '/api/v1/rpc'
    payload = {
        'jsonrpc': '2.0',
        'method': 'send',
        'params': {
            'account': signal_account,
            'groupId': signal_group_id,
            'message': message,
        },
        'id': 'incident-portal-send',
    }
    data = json.dumps(payload).encode('utf-8')
    req = request.Request(
        rpc_url,
        data=data,
        headers={'Content-Type': 'application/json'},
        method='POST',
    )
    with request.urlopen(req, timeout=30) as resp:
        body = resp.read().decode('utf-8', errors='replace')
        parsed = json.loads(body)
        if 'error' in parsed:
            return False, f"Signal RPC error: {parsed['error']}"
        return True, body or 'notifikasi Signal berhasil dikirim via RPC'


def _send_via_signal_cli(signal_cli, signal_account, signal_group_id, message):
    cmd = [
        signal_cli,
        '-a', signal_account,
        'send',
        '-g', signal_group_id,
        '-m', message,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, check=False, timeout=60)
    if result.returncode != 0:
        detail = (result.stderr or result.stdout or '').strip() or f'exit {result.returncode}'
        return False, detail
    return True, (result.stdout or 'notifikasi Signal berhasil dikirim via CLI').strip()


def _send_via_telegram_bot(bot_token, chat_id, thread_id, message):
    if not bot_token or not chat_id:
        return False, 'Konfigurasi TELEGRAM_BOT_TOKEN atau TELEGRAM_GROUP_ID belum diisi'
    payload = {
        'chat_id': str(chat_id),
        'text': message,
    }
    if str(thread_id or '').strip():
        payload['message_thread_id'] = int(str(thread_id).strip())
    data = parse.urlencode(payload).encode('utf-8')
    req = request.Request(
        f'https://api.telegram.org/bot{bot_token}/sendMessage',
        data=data,
        headers={'Content-Type': 'application/x-www-form-urlencoded'},
        method='POST',
    )
    try:
        with request.urlopen(req, timeout=30) as resp:
            body = resp.read().decode('utf-8', errors='replace')
            parsed = json.loads(body or '{}')
            if not parsed.get('ok'):
                return False, f"Telegram API error: {parsed.get('description') or body or 'unknown error'}"
            return True, body or 'notifikasi Telegram berhasil dikirim'
    except error.HTTPError as exc:
        body = exc.read().decode('utf-8', errors='replace')
        try:
            parsed = json.loads(body or '{}')
        except Exception:
            parsed = {}
        description = parsed.get('description') or body or str(exc)
        if thread_id and 'message thread not found' in description.lower():
            payload.pop('message_thread_id', None)
            fallback_req = request.Request(
                f'https://api.telegram.org/bot{bot_token}/sendMessage',
                data=parse.urlencode(payload).encode('utf-8'),
                headers={'Content-Type': 'application/x-www-form-urlencoded'},
                method='POST',
            )
            with request.urlopen(fallback_req, timeout=30) as resp:
                fallback_body = resp.read().decode('utf-8', errors='replace')
                fallback_parsed = json.loads(fallback_body or '{}')
                if not fallback_parsed.get('ok'):
                    return False, f"Telegram API error: {fallback_parsed.get('description') or fallback_body or 'unknown error'}"
                return True, fallback_body or 'notifikasi Telegram berhasil dikirim tanpa thread'
        raise


def send_new_ticket_notification(ticket, incident_record=None):
    telegram_bot_token = current_app.config.get('TELEGRAM_BOT_TOKEN', '').strip()
    telegram_group_id = current_app.config.get('TELEGRAM_GROUP_ID', '').strip()
    telegram_topic_insiden_id = str(current_app.config.get('TELEGRAM_TOPIC_INSIDEN_ID', '') or '').strip()
    message = _build_message(ticket, incident_record=incident_record)

    if telegram_bot_token and telegram_group_id:
        try:
            return _send_via_telegram_bot(telegram_bot_token, telegram_group_id, telegram_topic_insiden_id, message)
        except Exception as telegram_exc:
            telegram_error = str(telegram_exc)
            if isinstance(telegram_exc, error.HTTPError):
                try:
                    telegram_error = telegram_exc.read().decode('utf-8', errors='replace') or str(telegram_exc)
                except Exception:
                    telegram_error = str(telegram_exc)
            return False, f'Notifikasi Telegram gagal: {telegram_error}'

    signal_account = current_app.config.get('SIGNAL_ACCOUNT', '').strip()
    signal_group_id = current_app.config.get('SIGNAL_GROUP_ID', '').strip()
    signal_cli = current_app.config.get('SIGNAL_CLI_PATH', '/usr/local/bin/signal-cli').strip()
    signal_http_url = current_app.config.get('SIGNAL_HTTP_URL', 'http://127.0.0.1:8080').strip()

    if not signal_account or not signal_group_id:
        return False, 'Konfigurasi Telegram belum lengkap dan SIGNAL_ACCOUNT atau SIGNAL_GROUP_ID belum diisi'

    try:
        return _send_via_signal_rpc(signal_http_url, signal_account, signal_group_id, message)
    except Exception as rpc_exc:
        rpc_error = str(rpc_exc)
        if isinstance(rpc_exc, error.HTTPError):
            try:
                rpc_error = rpc_exc.read().decode('utf-8', errors='replace') or str(rpc_exc)
            except Exception:
                rpc_error = str(rpc_exc)

    try:
        ok, detail = _send_via_signal_cli(signal_cli, signal_account, signal_group_id, message)
        if ok:
            return True, detail
        return False, f'RPC gagal: {rpc_error} | CLI gagal: {detail}'
    except subprocess.TimeoutExpired:
        return False, f'RPC gagal: {rpc_error} | CLI timeout saat mengirim notifikasi'
    except Exception as cli_exc:
        return False, f'RPC gagal: {rpc_error} | CLI gagal: {cli_exc}'
