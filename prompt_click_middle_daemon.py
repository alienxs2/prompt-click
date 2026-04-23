#!/usr/bin/env python3
import glob
import json
import logging
import os
import pwd
import select
import shutil
import signal
import subprocess
import sys
import threading
import time
import uuid
from dataclasses import dataclass

from evdev import InputDevice, UInput, ecodes, list_devices

PROMPT_BINARY_NAME = "prompt_click"
SESSION_RETRY_SECONDS = 2.0
DEVICE_RETRY_SECONDS = 2.0
LAUNCH_COOLDOWN_SECONDS = 0.5
PASTE_DELAY_SECONDS = 0.15
ENV_KEYS = (
    "DBUS_SESSION_BUS_ADDRESS",
    "DESKTOP_SESSION",
    "DISPLAY",
    "WAYLAND_DISPLAY",
    "XAUTHORITY",
    "XDG_CURRENT_DESKTOP",
    "XDG_RUNTIME_DIR",
    "XDG_SESSION_TYPE",
)

_running = True
_last_launch = 0.0
_keyboard = None
_keyboard_lock = threading.Lock()
_prompt_thread = None
_prompt_thread_lock = threading.Lock()


@dataclass
class GraphicalSession:
    session_id: str
    uid: int
    gid: int
    user: str
    home: str
    session_type: str
    leader: int
    env: dict

    @property
    def runtime_dir(self):
        return self.env["XDG_RUNTIME_DIR"]

    @property
    def prompt_path(self):
        return os.path.join(self.home, ".local", "bin", PROMPT_BINARY_NAME)

    @property
    def trigger_path(self):
        return os.path.join(self.runtime_dir, "prompt_click_autopaste.trigger")

    @property
    def log_path(self):
        return os.path.join(self.runtime_dir, "prompt_click_middle_launch.log")


def _stop(_signum, _frame):
    global _running
    _running = False


def _run_command(args):
    return subprocess.run(
        args,
        capture_output=True,
        text=True,
        check=False,
    )


def _read_proc_env(pid):
    try:
        with open(f"/proc/{pid}/environ", "rb") as f:
            raw = f.read()
    except OSError:
        return {}

    env = {}
    for entry in raw.split(b"\0"):
        if not entry or b"=" not in entry:
            continue
        key, value = entry.split(b"=", 1)
        key_str = key.decode("utf-8", "ignore")
        if key_str in ENV_KEYS:
            env[key_str] = value.decode("utf-8", "ignore")
    return env


def _list_session_ids():
    result = _run_command(["loginctl", "list-sessions", "--no-legend"])
    if result.returncode != 0:
        logging.error("Failed to list sessions: %s", result.stderr.strip())
        return []

    session_ids = []
    for line in result.stdout.splitlines():
        parts = line.split()
        if parts and parts[0].isdigit():
            session_ids.append(parts[0])
    return session_ids


def _show_session(session_id):
    result = _run_command(["loginctl", "show-session", session_id, "-a"])
    if result.returncode != 0:
        return {}

    data = {}
    for line in result.stdout.splitlines():
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        data[key] = value
    return data


def _pgrep_user(user, pattern):
    result = _run_command(["pgrep", "-u", user, "-f", pattern])
    if result.returncode != 0:
        return []
    return [int(pid) for pid in result.stdout.split() if pid.isdigit()]


def _merge_session_env(session_type, user, leader, fallback_env):
    env = dict(fallback_env)
    candidate_pids = []
    if leader > 0:
        candidate_pids.append(leader)

    patterns = [
        r"/usr/bin/gnome-shell",
        r"gnome-session-binary",
        r"gdm-(wayland|x)-session",
    ]
    if session_type == "x11":
        patterns.append(r"/usr/lib/xorg/Xorg")

    for pattern in patterns:
        for pid in _pgrep_user(user, pattern):
            if pid not in candidate_pids:
                candidate_pids.append(pid)

    for pid in candidate_pids:
        for key, value in _read_proc_env(pid).items():
            if value and key not in env:
                env[key] = value

    return env


