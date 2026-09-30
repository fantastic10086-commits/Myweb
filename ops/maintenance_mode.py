#!/usr/bin/env python3
"""Safely switch PI Manager maintenance mode from the server command line."""

import argparse
import json
import os
import tempfile


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('state', choices=('on', 'off', 'status'))
    parser.add_argument('--settings', default=os.environ.get('SETTINGS_FILE', '/var/lib/pi-manager/settings.json'))
    parser.add_argument('--message', default='系统正在升级维护，请稍后再试。')
    parser.add_argument('--until', default='')
    args = parser.parse_args()

    data = {}
    if os.path.exists(args.settings):
        with open(args.settings, encoding='utf-8') as stream:
            data = json.load(stream)

    if args.state == 'status':
        print('on' if str(data.get('maintenance_enabled', '0')).lower() in {'1', 'true', 'yes', 'on'} else 'off')
        return

    data['maintenance_enabled'] = '1' if args.state == 'on' else '0'
    if args.state == 'on':
        data['maintenance_message'] = args.message.strip() or '系统正在升级维护，请稍后再试。'
        data['maintenance_until'] = args.until.strip()

    directory = os.path.dirname(args.settings) or '.'
    os.makedirs(directory, exist_ok=True)
    fd, temp_path = tempfile.mkstemp(prefix='.settings-', dir=directory, text=True)
    try:
        with os.fdopen(fd, 'w', encoding='utf-8') as stream:
            json.dump(data, stream, ensure_ascii=False, indent=2)
            stream.flush()
            os.fsync(stream.fileno())
        os.chmod(temp_path, 0o600)
        os.replace(temp_path, args.settings)
    finally:
        if os.path.exists(temp_path):
            os.remove(temp_path)
    print(args.state)


if __name__ == '__main__':
    main()
