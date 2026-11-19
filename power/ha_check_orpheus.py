#!/usr/bin/env python3
"""Liest die Orpheus-Bereitschaft aus dem lokalen Router, ohne Workstation-Zugriff."""

import http.client
import json
import urllib.request


def ready(url="http://127.0.0.1:11436/status"):
    try:
        with urllib.request.urlopen(url, timeout=1) as response:
            data = json.load(response)
        return data["services"]["orpheus"]["available"] is True
    except (OSError, ValueError, KeyError, TypeError, http.client.HTTPException):
        return False


if __name__ == "__main__":
    print("ON" if ready() else "OFF")