def _resolve_display(session_type, runtime_dir, env):
    if session_type == "x11":
        if env.get("DISPLAY"):
            return env["DISPLAY"]
        for socket_path in sorted(glob.glob("/tmp/.X11-unix/X*")):
            socket_name = os.path.basename(socket_path)
            return f":{socket_name[1:]}"
        return None

    if env.get("WAYLAND_DISPLAY"):
        return env["WAYLAND_DISPLAY"]
    for wayland_socket in sorted(glob.glob(os.path.join(runtime_dir, "wayland-*"))):
        return os.path.basename(wayland_socket)
    return None


def _resolve_xauthority(env, runtime_dir, home):
    for candidate in (
        env.get("XAUTHORITY"),
        os.path.join(runtime_dir, "gdm", "Xauthority"),
        os.path.join(home, ".Xauthority"),
    ):
        if candidate and os.path.exists(candidate):
            return candidate
    return None


def _build_graphical_session(session_id, props):
    if props.get("Active") != "yes":
        return None
    if props.get("Remote") == "yes":
        return None
    if props.get("State") != "active":
        return None
    if props.get("Class") != "user":
        return None

    session_type = props.get("Type", "")
    if session_type not in ("x11", "wayland"):
        return None

    uid_value = props.get("User")
    if not uid_value or not uid_value.isdigit():
        return None

    uid = int(uid_value)
    try:
        pw = pwd.getpwuid(uid)
    except KeyError:
        return None

    runtime_dir = f"/run/user/{uid}"
    env = {
        "HOME": pw.pw_dir,
        "LOGNAME": pw.pw_name,
        "USER": pw.pw_name,
        "XDG_RUNTIME_DIR": runtime_dir,
        "DBUS_SESSION_BUS_ADDRESS": f"unix:path={runtime_dir}/bus",
        "XDG_SESSION_TYPE": session_type,
    }

    leader = int(props.get("Leader") or 0)
    env = _merge_session_env(session_type, pw.pw_name, leader, env)

    if session_type == "x11":
        display = _resolve_display(session_type, runtime_dir, env)
        if display:
            env["DISPLAY"] = display
        xauthority = _resolve_xauthority(env, runtime_dir, pw.pw_dir)
        if xauthority:
            env["XAUTHORITY"] = xauthority
    else:
        wayland_display = _resolve_display(session_type, runtime_dir, env)
        if wayland_display:
            env["WAYLAND_DISPLAY"] = wayland_display

    return GraphicalSession(
        session_id=session_id,
        uid=uid,
        gid=pw.pw_gid,
        user=pw.pw_name,
        home=pw.pw_dir,
        session_type=session_type,
        leader=leader,
        env=env,
    )


def _active_graphical_session():
    for session_id in _list_session_ids():
        session = _build_graphical_session(session_id, _show_session(session_id))
        if session is not None:
            return session
    return None


def _session_ready(session):
    runtime_dir = session.runtime_dir
    if not os.path.isdir(runtime_dir):
        return False

    if not os.path.exists(os.path.join(runtime_dir, "bus")):
        return False

    if session.session_type == "x11":
        return bool(session.env.get("DISPLAY"))

    wayland_display = session.env.get("WAYLAND_DISPLAY")
    if not wayland_display:
        return False
    return os.path.exists(os.path.join(runtime_dir, wayland_display))


def _prompt_click_running(session):
    result = subprocess.run(
        ["pgrep", "-u", session.user, "-f", session.prompt_path],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=False,
    )
    return result.returncode == 0


def _command_exists(command):
    return shutil.which(command) is not None


def _session_env_items(session, extra_env=None):
    env = dict(session.env)
    if extra_env:
        env.update(extra_env)
    return [f"{key}={value}" for key, value in sorted(env.items()) if value]


def _build_prompt_cmd(session, token):
    return [
        "/usr/sbin/runuser",
        "-u",
        session.user,
        "--",
        "env",
        *_session_env_items(
            session,
            {
                "PROMPT_CLICK_AUTOPASTE_TOKEN": token,
                "PROMPT_CLICK_AUTOPASTE_TRIGGER": session.trigger_path,
            },
        ),
        session.prompt_path,
        "--paste-mode",
        "auto",
    ]


