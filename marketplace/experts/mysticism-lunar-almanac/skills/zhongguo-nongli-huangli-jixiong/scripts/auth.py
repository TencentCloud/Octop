#!/usr/bin/env python3
"""CLI device authorization helper for Huangli toolkit.

Canonical usage (recommended from any project/root directory):
    python3 skills/zhongguo-nongli-huangli-jixiong/auth.py login --username=<username> --password=<password>
    python3 skills/zhongguo-nongli-huangli-jixiong/auth.py register --username=<username> --email=<email>
    python3 skills/zhongguo-nongli-huangli-jixiong/auth.py status

Short usage (only when current directory is this installed skill folder):
    python3 auth.py login --username=<username> --password=<password>
    python3 auth.py register --username=<username> --email=<email>
    python3 auth.py status
    python3 auth.py login --print-shell

Security behavior:
    - Does not write token/env files by default.
    - Does not modify shell profile files (e.g. ~/.zshrc).
    - Prints shell exports for one-session use.

Env vars:
    HUANGLI_BASE       Optional API base, default https://api.nongli.skill.4glz.com
    HUANGLI_USERNAME   Optional default username for CLI login/register
    HUANGLI_EMAIL      Optional default email for CLI register
    HUANGLI_PASSWORD   Optional password override for CLI login/register
    HUANGLI_TOKEN      Token for status verify / direct API calls
"""
import json
import os
import secrets
import string
import sys
import time
import webbrowser
import urllib.request
import urllib.error

BASE = os.environ.get('HUANGLI_BASE', 'https://api.nongli.skill.4glz.com').rstrip('/')


def post_json(url, payload):
    body = json.dumps(payload).encode('utf-8')
    req = urllib.request.Request(url, data=body, method='POST', headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req) as resp:
        return resp.getcode(), json.loads(resp.read())


def get_json(url, headers=None):
    req = urllib.request.Request(url, headers=headers or {})
    with urllib.request.urlopen(req) as resp:
        return resp.getcode(), json.loads(resp.read())


def random_password(length=18):
    alphabet = string.ascii_letters + string.digits
    return ''.join(secrets.choice(alphabet) for _ in range(length))


def read_flag(flag_name):
    prefix = f'{flag_name}='
    for arg in sys.argv[1:]:
        if arg.startswith(prefix):
            return arg[len(prefix):].strip()
    return ''


def read_option(flag_name, env_name=''):
    value = read_flag(flag_name)
    if value:
        return value
    key = env_name or flag_name.lstrip('-').replace('-', '_').upper()
    return os.environ.get(key, '').strip()


def mask_secret(value, keep=4):
    if not value:
        return ''
    if len(value) <= keep:
        return '*' * len(value)
    return '*' * (len(value) - keep) + value[-keep:]


def cmd_agent(action, username, email, password):
    """One-step agent mode: mode=agent, no browser, no polling."""
    start_payload = {
        'action': action,
        'username': username,
        'password': password,
        'mode': 'agent',
    }
    if action == 'register':
        start_payload['email'] = email

    try:
        code, data = post_json(f'{BASE}/api/auth/cli/device/start', start_payload)
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')
        try:
            err_json = json.loads(body)
            body = err_json.get('error', err_json.get('message', body))
        except Exception:
            pass
        print(f'Error: HTTP {e.code} — {body}', file=sys.stderr)
        return 1
    except urllib.error.URLError as e:
        print(f'Error: Cannot connect to {BASE}\n{e.reason}', file=sys.stderr)
        return 1

    err = data.get('error')
    if err:
        print(f"Error: {data.get('message') or err}", file=sys.stderr)
        return 1

    token = data.get('access_token')
    if not token:
        print('Error: No access_token in agent-mode response', file=sys.stderr)
        return 1

    exports = shell_exports(token, BASE).strip()
    print(f'\nAgent mode authorization successful (mode=agent, one-step).')
    print(f'Username: {data.get("username")}')
    if action == 'register':
        print(f'Email: {email}')
        print(f'Generated password: {password}')
        print(f'Masked password: {mask_secret(password)}')
    if print_shell:
        print('\n# shell exports')
        print(exports)
    else:
        print('\nRun in your current shell session:')
        print(exports)
    print('\nFor persistence, store HUANGLI_TOKEN via your own secret manager.')
    return 0


def shell_quote(value):
    return value.replace("'", "'\"'\"'")


def shell_exports(access_token, base_url):
    return (
        f"export HUANGLI_TOKEN='{shell_quote(access_token)}'\n"
        f"export HUANGLI_BASE='{shell_quote(base_url)}'\n"
    )


def show_status():
    print('=== Huangli CLI Status ===')
    print(f'API Base: {BASE}')

    token = os.environ.get('HUANGLI_TOKEN', '').strip()
    if not token:
        print('Token status: missing')
        print('Hint: export HUANGLI_TOKEN first, or run login/register and source printed exports.')
        return 1

    try:
        _, data = get_json(
            f'{BASE}/api/auth/verify',
            headers={'Authorization': f'Bearer {token}'}
        )
        print('Token status: valid')
        print(f"User: {data.get('username')} (id={data.get('user_id')})")
        print(f"Session type: {data.get('session_type')}")
        return 0
    except urllib.error.HTTPError as e:
        body = e.read().decode('utf-8', errors='replace')
        print(f'Token status: invalid (HTTP {e.code})')
        if body:
            print(body)
        return 1
    except urllib.error.URLError as e:
        print(f'Network error: {e.reason}')
        return 1


