"""
PhoneDesk Server — full-featured phone trackpad/keyboard
Requirements: pip install fastapi uvicorn websockets pyautogui qrcode pillow
Run: python server.py
Then open http://<your-ip>:8000 on your phone
"""

import asyncio
import json
import socket
import math
import time
import platform
import subprocess
import os
import re
import ctypes
import uuid
import ipaddress
import webbrowser
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
import qrcode
import io
import base64
import pyautogui
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Request
from fastapi.responses import HTMLResponse, Response
from pathlib import Path
from urllib.error import URLError, HTTPError
from urllib.request import Request as UrlRequest, urlopen

pyautogui.FAILSAFE = False
pyautogui.PAUSE = 0

app = FastAPI()

# Track connected clients
clients: set[WebSocket] = set()

# Acceleration state per client
client_state: dict = {}

APP_PIN = os.getenv("TRACKPAD_PIN", "").strip()
CUSTOM_APPS_FILE = Path("quick_launch_custom.json")
custom_apps_cache: dict[str, dict] = {}
CUSTOM_MACROS_FILE = Path("macros_custom.json")
MACRO_USAGE_FILE = Path("macro_usage.json")
custom_macros_cache: dict[str, dict] = {}
macro_usage_cache: dict[str, dict] = {}
SHARE_DIR = Path("shared_files")
SHARE_RECENT_FILE = Path("share_recent.json")
share_recent_cache: list[dict] = []
DESKTOP_ID_FILE = Path("desktop_id.txt")
INVITE_STATE_FILE = Path("invite_state.json")
DISCOVERY_RADIUS = max(0, int(os.getenv("TRACKPAD_DISCOVERY_RADIUS", "4")))


def mask_to_prefix(mask: str) -> int | None:
    try:
        return ipaddress.IPv4Network(f"0.0.0.0/{mask}").prefixlen
    except Exception:
        return None

def get_local_ip():
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("8.8.8.8", 80))
        return s.getsockname()[0]
    finally:
        s.close()


def is_private_ipv4(value: str) -> bool:
    try:
        return ipaddress.ip_address(value).is_private
    except Exception:
        return False


def parse_windows_private_ipv4_pairs() -> list[tuple[str, int]]:
    if platform.system() != "Windows":
        return []
    try:
        output = subprocess.check_output(["ipconfig"], text=True, errors="ignore")
    except Exception:
        return []

    pairs: list[tuple[str, int]] = []
    current_ip = ""
    for line in output.splitlines():
        ip_match = re.search(r"IPv4 Address[^:]*:\s*([0-9.]+)", line)
        if ip_match:
            candidate = ip_match.group(1).strip()
            current_ip = candidate if is_private_ipv4(candidate) else ""
            continue

        mask_match = re.search(r"Subnet Mask[^:]*:\s*([0-9.]+)", line)
        if mask_match and current_ip:
            prefix = mask_to_prefix(mask_match.group(1).strip())
            if prefix is not None:
                pairs.append((current_ip, prefix))
            current_ip = ""
    return pairs


def build_candidate_networks() -> list[ipaddress.IPv4Network]:
    networks: list[ipaddress.IPv4Network] = []
    seen: set[str] = set()

    def add_network(net: ipaddress.IPv4Network) -> None:
        key = str(net)
        if key not in seen:
            seen.add(key)
            networks.append(net)

    def add_network_radius(ip_value: str, prefix: int) -> None:
        try:
            ip_obj = ipaddress.ip_address(ip_value)
        except Exception:
            return
        if not isinstance(ip_obj, ipaddress.IPv4Address):
            return
        if prefix >= 24:
            add_network(ipaddress.ip_network(f"{ip_obj}/{prefix}", strict=False))
            return

        octets = ip_value.split(".")
        if len(octets) != 4:
            return
        first_two = ".".join(octets[:2])
        third = int(octets[2])
        for offset in range(-DISCOVERY_RADIUS, DISCOVERY_RADIUS + 1):
            candidate_third = third + offset
            if 0 <= candidate_third <= 255:
                add_network(ipaddress.ip_network(f"{first_two}.{candidate_third}.0/24", strict=False))

    windows_pairs = parse_windows_private_ipv4_pairs()
    if windows_pairs:
        for ip_value, prefix in windows_pairs:
            add_network_radius(ip_value, prefix)

    local_ip = get_local_ip()
    add_network_radius(local_ip, 24)

    extra_subnets = os.getenv("TRACKPAD_DISCOVERY_SUBNETS", "").strip()
    if extra_subnets:
        for part in re.split(r"[;,\s]+", extra_subnets):
            if not part:
                continue
            try:
                net = ipaddress.ip_network(part, strict=False)
                if isinstance(net, ipaddress.IPv4Network):
                    add_network(net)
            except Exception:
                continue

    return networks


def get_local_subnet_hosts() -> list[str]:
    local_ip = get_local_ip()
    hosts: list[str] = []
    seen_hosts: set[str] = set()
    for net in build_candidate_networks():
        for host in net.hosts():
            host_str = str(host)
            if host_str not in seen_hosts and host_str != local_ip:
                seen_hosts.add(host_str)
                hosts.append(host_str)
    return hosts


def fetch_remote_desktop(host: str) -> dict | None:
    try:
        req = UrlRequest(
            f"http://{host}:8000/desktop",
            headers={"User-Agent": "Trackpad-Pro-Discovery"},
        )
        with urlopen(req, timeout=0.35) as response:
            raw = response.read().decode("utf-8")
        data = json.loads(raw)
        if not isinstance(data, dict):
            return None
        ws_url = str(data.get("ws", f"ws://{host}:8000/ws"))
        return {
            "id": str(data.get("id", host)),
            "name": str(data.get("name", host)),
            "ip": str(data.get("ip", host)),
            "ws": ws_url,
            "invite": str(data.get("invite", "")),
        }
    except (URLError, HTTPError, TimeoutError, json.JSONDecodeError, ValueError, OSError):
        return None


def discover_nearby_desktops() -> list[dict]:
    hosts = get_local_subnet_hosts()
    if not hosts:
        return []
    found: list[dict] = []
    with ThreadPoolExecutor(max_workers=24) as executor:
        futures = [executor.submit(fetch_remote_desktop, host) for host in hosts]
        for future in as_completed(futures):
            result = future.result()
            if result:
                found.append(result)
    found.sort(key=lambda item: (item.get("name", ""), item.get("ip", "")))
    return found


def generate_qr(url: str) -> str:
    qr = qrcode.QRCode(box_size=4, border=2)
    qr.add_data(url)
    qr.make(fit=True)
    img = qr.make_image(fill_color="black", back_color="white")
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return base64.b64encode(buf.getvalue()).decode()


def get_machine_name() -> str:
    return platform.node() or "Desktop"