def _emit_paste():
    if _keyboard is None:
        logging.error("Virtual keyboard is not initialized")
        return

    with _keyboard_lock:
        _keyboard.write(ecodes.EV_KEY, ecodes.KEY_LEFTSHIFT, 1)
        _keyboard.write(ecodes.EV_KEY, ecodes.KEY_INSERT, 1)
        _keyboard.syn()
        _keyboard.write(ecodes.EV_KEY, ecodes.KEY_INSERT, 0)
        _keyboard.write(ecodes.EV_KEY, ecodes.KEY_LEFTSHIFT, 0)
        _keyboard.syn()

    logging.info("Injected Shift+Insert into active window")


def _copy_with_xclip(session, text_bytes):
    base_cmd = [
        "/usr/sbin/runuser",
        "-u",
        session.user,
        "--",
        "env",
        *_session_env_items(session),
    ]
    for selection in ("clipboard", "primary"):
        proc = subprocess.Popen(
            base_cmd + ["xclip", "-selection", selection],
            stdin=subprocess.PIPE,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        proc.communicate(text_bytes)


def _copy_with_wl_copy(session, text_bytes):
    base_cmd = [
        "/usr/sbin/runuser",
        "-u",
        session.user,
        "--",
        "env",
        *_session_env_items(session),
    ]
    subprocess.run(
        base_cmd + ["wl-copy", "--type", "text/plain;charset=utf-8"],
        input=text_bytes,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
    )
    subprocess.run(
        base_cmd + ["wl-copy", "--primary", "--type", "text/plain;charset=utf-8"],
        input=text_bytes,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
        check=True,
    )


def _set_clipboard_text(session, text):
    text_bytes = text.encode("utf-8")
    if session.session_type == "wayland" and _command_exists("wl-copy"):
        _copy_with_wl_copy(session, text_bytes)
        logging.info("Updated clipboard with selected Prompt Click text via wl-copy")
        return

    if session.env.get("DISPLAY") and _command_exists("xclip"):
        _copy_with_xclip(session, text_bytes)
        logging.info("Updated clipboard with selected Prompt Click text via xclip")
        return

    logging.warning("No clipboard helper available; keeping Prompt Click clipboard state")


def _run_prompt_click_session(session):
    global _prompt_thread

    token = uuid.uuid4().hex
    try:
        with open(session.trigger_path, "w", encoding="utf-8") as f:
            f.write("")
        os.chown(session.trigger_path, session.uid, session.gid)
        os.chmod(session.trigger_path, 0o600)
    except OSError:
        logging.exception("Failed to reset trigger file %s", session.trigger_path)

    try:
        with open(session.log_path, "ab") as log_file:
            subprocess.run(
                _build_prompt_cmd(session, token),
                stdout=log_file,
                stderr=subprocess.STDOUT,
                check=False,
            )
    except OSError:
        logging.exception("Failed to launch Prompt Click")

    payload = None
    try:
        with open(session.trigger_path, "r", encoding="utf-8") as f:
            payload = json.load(f)
    except (OSError, json.JSONDecodeError):
        payload = None

    if payload and payload.get("token") == token and isinstance(payload.get("text"), str):
        _set_clipboard_text(session, payload["text"])
        time.sleep(PASTE_DELAY_SECONDS)
        _emit_paste()
    else:
        logging.info("Prompt Click closed without auto-paste request")

    try:
        os.remove(session.trigger_path)
    except FileNotFoundError:
        pass
    except OSError:
        logging.exception("Failed to remove trigger file %s", session.trigger_path)

    with _prompt_thread_lock:
        _prompt_thread = None


def _launch_prompt_click():
    global _last_launch
    global _prompt_thread

    now = time.monotonic()
    if now - _last_launch < LAUNCH_COOLDOWN_SECONDS:
        return

    session = _active_graphical_session()
    if session is None:
        logging.info("Skipping middle click: no active local X11/Wayland session found")
        return

    if not _session_ready(session):
        logging.info(
            "Skipping middle click: %s session for %s is not ready",
            session.session_type,
            session.user,
        )
        return

    if not os.path.exists(session.prompt_path):
        logging.error("Skipping middle click: Prompt Click binary not found at %s", session.prompt_path)
        return

    if _prompt_click_running(session):
        logging.info("Skipping middle click: Prompt Click is already running")
        return

    with _prompt_thread_lock:
        if _prompt_thread and _prompt_thread.is_alive():
            logging.info("Skipping middle click: Prompt Click launcher is already active")
            return

        _prompt_thread = threading.Thread(
            target=_run_prompt_click_session,
            args=(session,),
            name="prompt-click-launcher",
            daemon=True,
        )
        _prompt_thread.start()

    _last_launch = now
    logging.info(
        "Launched Prompt Click for %s session=%s user=%s",
        session.session_type,
        session.session_id,
        session.user,
    )


def _device_supports_middle_click(device_path):
    try:
        device = InputDevice(device_path)
        capabilities = device.capabilities()
        device.close()
    except OSError:
        return False

    keys = capabilities.get(ecodes.EV_KEY, [])
    if not keys:
        return False
    return ecodes.BTN_MIDDLE in keys


def _find_mouse_device():
    preferred_patterns = (
        "/dev/input/by-id/*-event-mouse",
        "/dev/input/by-path/*-event-mouse",
    )
    seen = set()

    for pattern in preferred_patterns:
        for device_path in sorted(glob.glob(pattern)):
            real_path = os.path.realpath(device_path)
            if real_path in seen:
                continue
            seen.add(real_path)
            if _device_supports_middle_click(device_path):
                return device_path

    for device_path in sorted(list_devices()):
        real_path = os.path.realpath(device_path)
        if real_path in seen:
            continue
        seen.add(real_path)
        if _device_supports_middle_click(device_path):
            return device_path

    return None


def _forward_loop(device_path):
    global _keyboard

    logging.info("Opening device %s", device_path)
    source = InputDevice(device_path)
    virtual = UInput.from_device(
        source,
        name="Prompt Click Virtual Mouse",
        vendor=source.info.vendor,
        product=source.info.product,
        version=source.info.version,
        bustype=source.info.bustype,
    )
    _keyboard = UInput(
        {
            ecodes.EV_KEY: [ecodes.KEY_LEFTSHIFT, ecodes.KEY_INSERT],
        },
        name="Prompt Click Virtual Keyboard",
    )
    middle_pressed = False

    try:
        source.grab()
        logging.info("Grabbed %s", device_path)

        while _running:
            readable, _, _ = select.select([source.fd], [], [], 0.25)
            if not readable:
                continue

            for event in source.read():
                if event.type == ecodes.EV_KEY and event.code == ecodes.BTN_MIDDLE:
                    if event.value == 1:
                        middle_pressed = True
                    elif event.value == 0:
                        if middle_pressed:
                            _launch_prompt_click()
                        middle_pressed = False
                    continue

                if event.type == ecodes.EV_SYN:
                    virtual.syn()
                else:
                    virtual.write_event(event)
    finally:
        try:
            source.ungrab()
        except OSError:
            pass
        source.close()
        virtual.close()
        if _keyboard is not None:
            _keyboard.close()
            _keyboard = None
        logging.info("Released %s", device_path)


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(message)s",
    )
    signal.signal(signal.SIGINT, _stop)
    signal.signal(signal.SIGTERM, _stop)

    while _running:
        device_path = _find_mouse_device()
        if not device_path:
            logging.warning("No middle-click mouse device found; retrying")
            time.sleep(DEVICE_RETRY_SECONDS)
            continue

        if _active_graphical_session() is None:
            logging.info("No active local X11/Wayland session found; waiting")
            time.sleep(SESSION_RETRY_SECONDS)
            continue

        try:
            _forward_loop(device_path)
        except KeyboardInterrupt:
            break
        except Exception as error:
            logging.exception("Mouse forwarder crashed: %s", error)
            time.sleep(DEVICE_RETRY_SECONDS)

    logging.info("Prompt Click middle-button daemon stopped")
    return 0


if __name__ == "__main__":
    sys.exit(main())
