#!/usr/bin/env python3
import json
import os
import shlex
import subprocess
import sys
from pathlib import Path
from urllib import error, request

ROOT_DIR = Path(__file__).resolve().parent
DEFAULT_MODEL = os.environ.get("OLLAMA_MODEL", "qwen35-local")
OLLAMA_HOST = os.environ.get("OLLAMA_HOST", "http://127.0.0.1:11434")
MAX_FILE_CHARS = int(os.environ.get("CHAT_FILE_MAX_CHARS", "12000"))
MAX_WRITE_CHARS = int(os.environ.get("CHAT_WRITE_MAX_CHARS", "50000"))


def ensure_server_running() -> None:
    tags_url = f"{OLLAMA_HOST}/api/tags"
    try:
        with request.urlopen(tags_url, timeout=2) as resp:
            if resp.status == 200:
                return
    except Exception:
        pass

    start_script = ROOT_DIR / "start_ollama.sh"
    subprocess.run([str(start_script)], check=True)


def resolve_path(path_arg: str) -> Path:
    p = Path(path_arg)
    if not p.is_absolute():
        p = (Path.cwd() / p).resolve()
    return p


def ollama_stream_chat(model: str, messages: list[dict]) -> str:
    payload = {
        "model": model,
        "messages": messages,
        "stream": True,
    }
    data = json.dumps(payload).encode("utf-8")
    req = request.Request(
        f"{OLLAMA_HOST}/api/chat",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    full = []
    with request.urlopen(req, timeout=600) as resp:
        for raw in resp:
            raw = raw.strip()
            if not raw:
                continue
            obj = json.loads(raw.decode("utf-8", errors="replace"))
            msg = obj.get("message", {})
            token = msg.get("content", "")
            if token:
                print(token, end="", flush=True)
                full.append(token)
            if obj.get("done"):
                break
    print()
    return "".join(full)


def load_file_into_context(messages: list[dict], path_arg: str, max_chars: int) -> None:
    p = resolve_path(path_arg)

    if not p.exists():
        print(f"Fehler: Datei nicht gefunden: {p}")
        return
    if not p.is_file():
        print(f"Fehler: Kein Dateipfad: {p}")
        return

    try:
        content = p.read_text(encoding="utf-8", errors="replace")
    except Exception as exc:
        print(f"Fehler beim Lesen von {p}: {exc}")
        return

    truncated = False
    if len(content) > max_chars:
        content = content[:max_chars]
        truncated = True

    note = (
        f"Dateiinhalt aus {p} (als Kontext fuer folgende Antworten):\n"
        "```text\n"
        f"{content}\n"
        "```\n"
    )
    if truncated:
        note += f"[Hinweis: auf {max_chars} Zeichen gekuerzt.]\n"

    messages.append({"role": "user", "content": note})
    print(f"Datei in Kontext geladen: {p}")


def read_multiline(prompt: str = "... ") -> str:
    print("Mehrzeiliger Modus. Mit /end abschliessen, mit /cancel abbrechen.")
    lines = []
    while True:
        try:
            line = input(prompt)
        except (EOFError, KeyboardInterrupt):
            print("\nAbgebrochen.")
            return ""
        if line.strip() == "/cancel":
            return ""
        if line.strip() == "/end":
            return "\n".join(lines)
        lines.append(line)


def print_pending(pending: dict) -> None:
    op = pending.get("op")
    path = pending.get("path")
    print(f"Pending: {op} -> {path}")

    if op in {"write", "append"}:
        content = pending.get("content", "")
        preview = content[:400]
        print(f"Zeichen: {len(content)}")
        print("Vorschau:")
        print("---")
        print(preview)
        if len(content) > len(preview):
            print("...[gekuerzt]")
        print("---")
    elif op == "replace":
        old = pending.get("old", "")
        new = pending.get("new", "")
        print(f"Replace: {old!r} -> {new!r}")

    print("Bestaetigen mit /confirm oder verwerfen mit /cancel")


def execute_pending(pending: dict) -> None:
    op = pending["op"]
    path = Path(pending["path"])
    path.parent.mkdir(parents=True, exist_ok=True)

    if op == "write":
        path.write_text(pending["content"], encoding="utf-8")
        print(f"Geschrieben: {path}")
        return

    if op == "append":
        content = pending["content"]
        needs_nl = False
        if path.exists() and path.is_file() and path.stat().st_size > 0:
            existing = path.read_text(encoding="utf-8", errors="replace")
            needs_nl = not existing.endswith("\n") and not content.startswith("\n")
        with path.open("a", encoding="utf-8") as f:
            if needs_nl:
                f.write("\n")
            f.write(content)
        print(f"Angehaengt: {path}")
        return

    if op == "replace":
        if not path.exists() or not path.is_file():
            print(f"Fehler: Datei nicht gefunden: {path}")
            return
        text = path.read_text(encoding="utf-8", errors="replace")
        old = pending["old"]
        new = pending["new"]
        count = text.count(old)
        if count == 0:
            print("Hinweis: Suchtext nicht gefunden, keine Aenderung.")
            return
        path.write_text(text.replace(old, new), encoding="utf-8")
        print(f"Ersetzt in {path}: {count} Treffer")
        return


def print_help() -> None:
    print("Befehle:")
    print("  /help                               Hilfe")
    print("  /read <pfad>                        Datei in den Chat-Kontext laden")
    print("  /read <pfad> <max_chars>            Datei mit eigener Kuerzung laden")
    print("  /write <pfad>                       Datei neu schreiben (mehrzeilig)")
    print("  /append <pfad>                      Text an Datei anhaengen (mehrzeilig)")
    print("  /replace <pfad> <alt> <neu>         Text in Datei ersetzen")
    print("  /confirm                            Pending Schreibaktion ausfuehren")
    print("  /cancel                             Pending Schreibaktion verwerfen")
    print("  /clear                              Verlauf zuruecksetzen")
    print("  /exit                               Beenden")


def main() -> int:
    model = DEFAULT_MODEL
    if len(sys.argv) > 1:
        model = sys.argv[1]

    ensure_server_running()

    messages: list[dict] = []
    pending_action: dict | None = None

    print(f"Modell: {model}")
    print("Tip: /read README.md und danach normal eine Frage stellen.")
    print_help()

    while True:
        try:
            user = input("\n>>> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nBeendet.")
            return 0

        if not user:
            continue

        if user == "/exit":
            print("Beendet.")
            return 0
        if user == "/help":
            print_help()
            continue
        if user == "/clear":
            messages = []
            print("Verlauf geleert.")
            continue

        if user == "/cancel":
            pending_action = None
            print("Pending Aktion verworfen.")
            continue

        if user == "/confirm":
            if pending_action is None:
                print("Keine Pending Aktion vorhanden.")
                continue
            try:
                execute_pending(pending_action)
            except Exception as exc:
                print(f"Fehler beim Schreiben: {exc}")
            pending_action = None
            continue

        if user.startswith("/read "):
            try:
                parts = shlex.split(user)
            except ValueError as exc:
                print(f"Fehler beim Parsen: {exc}")
                continue

            if len(parts) < 2:
                print("Nutzung: /read <pfad> [max_chars]")
                continue

            path_arg = parts[1]
            max_chars = MAX_FILE_CHARS
            if len(parts) >= 3:
                try:
                    max_chars = int(parts[2])
                except ValueError:
                    print("max_chars muss eine Zahl sein.")
                    continue

            load_file_into_context(messages, path_arg, max_chars)
            continue

        if user.startswith("/write "):
            try:
                parts = shlex.split(user)
            except ValueError as exc:
                print(f"Fehler beim Parsen: {exc}")
                continue
            if len(parts) < 2:
                print("Nutzung: /write <pfad>")
                continue
            content = read_multiline()
            if content == "":
                print("Abgebrochen.")
                continue
            if len(content) > MAX_WRITE_CHARS:
                print(f"Zu gross: {len(content)} Zeichen (Limit: {MAX_WRITE_CHARS})")
                continue
            pending_action = {
                "op": "write",
                "path": str(resolve_path(parts[1])),
                "content": content,
            }
            print_pending(pending_action)
            continue

        if user.startswith("/append "):
            try:
                parts = shlex.split(user)
            except ValueError as exc:
                print(f"Fehler beim Parsen: {exc}")
                continue
            if len(parts) < 2:
                print("Nutzung: /append <pfad>")
                continue
            content = read_multiline()
            if content == "":
                print("Abgebrochen.")
                continue
            if len(content) > MAX_WRITE_CHARS:
                print(f"Zu gross: {len(content)} Zeichen (Limit: {MAX_WRITE_CHARS})")
                continue
            pending_action = {
                "op": "append",
                "path": str(resolve_path(parts[1])),
                "content": content,
            }
            print_pending(pending_action)
            continue

        if user.startswith("/replace "):
            try:
                parts = shlex.split(user)
            except ValueError as exc:
                print(f"Fehler beim Parsen: {exc}")
                continue
            if len(parts) != 4:
                print('Nutzung: /replace <pfad> "alt" "neu"')
                continue
            pending_action = {
                "op": "replace",
                "path": str(resolve_path(parts[1])),
                "old": parts[2],
                "new": parts[3],
            }
            print_pending(pending_action)
            continue

        messages.append({"role": "user", "content": user})
        try:
            assistant = ollama_stream_chat(model, messages)
        except error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            print(f"HTTP-Fehler {exc.code}: {body}")
            messages.pop()
            continue
        except Exception as exc:
            print(f"Fehler bei Anfrage: {exc}")
            messages.pop()
            continue

        messages.append({"role": "assistant", "content": assistant})


if __name__ == "__main__":
    raise SystemExit(main())