def get_desktop_id() -> str:
    if DESKTOP_ID_FILE.exists():
        try:
            value = DESKTOP_ID_FILE.read_text(encoding="utf-8").strip()
            if value:
                return value
        except Exception:
            pass
    desktop_id = uuid.uuid4().hex[:12]
    try:
        DESKTOP_ID_FILE.write_text(desktop_id, encoding="utf-8")
    except Exception:
        pass
    return desktop_id


def build_desktop_invite(ws_url: str) -> str:
    payload = {
        "id": get_desktop_id(),
        "name": get_machine_name(),
        "ws": ws_url,
    }
    raw = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_desktop_invite(invite: str) -> dict | None:
    token = (invite or "").strip()
    if not token:
        return None
    padding = "=" * (-len(token) % 4)
    try:
        raw = base64.urlsafe_b64decode(token + padding)
        data = json.loads(raw.decode("utf-8"))
        if isinstance(data, dict) and isinstance(data.get("ws"), str):
            return {
                "id": str(data.get("id", "")),
                "name": str(data.get("name", "Desktop")),
                "ws": str(data.get("ws", "")),
            }
    except Exception:
        return None
    return None


def load_invite_state() -> dict:
    default_state = {
        "current": None,
        "lastDecision": "",
        "lastDecisionAt": "",
    }
    if not INVITE_STATE_FILE.exists():
        return default_state
    try:
        data = json.loads(INVITE_STATE_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            default_state.update({
                "current": data.get("current"),
                "lastDecision": str(data.get("lastDecision", "")),
                "lastDecisionAt": str(data.get("lastDecisionAt", "")),
            })
    except Exception:
        pass
    return default_state


def save_invite_state(state: dict) -> None:
    try:
        INVITE_STATE_FILE.write_text(json.dumps(state, indent=2), encoding="utf-8")
    except Exception:
        pass


def set_current_invite(message: str, sender: dict) -> dict:
    state = load_invite_state()
    invite = {
        "id": f"invite-{int(time.time() * 1000)}",
        "message": message,
        "sender": sender,
        "status": "pending",
        "createdAt": now_iso(),
        "respondedAt": "",
    }
    state["current"] = invite
    state["lastDecision"] = ""
    state["lastDecisionAt"] = ""
    save_invite_state(state)
    return invite


def respond_current_invite(decision: str) -> dict | None:
    state = load_invite_state()
    current = state.get("current")
    if not isinstance(current, dict):
        return None
    current["status"] = decision
    current["respondedAt"] = now_iso()
    state["current"] = current
    state["lastDecision"] = decision
    state["lastDecisionAt"] = now_iso()
    save_invite_state(state)
    return current


def get_current_invite() -> dict | None:
    state = load_invite_state()
    current = state.get("current")
    if isinstance(current, dict):
        return current
    return None


def invite_status_summary() -> dict:
    state = load_invite_state()
    current = state.get("current")
    if isinstance(current, dict):
        return {
            "status": str(current.get("status", "pending")),
            "message": str(current.get("message", "")),
            "sender": current.get("sender", {}),
            "createdAt": str(current.get("createdAt", "")),
        }
    return {
        "status": "idle",
        "message": "",
        "sender": {},
        "createdAt": "",
    }


def is_auth_required() -> bool:
    return bool(APP_PIN)


def slugify_app_id(name: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "_", name.strip().lower())
    value = re.sub(r"_+", "_", value).strip("_")
    return value or f"app_{int(time.time())}"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def slugify_macro_id(name: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "_", name.strip().lower())
    value = re.sub(r"_+", "_", value).strip("_")
    return value or f"macro_{int(time.time())}"


def get_app_command_map() -> dict[str, list[str]]:
    system_name = platform.system()
    if system_name == "Windows":
        return {
            "chrome": ["cmd", "/c", "start", "", "chrome"],
            "edge": ["cmd", "/c", "start", "", "msedge"],
            "vscode": ["cmd", "/c", "start", "", "code"],
            "explorer": ["explorer"],
            "terminal": ["cmd", "/c", "start", "", "wt"],
            "notepad": ["notepad"],
            "taskmgr": ["taskmgr"],
            "settings": ["cmd", "/c", "start", "", "ms-settings:"],
            "spotify": ["cmd", "/c", "start", "", "spotify"],
        }
    if system_name == "Darwin":
        return {
            "chrome": ["open", "-a", "Google Chrome"],
            "safari": ["open", "-a", "Safari"],
            "vscode": ["open", "-a", "Visual Studio Code"],
            "finder": ["open", "-a", "Finder"],
            "terminal": ["open", "-a", "Terminal"],
            "spotify": ["open", "-a", "Spotify"],
        }
    return {
        "chrome": ["google-chrome"],
        "firefox": ["firefox"],
        "vscode": ["code"],
        "files": ["xdg-open", "."],
        "terminal": ["x-terminal-emulator"],
        "spotify": ["spotify"],
    }


def load_custom_apps() -> dict[str, dict]:
    global custom_apps_cache
    if custom_apps_cache:
        return custom_apps_cache
    if not CUSTOM_APPS_FILE.exists():
        custom_apps_cache = {}
        return custom_apps_cache
    try:
        data = json.loads(CUSTOM_APPS_FILE.read_text(encoding="utf-8"))
        if isinstance(data, dict):
            valid = {}
            for app_id, item in data.items():
                if not isinstance(item, dict):
                    continue
                cmd = item.get("command")
                name = item.get("name", app_id)
                if isinstance(cmd, list) and cmd:
                    valid[app_id] = {"name": str(name), "command": [str(x) for x in cmd]}
            custom_apps_cache = valid
        else:
            custom_apps_cache = {}
    except Exception:
        custom_apps_cache = {}
    return custom_apps_cache


def save_custom_apps() -> None:
    try:
        CUSTOM_APPS_FILE.write_text(json.dumps(custom_apps_cache, indent=2), encoding="utf-8")
    except Exception:
        pass


def load_custom_macros() -> dict[str, dict]:
    global custom_macros_cache
    if custom_macros_cache:
        return custom_macros_cache
    if not CUSTOM_MACROS_FILE.exists():
        custom_macros_cache = {}
        return custom_macros_cache
    try:
        data = json.loads(CUSTOM_MACROS_FILE.read_text(encoding="utf-8"))
        valid: dict[str, dict] = {}
        if isinstance(data, dict):
            for macro_id, item in data.items():
                if not isinstance(item, dict):
                    continue
                name = str(item.get("name", macro_id)).strip()
                steps = item.get("steps", [])
                if validate_macro_steps(steps):
                    valid[macro_id] = {"name": name, "steps": steps}
        custom_macros_cache = valid
    except Exception:
        custom_macros_cache = {}
    return custom_macros_cache


def save_custom_macros() -> None:
    try:
        CUSTOM_MACROS_FILE.write_text(json.dumps(custom_macros_cache, indent=2), encoding="utf-8")
    except Exception:
        pass


def load_macro_usage() -> dict[str, dict]:
    global macro_usage_cache
    if macro_usage_cache:
        return macro_usage_cache
    if not MACRO_USAGE_FILE.exists():
        macro_usage_cache = {}
        return macro_usage_cache
    try:
        data = json.loads(MACRO_USAGE_FILE.read_text(encoding="utf-8"))
        valid: dict[str, dict] = {}
        if isinstance(data, dict):
            for macro_id, item in data.items():
                if isinstance(item, dict):
                    count = int(item.get("count", 0))
                    last_used = str(item.get("lastUsedAt", ""))
                    valid[macro_id] = {"count": max(0, count), "lastUsedAt": last_used}
        macro_usage_cache = valid
    except Exception:
        macro_usage_cache = {}
    return macro_usage_cache


def save_macro_usage() -> None:
    try:
        MACRO_USAGE_FILE.write_text(json.dumps(macro_usage_cache, indent=2), encoding="utf-8")
    except Exception:
        pass


def load_share_recent() -> list[dict]:
    global share_recent_cache
    if share_recent_cache:
        return share_recent_cache
    if not SHARE_RECENT_FILE.exists():
        share_recent_cache = []
        return share_recent_cache
    try:
        data = json.loads(SHARE_RECENT_FILE.read_text(encoding="utf-8"))
        if isinstance(data, list):
            share_recent_cache = [item for item in data if isinstance(item, dict)]
        else:
            share_recent_cache = []
    except Exception:
        share_recent_cache = []
    return share_recent_cache


def save_share_recent() -> None:
    try:
        SHARE_RECENT_FILE.write_text(json.dumps(load_share_recent(), indent=2), encoding="utf-8")
    except Exception:
        pass


def push_share_recent(item: dict) -> None:
    recent = load_share_recent()
    recent.insert(0, item)
    del recent[20:]
    save_share_recent()


def normalize_share_target(target: str) -> Path:
    value = (target or "").strip().lower()
    if value == "downloads":
        return Path.home() / "Downloads"
    if value == "desktop":
        return Path.home() / "Desktop"
    return SHARE_DIR


def safe_share_filename(name: str, default_ext: str = "") -> str:
    raw = (name or "").strip().replace("\\", "/")
    raw = raw.split("/")[-1].strip()
    raw = re.sub(r"[^a-zA-Z0-9._-]+", "_", raw)
    raw = raw.strip("._-")
    if not raw:
        raw = f"shared_{int(time.time())}"
    if default_ext and "." not in raw:
        raw += default_ext
    return raw


def decode_data_url(data_url: str) -> tuple[bytes, str, str]:
    raw = (data_url or "").strip()
    if raw.startswith("data:") and "," in raw:
        header, payload = raw.split(",", 1)
        mime = header[5:].split(";")[0].strip() or "application/octet-stream"
        extension = {
            "image/png": ".png",
            "image/jpeg": ".jpg",
            "image/jpg": ".jpg",
            "image/gif": ".gif",
            "image/webp": ".webp",
            "text/plain": ".txt",
            "application/pdf": ".pdf",
        }.get(mime, "")
        return base64.b64decode(payload), mime, extension
    return base64.b64decode(raw), "application/octet-stream", ""


def set_clipboard_text(text: str) -> bool:
    value = str(text or "")
    if not value:
        return False
    try:
        system_name = platform.system()
        if system_name == "Windows":
            subprocess.run(["cmd", "/c", "clip"], input=value, text=True, check=True)
            return True
        if system_name == "Darwin":
            subprocess.run(["pbcopy"], input=value, text=True, check=True)
            return True
        try:
            subprocess.run(["xclip", "-selection", "clipboard"], input=value, text=True, check=True)
            return True
        except Exception:
            try:
                subprocess.run(["xsel", "--clipboard", "--input"], input=value, text=True, check=True)
                return True
            except Exception:
                import tkinter as tk

                root = tk.Tk()
                root.withdraw()
                root.clipboard_clear()
                root.clipboard_append(value)
                root.update()
                root.destroy()
                return True
    except Exception:
        return False


def set_clipboard_image(image_bytes: bytes) -> bool:
    if platform.system() != "Windows":
        return False
    try:
        from PIL import Image

        image = Image.open(io.BytesIO(image_bytes)).convert("RGB")
        bitmap = io.BytesIO()
        image.save(bitmap, "BMP")
        dib = bitmap.getvalue()[14:]

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        CF_DIB = 8
        GMEM_MOVEABLE = 0x0002

        if not user32.OpenClipboard(None):
            return False
        try:
            user32.EmptyClipboard()
            handle = kernel32.GlobalAlloc(GMEM_MOVEABLE, len(dib))
            if not handle:
                return False
            locked = kernel32.GlobalLock(handle)
            if not locked:
                kernel32.GlobalFree(handle)
                return False
            try:
                ctypes.memmove(locked, dib, len(dib))
            finally:
                kernel32.GlobalUnlock(handle)
            if not user32.SetClipboardData(CF_DIB, handle):
                kernel32.GlobalFree(handle)
                return False
            return True
        finally:
            user32.CloseClipboard()
    except Exception:
        return False


def open_path(path: Path) -> bool:
    try:
        system_name = platform.system()
        if system_name == "Windows":
            os.startfile(path)  # type: ignore[attr-defined]
            return True
        if system_name == "Darwin":
            subprocess.Popen(["open", str(path)])
            return True
        subprocess.Popen(["xdg-open", str(path)])
        return True
    except Exception:
        return False


def save_shared_item(filename: str, payload: bytes, target: str, open_after: bool) -> dict:
    folder = normalize_share_target(target)
    folder.mkdir(parents=True, exist_ok=True)
    safe_name = safe_share_filename(filename)
    file_path = folder / safe_name
    file_path.write_bytes(payload)
    opened = False
    if open_after:
        opened = open_path(file_path)
    item = {
        "id": f"share-{int(time.time() * 1000)}",
        "kind": "file",
        "name": safe_name,
        "target": str(folder),
        "path": str(file_path),
        "opened": opened,
        "createdAt": now_iso(),
    }
    push_share_recent(item)
    return item


def copy_shared_image_to_clipboard(payload: bytes) -> bool:
    return set_clipboard_image(payload)


def track_macro_usage(macro_id: str) -> None:
    usage = load_macro_usage()
    item = usage.get(macro_id, {"count": 0, "lastUsedAt": ""})
    item["count"] = int(item.get("count", 0)) + 1
    item["lastUsedAt"] = now_iso()
    usage[macro_id] = item
    save_macro_usage()


def get_all_apps_with_meta() -> dict[str, dict]:
    apps = {}
    for app_id, cmd in get_app_command_map().items():
        apps[app_id] = {"id": app_id, "name": app_id.replace("_", " ").title(), "command": cmd, "source": "built_in"}
    for app_id, item in load_custom_apps().items():
        apps[app_id] = {
            "id": app_id,
            "name": item.get("name", app_id),
            "command": item.get("command", []),
            "source": "custom",
        }
    return apps


def launch_app(app_id: str) -> bool:
    app_id = (app_id or "").strip().lower()
    if not app_id:
        return False
    command = get_all_apps_with_meta().get(app_id, {}).get("command")
    if not command:
        return False
    try:
        subprocess.Popen(command)
        return True
    except Exception:
        return False


def open_url(url: str) -> bool:
    if not isinstance(url, str) or not url.startswith(("http://", "https://")):
        return False


def get_foreground_app_windows() -> tuple[str, str] | None:
    if platform.system() != "Windows":
        return None
    try:
        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        hwnd = user32.GetForegroundWindow()
        if not hwnd:
            return None
        pid = ctypes.c_ulong(0)
        user32.GetWindowThreadProcessId(hwnd, ctypes.byref(pid))
        if not pid.value:
            return None
        PROCESS_QUERY_LIMITED_INFORMATION = 0x1000
        handle = kernel32.OpenProcess(PROCESS_QUERY_LIMITED_INFORMATION, False, pid.value)
        if not handle:
            return None
        try:
            buffer_len = ctypes.c_ulong(1024)
            buffer = ctypes.create_unicode_buffer(1024)
            ok = kernel32.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(buffer_len))
            if not ok:
                return None
            exe_path = buffer.value
            if not exe_path:
                return None
            name = Path(exe_path).stem.replace("_", " ").title()
            return name, exe_path
        finally:
            kernel32.CloseHandle(handle)
    except Exception:
        return None


