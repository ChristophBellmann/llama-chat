#!/usr/bin/env python3
"""systemd-ExecCondition: Orpheus für ein Ramona-Modell auch beim Boot auslassen."""
import re
from pathlib import Path
from model_control import ModelControl

if __name__ == '__main__':
    control = ModelControl()
    configuration = control.dropin.read_text() if control.dropin.exists() else ''
    match = re.search(r'Environment="MODEL_PATH=(.*)"', configuration)
    model = Path(match[1]).name if match else None
    raise SystemExit(1 if control.voice(model) == 'ramona' else 0)
