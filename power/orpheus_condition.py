#!/usr/bin/env python3
"""systemd-ExecCondition: Orpheus für ein Ramona-Modell auch beim Boot auslassen."""
import re
import subprocess
from pathlib import Path
try:
    from .model_control import ModelControl
except ImportError:
    from model_control import ModelControl


def manual_start_active():
    try:
        result = subprocess.run(
            ['systemctl', '--user', 'is-active', '--quiet', 'orpheus-manual.target'],
            check=False,
        )
    except OSError:
        return False
    return result.returncode == 0


def should_start(control=None):
    if manual_start_active():
        return True
    control = control or ModelControl()
    configuration = control.dropin.read_text() if control.dropin.exists() else ''
    match = re.search(r'Environment="MODEL_PATH=(.*)"', configuration)
    model = Path(match[1]).name if match else None
    return control.voice(model) != 'ramona'


if __name__ == '__main__':
    raise SystemExit(0 if should_start() else 1)