def register_foreground_app() -> dict:
    info = get_foreground_app_windows()
    if not info:
        return {"ok": False, "reason": "unsupported_or_not_found"}
    name, exe_path = info
    app_id = slugify_app_id(name)
    existing = load_custom_apps()
    if app_id in existing and existing[app_id].get("command") == [exe_path]:
        return {"ok": True, "id": app_id, "name": existing[app_id].get("name", name), "already": True}
    # Ensure unique id when names collide.
    if app_id in existing and existing[app_id].get("command") != [exe_path]:
        app_id = f"{app_id}_{int(time.time())}"
    existing[app_id] = {"name": name, "command": [exe_path]}
    save_custom_apps()
    return {"ok": True, "id": app_id, "name": name, "already": False}
    try:
        import webbrowser
        webbrowser.open_new_tab(url)
        return True
    except Exception:
        return False


def perform_media_cmd(cmd: str) -> bool:
    media_map = {
        "play_pause": "playpause",
        "next": "nexttrack",
        "prev": "prevtrack",
        "vol_up": "volumeup",
        "vol_down": "volumedown",
        "mute": "volumemute",
    }
    if cmd in media_map:
        pyautogui.press(media_map[cmd], _pause=False)
        return True
    return cmd == "vol_set"


def perform_system_cmd(cmd: str) -> bool:
    if cmd == "screenshot":
        pyautogui.hotkey("ctrl", "shift", "s")
        return True
    if cmd == "lock":
        p = platform.system()
        if p == "Windows":
            pyautogui.hotkey("win", "l")
        elif p == "Darwin":
            pyautogui.hotkey("ctrl", "cmd", "q")
        else:
            pyautogui.hotkey("super", "l")
        return True
    if cmd == "show_desktop":
        p = platform.system()
        if p == "Windows":
            pyautogui.hotkey("win", "d")
        elif p == "Darwin":
            pyautogui.hotkey("fn", "f11")
        else:
            pyautogui.hotkey("super", "d")
        return True
    return False