def main():
    global print_shell
    action = 'login'
    print_shell = '--print-shell' in sys.argv
    agent_mode = '--agent' in sys.argv or read_option('--mode') == 'agent'
    auto_agent = os.environ.get('HUANGLI_AUTO_AGENT', '').strip().lower() in {'1', 'true', 'yes'}
    agent_mode = agent_mode or auto_agent

    positional = [arg for arg in sys.argv[1:] if not arg.startswith('--')]
    if positional:
        action = positional[0].strip().lower()

    if action not in {'login', 'register', 'status'}:
        print('Usage (canonical): python3 skills/zhongguo-nongli-huangli-jixiong/auth.py [login|register|status] [--username=<name>] [--email=<email>] [--password=<password>] [--agent] [--print-shell]', file=sys.stderr)
        print('Usage (short, only inside skill folder): python3 auth.py [login|register|status] [--username=<name>] [--email=<email>] [--password=<password>] [--agent] [--print-shell]', file=sys.stderr)
        sys.exit(1)

    if action == 'status':
        sys.exit(show_status())

    username = read_option('--username', 'HUANGLI_USERNAME')
    email = read_option('--email', 'HUANGLI_EMAIL')
    password = read_option('--password', 'HUANGLI_PASSWORD')

    # ── Agent mode: one-step, no browser ────────────────────────────────────
    if agent_mode:
        if not username:
            print('Error: agent mode requires --username or HUANGLI_USERNAME', file=sys.stderr)
            sys.exit(1)
        if action == 'login':
            if not password and not os.environ.get('HUANGLI_PASSWORD'):
                print('Error: agent mode login requires --password or HUANGLI_PASSWORD', file=sys.stderr)
                sys.exit(1)
        if action == 'register':
            if not email:
                email = f'{username}@agent.local'
            if not password:
                password = random_password()
        sys.exit(cmd_agent(action, username, email, password))

    # ── Standard browser-based device authorization flow ─────────────────────
    if action == 'login':
        if not username:
            print('Error: login requires --username or HUANGLI_USERNAME', file=sys.stderr)
            sys.exit(1)
        if not password:
            print('Error: login requires --password or HUANGLI_PASSWORD', file=sys.stderr)
            sys.exit(1)
    else:
        if not username:
            print('Error: register requires --username or HUANGLI_USERNAME', file=sys.stderr)
            sys.exit(1)
        if not email:
            email = f'{username}@cli.local'
        if not password:
            password = random_password()

    start_payload = {
        'action': action,
        'username': username,
        'password': password,
    }
    if action == 'register':
        start_payload['email'] = email

    try:
        _, start = post_json(f'{BASE}/api/auth/cli/device/start', start_payload)
    except urllib.error.HTTPError as e:
        print(f'Error: HTTP {e.code} while starting device auth', file=sys.stderr)
        print(e.read().decode('utf-8', errors='replace'), file=sys.stderr)
        sys.exit(1)
    except urllib.error.URLError as e:
        print(f'Error: Cannot connect to {BASE}\n{e.reason}', file=sys.stderr)
        sys.exit(1)

    device_code = start['device_code']
    interval = int(start.get('interval', 5))
    verify_url = start['verification_uri_complete']
    user_code = start['user_code']

    print('\n=== Huangli CLI Authorization ===')
    print(f'Action: {action}')
    print(f'Username: {start.get("username") or username}')
    if action == 'register':
        print(f'Email: {email}')
        print(f'Generated password: {password}')
        print(f'Masked password: {mask_secret(password)}')
    print(f'User code: {user_code}')
    print(f'Open this URL in your browser and confirm device binding:\n{verify_url}\n')

    try:
        webbrowser.open(verify_url)
        print('Browser opened automatically. If not, copy the URL above.\n')
    except Exception:
        pass

    while True:
        time.sleep(interval)
        try:
            status, data = post_json(f'{BASE}/api/auth/cli/device/poll', {'device_code': device_code})
            _ = status
        except urllib.error.HTTPError as e:
            body = e.read().decode('utf-8', errors='replace')
            try:
                data = json.loads(body)
            except Exception:
                data = {'error': body or f'HTTP {e.code}'}

            if e.code == 428 and data.get('error') == 'authorization_pending':
                print('Waiting for browser device confirmation...')
                interval = int(data.get('interval', interval))
                continue
            if e.code == 429 and data.get('error') == 'slow_down':
                interval = int(data.get('interval', interval))
                print(f'Slow down requested. Polling every {interval}s...')
                continue
            print(f"Authorization failed: {data.get('message') or data.get('error')}", file=sys.stderr)
            sys.exit(1)
        except urllib.error.URLError as e:
            print(f'Network error: {e.reason}', file=sys.stderr)
            sys.exit(1)

        exports = shell_exports(data['access_token'], BASE).strip()

        print('Authorization successful.')
        print('No local token/env files were written.')
        print('No shell profile files were modified.')
        if print_shell:
            print('\n# shell exports')
            print(exports)
        else:
            print('\nRun in your current shell session:')
            print(exports)
        print('For persistence, store HUANGLI_TOKEN via your own secret manager or shell profile policy.')
        print('Note: logout and device unbinding must be done from the web dashboard for security.')
        break


if __name__ == '__main__':
    main()