def perform_window_cmd(cmd: str) -> bool:
    p = platform.system()
    if cmd == "maximize":
        if p == "Windows":
            pyautogui.hotkey("win", "up")
        elif p == "Darwin":
            pyautogui.hotkey("ctrl", "cmd", "f")
        return True
    if cmd == "snap_left":
        if p == "Windows":
            pyautogui.hotkey("win", "left")
        return True
    if cmd == "snap_right":
        if p == "Windows":
            pyautogui.hotkey("win", "right")
        return True
    if cmd == "close":
        if p == "Windows":
            pyautogui.hotkey("alt", "f4")
        elif p == "Darwin":
            pyautogui.hotkey("cmd", "w")
        else:
            pyautogui.hotkey("alt", "f4")
        return True
    return False


def get_macro_map() -> dict[str, dict]:
    return {
        "focus_work": {
            "name": "Focus Work",
            "steps": [
                {"type": "app", "id": "vscode"},
                {"type": "sleep", "ms": 350},
                {"type": "app", "id": "chrome"},
                {"type": "sleep", "ms": 350},
                {"type": "hotkey", "keys": ["win", "up"]},
            ],
        },
        "meeting_mode": {
            "name": "Meeting Mode",
            "steps": [
                {"type": "media", "cmd": "mute"},
                {"type": "app", "id": "chrome"},
                {"type": "sleep", "ms": 300},
                {"type": "open_url", "url": "https://calendar.google.com"},
            ],
        },
        "dev_tools": {
            "name": "Dev Tools",
            "steps": [
                {"type": "app", "id": "terminal"},
                {"type": "sleep", "ms": 280},
                {"type": "app", "id": "vscode"},
                {"type": "sleep", "ms": 280},
                {"type": "hotkey", "keys": ["ctrl", "shift", "esc"]},
            ],
        },
    }


def get_all_macros() -> dict[str, dict]:
    result: dict[str, dict] = {}
    for macro_id, data in get_macro_map().items():
        result[macro_id] = {
            "id": macro_id,
            "name": data.get("name", macro_id),
            "steps": data.get("steps", []),
            "source": "built_in",
        }
    for macro_id, data in load_custom_macros().items():
        result[macro_id] = {
            "id": macro_id,
            "name": data.get("name", macro_id),
            "steps": data.get("steps", []),
            "source": "custom",
        }
    return result


def validate_macro_steps(steps: object) -> bool:
    if not isinstance(steps, list) or not steps:
        return False
    allowed = {"sleep", "app", "open_url", "media", "window", "system", "hotkey", "key"}
    for step in steps:
        if not isinstance(step, dict):
            return False
        step_type = str(step.get("type", "")).strip().lower()
        if step_type not in allowed:
            return False
    return True


def generate_macro_from_prompt(prompt: str) -> dict:
    p = (prompt or "").strip().lower()
    if not p:
        return {
            "name": "Quick Focus",
            "steps": [
                {"type": "app", "id": "vscode"},
                {"type": "sleep", "ms": 250},
                {"type": "app", "id": "chrome"},
            ],
        }

    steps: list[dict] = []
    if "spotify" in p:
        steps.append({"type": "app", "id": "spotify"})
    if "code" in p or "vscode" in p or "dev" in p:
        steps.append({"type": "app", "id": "vscode"})
    if "browser" in p or "chrome" in p or "edge" in p or "web" in p:
        steps.append({"type": "app", "id": "chrome"})
    if "meeting" in p or "call" in p:
        steps.extend([
            {"type": "media", "cmd": "mute"},
            {"type": "open_url", "url": "https://calendar.google.com"},
        ])
    if "focus" in p:
        steps.append({"type": "system", "cmd": "show_desktop"})
    if "tabs" in p:
        steps.append({"type": "hotkey", "keys": ["ctrl", "t"]})
    if not steps:
        steps = [
            {"type": "app", "id": "terminal"},
            {"type": "sleep", "ms": 200},
            {"type": "app", "id": "vscode"},
        ]

    name = "AI Macro"
    if "meeting" in p:
        name = "AI Meeting Starter"
    elif "focus" in p:
        name = "AI Focus Starter"
    elif "music" in p or "spotify" in p:
        name = "AI Music Starter"
    return {"name": name, "steps": steps}


def execute_macro(macro_id: str) -> bool:
    macro = get_all_macros().get((macro_id or "").strip().lower())
    if not macro:
        return False
    try:
        for step in macro.get("steps", []):
            step_type = step.get("type")
            if step_type == "sleep":
                ms = max(0, min(int(step.get("ms", 0)), 2000))
                time.sleep(ms / 1000)
            elif step_type == "app":
                launch_app(str(step.get("id", "")))
            elif step_type == "open_url":
                open_url(str(step.get("url", "")))
            elif step_type == "media":
                perform_media_cmd(str(step.get("cmd", "")))
            elif step_type == "window":
                perform_window_cmd(str(step.get("cmd", "")))
            elif step_type == "system":
                perform_system_cmd(str(step.get("cmd", "")))
            elif step_type == "hotkey":
                keys = step.get("keys", [])
                if keys:
                    pyautogui.hotkey(*keys)
            elif step_type == "key":
                key = str(step.get("key", "")).strip()
                if key:
                    pyautogui.press(key, _pause=False)
        track_macro_usage((macro_id or "").strip().lower())
        return True
    except Exception:
        return False


def apply_acceleration(dx: float, dy: float, speed: float, accel: bool) -> tuple[float, float]:
    dist = math.sqrt(dx * dx + dy * dy)
    if dist == 0:
        return 0, 0
    multiplier = speed
    if accel:
        multiplier *= max(1.0, dist * 0.15)
    return dx * multiplier / dist * dist, dy * multiplier / dist * dist


@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    client_id = id(websocket)
    clients.add(websocket)
    client_state[client_id] = {
        "last_time": time.time(),
        "dragging": False,
        "authenticated": not is_auth_required(),
    }

    try:
        while True:
            raw = await websocket.receive_text()
            data = json.loads(raw)
            action = data.get("type")
            state = client_state[client_id]

            if action == "auth":
                pin = str(data.get("pin", ""))
                ok = (not is_auth_required()) or (pin == APP_PIN)
                state["authenticated"] = ok
                await websocket.send_text(json.dumps({"type": "auth_result", "ok": ok}))
                continue

            if is_auth_required() and not state.get("authenticated", False):
                if action == "ping":
                    await websocket.send_text(json.dumps({"type": "pong"}))
                else:
                    await websocket.send_text(json.dumps({"type": "auth_required"}))
                continue

            # --- TRACKPAD MOVE ---
            if action == "move":
                dx = data.get("dx", 0)
                dy = data.get("dy", 0)
                speed = data.get("speed", 5)
                accel = data.get("accel", True)
                fdx, fdy = apply_acceleration(dx, dy, speed, accel)
                pyautogui.moveRel(fdx, fdy, _pause=False)

            # --- SCROLL ---
            elif action == "scroll":
                dy = data.get("dy", 0)
                dx = data.get("dx", 0)
                speed = data.get("scrollSpeed", 4)
                pyautogui.scroll(int(-dy * speed * 0.5), _pause=False)
                if abs(dx) > abs(dy):
                    pyautogui.hscroll(int(dx * speed * 0.5), _pause=False)

            # --- CLICKS ---
            elif action == "left_click":
                pyautogui.click(_pause=False)
            elif action == "right_click":
                pyautogui.click(button="right", _pause=False)
            elif action == "middle_click":
                pyautogui.click(button="middle", _pause=False)
            elif action == "double_click":
                pyautogui.click(clicks=2, interval=0.08, _pause=False)

            # --- DRAG ---
            elif action == "drag_start":
                pyautogui.mouseDown()
                state["dragging"] = True
            elif action == "drag_end":
                pyautogui.mouseUp()
                state["dragging"] = False

            # --- KEYBOARD ---
            elif action == "key":
                key = data.get("key", "")
                if key:
                    try:
                        pyautogui.press(key, _pause=False)
                    except Exception:
                        pass

            elif action == "type":
                text = data.get("text", "")
                if text:
                    pyautogui.typewrite(text, interval=0.02)

            elif action == "hotkey":
                keys = data.get("keys", [])
                if keys:
                    pyautogui.hotkey(*keys)

            # --- MEDIA ---
            elif action == "media":
                cmd = data.get("cmd")
                perform_media_cmd(cmd)

            elif action == "open_url":
                url = data.get("url", "")
                open_url(url)

            elif action == "launch":
                target = data.get("target")
                if target == "spotify":
                    open_url("https://open.spotify.com")

            elif action == "app":
                app_id = data.get("id", "")
                ok = launch_app(app_id)
                await websocket.send_text(json.dumps({"type": "app_result", "id": app_id, "ok": ok}))

            elif action == "register_foreground_app":
                result = register_foreground_app()
                await websocket.send_text(json.dumps({"type": "register_app_result", **result}))

            elif action == "macro":
                macro_id = data.get("id", "")
                ok = execute_macro(macro_id)
                await websocket.send_text(json.dumps({"type": "macro_result", "id": macro_id, "ok": ok}))

            # --- SYSTEM ---
            elif action == "system":
                cmd = data.get("cmd")
                perform_system_cmd(cmd)

            # --- WINDOW MANAGEMENT ---
            elif action == "window":
                cmd = data.get("cmd")
                perform_window_cmd(cmd)

            # --- PING ---
            elif action == "ping":
                await websocket.send_text(json.dumps({"type": "pong"}))

    except WebSocketDisconnect:
        pass
    except OSError:
        # Network hiccups on mobile clients can produce transient socket errors.
        pass
    except Exception:
        # Keep server alive even when malformed client frames arrive.
        pass
    finally:
        clients.discard(websocket)
        client_state.pop(client_id, None)


@app.get("/qr")
def get_qr(request: Request):
    host = request.headers.get("host", "")
    scheme = request.headers.get("x-forwarded-proto", request.url.scheme or "http")
    if host and not host.startswith("localhost") and not host.startswith("127.0.0.1"):
        url = f"{scheme}://{host}"
    else:
        ip = get_local_ip()
        url = f"http://{ip}:8000"
    qr_b64 = generate_qr(url)
    return {"url": url, "qr": qr_b64}


@app.get("/desktop")
def get_desktop_info():
    ip = get_local_ip()
    ws_url = f"ws://{ip}:8000/ws"
    return {
        "id": get_desktop_id(),
        "name": get_machine_name(),
        "ip": ip,
        "ws": ws_url,
        "invite": build_desktop_invite(ws_url),
        "inviteStatus": invite_status_summary(),
    }


@app.get("/desktops/nearby")
def get_nearby_desktops():
    return {
        "current": {
            "id": get_desktop_id(),
            "name": get_machine_name(),
            "ip": get_local_ip(),
            "ws": f"ws://{get_local_ip()}:8000/ws",
            "invite": build_desktop_invite(f"ws://{get_local_ip()}:8000/ws"),
            "inviteStatus": invite_status_summary(),
        },
        "desktops": discover_nearby_desktops(),
    }


@app.post("/invite/send")
async def send_invite(request: Request):
    body = await request.json()
    if not isinstance(body, dict):
        return {"ok": False, "reason": "invalid_body"}

    message = str(body.get("message", "")).strip() or f"Invite to connect to {get_machine_name()}"
    sender = {
        "name": str(body.get("senderName", get_machine_name())),
        "ip": str(body.get("senderIp", get_local_ip())),
        "ws": str(body.get("senderWs", f"ws://{get_local_ip()}:8000/ws")),
    }
    invite = set_current_invite(message, sender)
    return {"ok": True, "invite": invite}


@app.post("/invite/respond")
async def respond_invite(request: Request):
    body = await request.json()
    if not isinstance(body, dict):
        return {"ok": False, "reason": "invalid_body"}
    decision = str(body.get("decision", "")).strip().lower()
    if decision not in {"accept", "reject"}:
        return {"ok": False, "reason": "invalid_decision"}
    invite = respond_current_invite(decision)
    return {"ok": bool(invite), "invite": invite}


@app.get("/invite/current")
def get_invite_current():
    return {"invite": get_current_invite(), "status": invite_status_summary()}


@app.post("/invite/proxy/send")
async def proxy_invite_send(request: Request):
    body = await request.json()
    if not isinstance(body, dict):
        return {"ok": False, "reason": "invalid_body"}

    target_ip = str(body.get("targetIp", "")).strip()
    if not target_ip:
        return {"ok": False, "reason": "target_ip_required"}

    payload = {
        "message": str(body.get("message", "")).strip(),
        "senderName": str(body.get("senderName", get_machine_name())),
        "senderIp": str(body.get("senderIp", get_local_ip())),
        "senderWs": str(body.get("senderWs", f"ws://{get_local_ip()}:8000/ws")),
    }
    try:
        req = UrlRequest(
            f"http://{target_ip}:8000/invite/send",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urlopen(req, timeout=1.0) as response:
            response_payload = json.loads(response.read().decode("utf-8"))
        return {"ok": True, "response": response_payload}
    except Exception as exc:
        return {"ok": False, "reason": str(exc)}


@app.get("/invite-center")
def invite_center():
        return HTMLResponse(
                """
<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Trackpad Invite</title>
<style>
        :root {
            --bg0: #06110f;
            --bg1: #0d2320;
            --card: rgba(9, 22, 20, 0.84);
            --border: rgba(109, 224, 201, 0.24);
            --text: #eafff8;
            --muted: #9acfc3;
            --accent: #59d8bf;
            --accent-strong: #2bc7a8;
            --danger: #ff4f6d;
        }
        * { box-sizing: border-box; }
        body {
            margin: 0;
            min-height: 100vh;
            display: grid;
            place-items: center;
            overflow: hidden;
            color: var(--text);
            font-family: 'Segoe UI', Arial, sans-serif;
            background:
                radial-gradient(circle at 20% 20%, rgba(89, 216, 191, 0.18), transparent 28%),
                radial-gradient(circle at 80% 30%, rgba(67, 192, 255, 0.14), transparent 26%),
                radial-gradient(circle at 50% 80%, rgba(43, 199, 168, 0.16), transparent 24%),
                linear-gradient(160deg, var(--bg0), var(--bg1) 60%, #091815);
        }
        body::before,
        body::after {
            content: '';
            position: absolute;
            inset: -15%;
            background: conic-gradient(from 180deg, transparent, rgba(89, 216, 191, 0.12), transparent 40%, rgba(67, 192, 255, 0.10), transparent 80%);
            filter: blur(30px);
            animation: drift 12s linear infinite;
            pointer-events: none;
        }
        body::after {
            animation-direction: reverse;
            opacity: 0.8;
        }
        @keyframes drift {
            0% { transform: rotate(0deg) scale(1); }
            50% { transform: rotate(180deg) scale(1.08); }
            100% { transform: rotate(360deg) scale(1); }
        }
        .card {
            position: relative;
            z-index: 1;
            width: min(620px, 92vw);
            background: linear-gradient(180deg, rgba(10, 25, 23, 0.92), rgba(7, 16, 14, 0.90));
            border: 1px solid var(--border);
            border-radius: 26px;
            padding: 24px;
            box-shadow: 0 24px 70px rgba(0,0,0,0.42);
            backdrop-filter: blur(18px);
            transform-origin: center;
            animation: popIn 600ms cubic-bezier(.2,.9,.2,1) both;
        }
        @keyframes popIn {
            from { opacity: 0; transform: translateY(18px) scale(0.96); }
            to { opacity: 1; transform: translateY(0) scale(1); }
        }
        .topline {
            display: flex;
            justify-content: space-between;
            align-items: center;
            gap: 12px;
            margin-bottom: 14px;
        }
        .brand {
            display: flex;
            align-items: center;
            gap: 12px;
        }
        .logo {
            width: 42px;
            height: 42px;
            border-radius: 14px;
            display: grid;
            place-items: center;
            background: linear-gradient(160deg, rgba(89, 216, 191, 0.22), rgba(67, 192, 255, 0.12));
            border: 1px solid rgba(109, 224, 201, 0.26);
            box-shadow: 0 0 0 6px rgba(89, 216, 191, 0.06);
            animation: pulse 2.8s ease-in-out infinite;
        }
        @keyframes pulse {
            0%, 100% { transform: scale(1); box-shadow: 0 0 0 6px rgba(89, 216, 191, 0.06); }
            50% { transform: scale(1.05); box-shadow: 0 0 0 12px rgba(89, 216, 191, 0.03); }
        }
        .title { font-size: 22px; font-weight: 800; }
        .subtitle { color: var(--muted); font-size: 13px; margin-top: 2px; }
        .badge {
            padding: 8px 12px;
            border-radius: 999px;
            border: 1px solid rgba(109, 224, 201, 0.24);
            background: rgba(255,255,255,0.03);
            color: var(--muted);
            font-size: 12px;
            white-space: nowrap;
        }
        .hero {
            display: grid;
            grid-template-columns: 1fr;
            gap: 14px;
            margin-top: 8px;
        }
        .message-box {
            padding: 18px;
            border-radius: 20px;
            border: 1px solid rgba(109, 224, 201, 0.22);
            background: linear-gradient(180deg, rgba(255,255,255,0.04), rgba(255,255,255,0.02));
        }
        .message-label {
            font-size: 11px;
            text-transform: uppercase;
            letter-spacing: 0.12em;
            color: var(--muted);
            margin-bottom: 8px;
        }
        .message {
            font-size: 16px;
            line-height: 1.6;
            color: var(--text);
            word-break: break-word;
        }
        .sender-grid {
            display: grid;
            grid-template-columns: repeat(3, 1fr);
            gap: 10px;
            margin-top: 4px;
        }
        .stat {
            border-radius: 16px;
            border: 1px solid rgba(109, 224, 201, 0.18);
            background: rgba(255,255,255,0.03);
            padding: 12px;
        }
        .stat .k { font-size: 11px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.08em; }
        .stat .v { margin-top: 4px; font-size: 13px; color: var(--text); overflow: hidden; text-overflow: ellipsis; }
        .actions { display: flex; gap: 12px; margin-top: 18px; }
        button {
            flex: 1;
            border: 0;
            border-radius: 16px;
            padding: 14px 16px;
            font-size: 15px;
            cursor: pointer;
            transition: transform 140ms ease, box-shadow 140ms ease, opacity 140ms ease;
            font-weight: 700;
        }
        button:hover { transform: translateY(-1px); }
        button:active { transform: translateY(1px) scale(0.99); }
        .accept {
            background: linear-gradient(160deg, #36dc84, #1fa861);
            color: #04130c;
            box-shadow: 0 10px 26px rgba(50, 214, 122, 0.20);
        }
        .reject {
            background: linear-gradient(160deg, #ff6a81, var(--danger));
            color: #fff;
            box-shadow: 0 10px 26px rgba(255, 79, 109, 0.16);
        }
        .foot {
            margin-top: 14px;
            color: var(--muted);
            font-size: 12px;
            display: flex;
            justify-content: space-between;
            gap: 8px;
            flex-wrap: wrap;
        }
        .pill { display: inline-block; margin-top: 12px; padding: 6px 10px; border: 1px solid rgba(109, 224, 201, 0.24); border-radius: 999px; font-size: 12px; color: var(--muted); }
        .pending-dot {
            width: 10px;
            height: 10px;
            border-radius: 50%;
            background: var(--accent);
            box-shadow: 0 0 0 0 rgba(89, 216, 191, 0.55);
            animation: ring 1.8s infinite;
        }
        @keyframes ring {
            0% { box-shadow: 0 0 0 0 rgba(89, 216, 191, 0.55); }
            70% { box-shadow: 0 0 0 12px rgba(89, 216, 191, 0); }
            100% { box-shadow: 0 0 0 0 rgba(89, 216, 191, 0); }
        }
        @media (max-width: 540px) {
            .sender-grid { grid-template-columns: 1fr; }
            .actions { flex-direction: column; }
            .topline { align-items: flex-start; flex-direction: column; }
        }
</style>
</head>
<body>
    <div class="card">
                <div class="topline">
                        <div class="brand">
                                <div class="logo">↗</div>
                                <div>
                                        <div class="title">Device invite</div>
                                        <div class="subtitle">Choose whether to allow this laptop to connect.</div>
                                </div>
                        </div>
                        <div class="badge"><span class="pending-dot" style="display:inline-block; vertical-align:middle; margin-right:8px;"></span><span id="state-badge">Waiting</span></div>
                </div>

                <div class="hero">
                        <div class="message-box">
                                <div class="message-label">Message</div>
                                <div id="message" class="message">This laptop is ready to receive a Wi-Fi invite.</div>
                                <div id="status" class="pill">No invite yet</div>
                        </div>

                        <div class="sender-grid">
                                <div class="stat"><div class="k">Sender</div><div id="sender-name" class="v">Unknown</div></div>
                                <div class="stat"><div class="k">Address</div><div id="sender-ip" class="v">Unknown</div></div>
                                <div class="stat"><div class="k">Time</div><div id="invite-time" class="v">Waiting</div></div>
                        </div>
                </div>

        <div class="actions">
            <button class="accept" onclick="respond('accept')">Accept</button>
            <button class="reject" onclick="respond('reject')">Reject</button>
        </div>
                <div class="foot">
                        <span>Visible consent prompt</span>
                        <span>Invite updates automatically</span>
                </div>
    </div>
<script>
function fmtTime(iso) {
        if (!iso) return 'Waiting';
        try {
                return new Date(iso).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
        } catch {
                return 'Waiting';
        }
}

async function refresh() {
    try {
        const res = await fetch('/invite/current');
        const data = await res.json();
        const invite = data.invite;
        const status = data.status || {};
        const statusEl = document.getElementById('status');
        const messageEl = document.getElementById('message');
                const badgeEl = document.getElementById('state-badge');
                const senderNameEl = document.getElementById('sender-name');
                const senderIpEl = document.getElementById('sender-ip');
                const inviteTimeEl = document.getElementById('invite-time');
        if (invite && invite.status === 'pending') {
                        statusEl.textContent = `Invite from ${invite.sender?.name || 'desktop'} (${invite.sender?.ip || 'unknown'}).`;
            messageEl.textContent = invite.message || 'No message';
                        badgeEl.textContent = 'Pending';
                        senderNameEl.textContent = invite.sender?.name || 'desktop';
                        senderIpEl.textContent = invite.sender?.ip || 'unknown';
                        inviteTimeEl.textContent = fmtTime(invite.createdAt);
        } else if (invite && invite.status === 'accept') {
            statusEl.textContent = 'Invite accepted.';
            messageEl.textContent = 'This laptop is ready.';
                        badgeEl.textContent = 'Accepted';
        } else if (invite && invite.status === 'reject') {
            statusEl.textContent = 'Invite rejected.';
            messageEl.textContent = 'You can wait for another invite.';
                        badgeEl.textContent = 'Rejected';
        } else {
            statusEl.textContent = 'This laptop is ready to receive a Wi-Fi invite.';
            messageEl.textContent = status.status === 'idle' ? 'No invite yet' : status.status;
                        badgeEl.textContent = 'Waiting';
        }
    } catch {
        document.getElementById('status').textContent = 'Could not check invite status.';
    }
}

async function respond(decision) {
    try {
        const res = await fetch('/invite/respond', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ decision })
        });
        const data = await res.json();
        if (data.ok) {
            document.getElementById('status').textContent = decision === 'accept' ? 'Invite accepted.' : 'Invite rejected.';
            document.getElementById('message').textContent = 'You can close this window now.';
        }
    } catch {
        document.getElementById('status').textContent = 'Could not respond to invite.';
    }
}

setInterval(refresh, 1000);
refresh();
</script>
</body>
</html>
                """
        )


@app.post("/desktop/invite/decode")
async def decode_invite(request: Request):
    body = await request.json()
    invite = str(body.get("invite", "")) if isinstance(body, dict) else ""
    data = decode_desktop_invite(invite)
    if not data:
        return {"ok": False, "reason": "invalid_invite"}
    return {"ok": True, "desktop": data}


@app.get("/config")
def get_config():
    return {
        "authRequired": is_auth_required(),
        "desktopName": get_machine_name(),
    }


@app.get("/apps")
def get_supported_apps():
    apps = []
    for app_id, meta in get_all_apps_with_meta().items():
        apps.append({
            "id": app_id,
            "name": meta.get("name", app_id),
            "source": meta.get("source", "built_in"),
        })
    apps.sort(key=lambda a: (a.get("source") != "built_in", a.get("name", "")))
    return {"apps": apps}


@app.get("/macros")
def get_supported_macros():
    usage = load_macro_usage()
    macros = []
    for macro_id, data in get_all_macros().items():
        u = usage.get(macro_id, {"count": 0, "lastUsedAt": ""})
        macros.append({
            "id": macro_id,
            "name": data.get("name", macro_id),
            "source": data.get("source", "built_in"),
            "steps": data.get("steps", []),
            "usageCount": int(u.get("count", 0)),
            "lastUsedAt": str(u.get("lastUsedAt", "")),
        })
    macros.sort(key=lambda m: (-m.get("usageCount", 0), m.get("name", "")))
    return {"macros": macros}


@app.get("/share/recent")
def get_share_recent():
    return {"items": load_share_recent()}


@app.post("/share/text")
async def share_text(request: Request):
    body = await request.json()
    text = str(body.get("text", "")) if isinstance(body, dict) else ""
    if not text.strip():
        return {"ok": False, "reason": "text_required"}
    ok = set_clipboard_text(text)
    item = {
        "id": f"text-{int(time.time() * 1000)}",
        "kind": "text",
        "name": (str(body.get("name", "")) if isinstance(body, dict) else "").strip() or "Clipboard text",
        "preview": text[:120],
        "createdAt": now_iso(),
        "copied": ok,
    }
    push_share_recent(item)
    return {"ok": ok, "item": item}


@app.post("/share/file")
async def share_file(request: Request):
    body = await request.json()
    if not isinstance(body, dict):
        return {"ok": False, "reason": "invalid_body"}

    filename = str(body.get("filename", "")).strip() or "shared-file"
    data_url = str(body.get("data", "")).strip()
    target = str(body.get("target", "shared")).strip()
    open_after = bool(body.get("openAfter", False))
    copy_to_clipboard = bool(body.get("copyToClipboard", False))

    try:
        payload, mime, extension = decode_data_url(data_url)
    except Exception:
        return {"ok": False, "reason": "invalid_payload"}

    safe_name = safe_share_filename(filename, extension)
    item = save_shared_item(safe_name, payload, target, open_after)
    item["mime"] = mime
    item["kind"] = "image" if mime.startswith("image/") else "file"
    if copy_to_clipboard and mime.startswith("image/"):
        item["clipboardCopied"] = copy_shared_image_to_clipboard(payload)
    else:
        item["clipboardCopied"] = False
    return {"ok": True, "item": item}


@app.post("/share/open")
async def open_shared_item(request: Request):
    body = await request.json()
    if not isinstance(body, dict):
        return {"ok": False, "reason": "invalid_body"}
    path_value = str(body.get("path", "")).strip()
    if not path_value:
        return {"ok": False, "reason": "path_required"}
    path = Path(path_value)
    if not path.exists():
        return {"ok": False, "reason": "not_found"}
    return {"ok": open_path(path)}


@app.post("/macros/generate")
async def generate_macro(request: Request):
    body = await request.json()
    prompt = str(body.get("prompt", "")) if isinstance(body, dict) else ""
    generated = generate_macro_from_prompt(prompt)
    return {"macro": generated}


@app.post("/macros/custom")
async def save_custom_macro(request: Request):
    body = await request.json()
    if not isinstance(body, dict):
        return {"ok": False, "reason": "invalid_body"}
    name = str(body.get("name", "")).strip()
    if not name:
        return {"ok": False, "reason": "name_required"}
    steps = body.get("steps", [])
    if not validate_macro_steps(steps):
        return {"ok": False, "reason": "invalid_steps"}
    macro_id = str(body.get("id", "")).strip().lower()
    if not macro_id:
        macro_id = slugify_macro_id(name)
    custom = load_custom_macros()
    custom[macro_id] = {"name": name, "steps": steps}
    save_custom_macros()
    return {"ok": True, "id": macro_id, "name": name}


@app.delete("/macros/custom/{macro_id}")
def delete_custom_macro(macro_id: str):
    macro_id = (macro_id or "").strip().lower()
    custom = load_custom_macros()
    if macro_id not in custom:
        return {"ok": False, "reason": "not_found"}
    del custom[macro_id]
    save_custom_macros()
    return {"ok": True}


@app.get("/relay/device/{device_id}")
async def relay_device_info(device_id: str):
    """
    Query device info from cloud relay.
    Used by phone to find friend's device after they click share link.
    """
    relay_url = os.getenv("TRACKPAD_RELAY_URL", "https://trackpad-relay.vercel.app").strip()
    try:
        req = UrlRequest(
            f"{relay_url}/api/device?id={device_id}&type=device",
            headers={"Accept": "application/json"},
            method="GET",
        )
        with urlopen(req, timeout=3.0) as response:
            data = json.loads(response.read().decode("utf-8"))
        return data
    except Exception as exc:
        return {"success": False, "error": str(exc)}


@app.get("/relay/share/{share_link_id}")
async def relay_share_link_info(share_link_id: str):
    """
    Query share link info from cloud relay.
    Alternative way to get device info using share link ID.
    """
    relay_url = os.getenv("TRACKPAD_RELAY_URL", "https://trackpad-relay.vercel.app").strip()
    try:
        req = UrlRequest(
            f"{relay_url}/api/device?id={share_link_id}&type=sharelink",
            headers={"Accept": "application/json"},
            method="GET",
        )
        with urlopen(req, timeout=3.0) as response:
            data = json.loads(response.read().decode("utf-8"))
        return data
    except Exception as exc:
        return {"success": False, "error": str(exc)}


@app.get("/favicon.ico")
def favicon():
    return Response(status_code=204)


@app.get("/")
def serve_ui():
    return HTMLResponse(Path("trackpad.html").read_text())


if __name__ == "__main__":
    import uvicorn
    import threading

    ip = get_local_ip()
    print(f"\n  PhoneDesk running!")
    print(f"  Local:   http://localhost:8000")
    print(f"  Network: http://{ip}:8000  ← open this on your phone\n")
    def _open_invite_center():
        try:
            webbrowser.open_new_tab("http://127.0.0.1:8000/invite-center")
        except Exception:
            pass

    threading.Timer(1.5, _open_invite_center).start()
    uvicorn.run(app, host="0.0.0.0", port=8000)
