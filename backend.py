"""
MacroDeck Backend v15
=====================
- Fenêtre console INVISIBLE (pas de clignotement)
- Connexion ESP32 via USB Série + BLE
- Détection application active (Windows)
- Moteur d'actions massif : clavier, souris, médias, scripts, apps, OBS, Zoom, Teams, Discord,
  Git, Docker, SSH, Home Assistant, webhooks, API REST, multi-actions, timers, etc.
- Métriques PC temps réel (CPU, RAM, GPU, SSD, réseau, températures, processus)
- Envoi métriques LED → ESP32
- Serveur WebSocket local → GUI

Dépendances :
    pip install pyserial bleak psutil gputil pynput pywin32
                keyboard mouse websockets asyncio aiofiles
                pywin32 comtypes pycaw wmi

Lancer : pythonw backend.py   (ou pyinstaller avec --noconsole)
"""

# ─── CACHER LA FENÊTRE CONSOLE IMMÉDIATEMENT ───────────────────────────────────
import sys, os, ctypes

if sys.platform == "win32":
    try:
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)   # SW_HIDE
    except Exception:
        pass

# ─── IMPORTS ───────────────────────────────────────────────────────────────────
import asyncio, json, time, subprocess, threading, logging, shutil, glob
import webbrowser, socket, re, datetime
from pathlib import Path
from typing import Optional

import serial
import serial.tools.list_ports
import psutil
import keyboard
import mouse
import websockets
from websockets.server import WebSocketServerProtocol

try:
    import GPUtil
    GPU_AVAILABLE = True
except ImportError:
    GPU_AVAILABLE = False

try:
    import win32gui, win32process
    WIN32_AVAILABLE = True
except ImportError:
    WIN32_AVAILABLE = False

try:
    from bleak import BleakClient, BleakScanner
    BLE_AVAILABLE = True
except ImportError:
    BLE_AVAILABLE = False

try:
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    from comtypes import CLSCTX_ALL
    PYCAW_AVAILABLE = True
except ImportError:
    PYCAW_AVAILABLE = False

try:
    import wmi as wmilib
    WMI_AVAILABLE = True
except ImportError:
    WMI_AVAILABLE = False

# ─── CONFIG ────────────────────────────────────────────────────────────────────
CONFIG_PATH   = Path(os.path.expanduser("~")) / ".macrodeck" / "config.json"
CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)
LOG_LEVEL     = logging.WARNING   # pas de spam de logs en prod
WS_PORT       = 8765
SERIAL_BAUD   = 115200
METRICS_INTERVAL = 1.0

BLE_SERVICE_UUID = "12345678-1234-1234-1234-123456789abc"
BLE_TX_UUID      = "12345678-1234-1234-1234-123456789abd"
BLE_RX_UUID      = "12345678-1234-1234-1234-123456789abe"

logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("MacroDeck")

# ─── CONFIG MANAGER ────────────────────────────────────────────────────────────
DEFAULT_CONFIG = {
    "profiles": {
        "default": {
            "name": "Global",
            "app_trigger": None,
            "buttons": {str(i): {"press": [], "long_press": [], "double_click": []} for i in range(8)},
            "pots": {
                "0": {"action": "volume_system"},
                "1": {"action": "volume_app", "app": ""},
                "2": {"action": "brightness"},
                "3": {"action": "custom", "script": ""}
            }
        }
    },
    "active_profile": "default",
    "led_strips": {
        str(i): {"metric": ["cpu", "ram", "gpu_usage", "ssd_usage"][i], "thresholds": [50, 80]}
        for i in range(4)
    },
    "serial_port": "AUTO",
    "ble_device": "MacroDeck"
}

class ConfigManager:
    def __init__(self):
        self.data = DEFAULT_CONFIG.copy()
        self.load()

    def load(self):
        if CONFIG_PATH.exists():
            try:
                with open(CONFIG_PATH, "r", encoding="utf-8") as f:
                    self.data = json.load(f)
            except Exception as e:
                log.error(f"Erreur config: {e}")

    def save(self):
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    def active_profile(self) -> dict:
        name = self.data.get("active_profile", "default")
        return self.data["profiles"].get(name, self.data["profiles"]["default"])

# ─── VOLUME (pycaw) ────────────────────────────────────────────────────────────
def _vol_iface():
    if not PYCAW_AVAILABLE:
        return None
    try:
        devices = AudioUtilities.GetSpeakers()
        iface = devices.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        return iface.QueryInterface(IAudioEndpointVolume)
    except:
        return None

def get_volume() -> int:
    try:
        v = _vol_iface()
        return int(v.GetMasterVolumeLevelScalar() * 100) if v else 0
    except:
        return 0

def set_volume(level: int):
    try:
        v = _vol_iface()
        if v:
            v.SetMasterVolumeLevelScalar(max(0, min(100, level)) / 100.0, None)
    except Exception as e:
        log.error(f"Volume: {e}")

def get_mute() -> bool:
    try:
        v = _vol_iface()
        return bool(v.GetMute()) if v else False
    except:
        return False

def set_mute(state: bool):
    try:
        v = _vol_iface()
        if v:
            v.SetMute(state, None)
    except:
        pass

# ─── LISTE APPLICATIONS INSTALLÉES ────────────────────────────────────────────
def get_installed_apps() -> list:
    """Retourne toutes les applications installées (raccourcis + exe)."""
    apps = []
    seen = set()

    def add(name, path, kind="lnk"):
        key = name.lower().strip()
        if key and key not in seen and name:
            seen.add(key)
            apps.append({"name": name, "path": path, "type": kind})

    # Menu Démarrer
    for base in [
        os.path.join(os.environ.get("APPDATA", ""), "Microsoft", "Windows", "Start Menu", "Programs"),
        r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs",
    ]:
        if os.path.isdir(base):
            for root, _, files in os.walk(base):
                for f in files:
                    if f.endswith(".lnk"):
                        add(f[:-4], os.path.join(root, f), "lnk")

    # Registre
    try:
        import winreg
        for hive in [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]:
            for path in [
                r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
                r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall",
            ]:
                try:
                    key = winreg.OpenKey(hive, path)
                    i = 0
                    while True:
                        try:
                            sub = winreg.OpenKey(key, winreg.EnumKey(key, i))
                            try:
                                name = winreg.QueryValueEx(sub, "DisplayName")[0]
                                exe  = winreg.QueryValueEx(sub, "DisplayIcon")[0].split(",")[0].strip('"')
                                if exe.endswith(".exe") and os.path.isfile(exe):
                                    add(name, exe, "exe")
                            except: pass
                            i += 1
                        except OSError: break
                except: pass
    except: pass

    # Dossiers Programs
    for base in [
        r"C:\Program Files", r"C:\Program Files (x86)",
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Programs"),
        os.path.join(os.environ.get("LOCALAPPDATA", ""), "Microsoft", "WindowsApps"),
    ]:
        if os.path.isdir(base):
            for d in os.listdir(base):
                full = os.path.join(base, d)
                if os.path.isdir(full):
                    for f in os.listdir(full):
                        if f.endswith(".exe"):
                            add(f[:-4], os.path.join(full, f), "exe")

    apps.sort(key=lambda x: x["name"].lower())
    return apps

# ─── MOTEUR D'ACTIONS ─────────────────────────────────────────────────────────
class ActionEngine:
    """Exécute toutes les actions : PC, clavier, audio, OBS, streaming, dev, domotique..."""

    # ── Dispatch principal ──────────────────────────────────────────────────────
    def run_actions(self, actions: list):
        for a in actions:
            self._run_one(a)

    def _run_one(self, action: dict):
        t = action.get("type", "")
        try:
            # ── 1. CONTRÔLE PC ────────────────────────────────────────────────
            if t == "launch" or t == "open_app":
                path = action.get("path", "")
                if path:
                    subprocess.Popen(path, shell=True,
                        creationflags=subprocess.CREATE_NO_WINDOW)

            elif t == "close_app":
                name = action.get("name", "").lower()
                for p in psutil.process_iter(["name"]):
                    if name in (p.info.get("name") or "").lower():
                        p.terminate()

            elif t == "open_folder":
                os.startfile(action.get("path", "."))

            elif t == "open_file":
                os.startfile(action.get("path", ""))

            elif t == "open_url":
                webbrowser.open(action.get("url", ""))

            elif t == "lock_session" or t == "win_lock":
                keyboard.send("win+l")

            elif t == "shutdown":
                os.system("shutdown /s /t 0")

            elif t == "restart":
                os.system("shutdown /r /t 0")

            elif t == "sleep":
                os.system("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")

            elif t == "logoff":
                os.system("shutdown /l")

            elif t == "run_command":
                subprocess.Popen(action.get("command", ""), shell=True,
                    creationflags=subprocess.CREATE_NO_WINDOW)

            elif t == "script_python":
                exec(action.get("code", ""), {"action": action})

            elif t == "script_powershell":
                cmd = action.get("code", action.get("path", ""))
                if action.get("path"):
                    subprocess.Popen(
                        ["powershell", "-ExecutionPolicy", "Bypass", "-File", action["path"]],
                        creationflags=subprocess.CREATE_NO_WINDOW)
                else:
                    subprocess.Popen(
                        ["powershell", "-Command", cmd],
                        creationflags=subprocess.CREATE_NO_WINDOW)

            elif t == "script_batch":
                path = action.get("path", "")
                if not path:
                    tmp = os.path.join(os.environ.get("TEMP", "."), "macrodeck_tmp.bat")
                    with open(tmp, "w") as f:
                        f.write(action.get("code", ""))
                    path = tmp
                subprocess.Popen(path, shell=True,
                    creationflags=subprocess.CREATE_NO_WINDOW)

            elif t == "script_ahk":
                subprocess.Popen(["AutoHotkey.exe", action.get("path", "")],
                    creationflags=subprocess.CREATE_NO_WINDOW)

            elif t == "clean_temp":
                temp = os.environ.get("TEMP", "")
                for f in glob.glob(os.path.join(temp, "*")):
                    try:
                        if os.path.isfile(f): os.remove(f)
                        elif os.path.isdir(f): shutil.rmtree(f, ignore_errors=True)
                    except: pass

            elif t == "mount_drive":
                letter = action.get("letter", "Z")
                path   = action.get("path", "")
                os.system(f"net use {letter}: \"{path}\"")

            elif t == "unmount_drive":
                letter = action.get("letter", "Z")
                os.system(f"net use {letter}: /delete /y")

            elif t == "win_minimize_all":
                keyboard.send("win+d")

            # ── 2. RACCOURCIS CLAVIER ─────────────────────────────────────────
            elif t == "hotkey":
                keyboard.send(action.get("keys", ""))

            elif t == "type_text":
                keyboard.write(action.get("text", ""), delay=action.get("delay", 0.03))

            elif t == "key_sequence":
                for seq in action.get("sequence", []):
                    keyboard.send(seq)
                    time.sleep(action.get("interval", 0.05))

            elif t == "key_repeat":
                k = action.get("key", "")
                n = action.get("count", 1)
                for _ in range(n):
                    keyboard.send(k)
                    time.sleep(action.get("interval", 0.05))

            elif t == "mouse_click":
                btn = action.get("button", "left")
                x, y = action.get("x"), action.get("y")
                if x is not None and y is not None:
                    mouse.move(x, y, absolute=True)
                mouse.click(btn)

            elif t == "mouse_double_click":
                mouse.double_click(action.get("button", "left"))

            elif t == "mouse_move":
                mouse.move(action.get("x", 0), action.get("y", 0),
                           absolute=action.get("absolute", True))

            elif t == "mouse_scroll":
                mouse.wheel(action.get("delta", 1))

            elif t == "screenshot":
                keyboard.send("win+shift+s")

            # ── 3. MÉDIAS / AUDIO ─────────────────────────────────────────────
            elif t == "media_play_pause":
                keyboard.send("play/pause media")

            elif t == "media_next":
                keyboard.send("next track")

            elif t == "media_prev":
                keyboard.send("previous track")

            elif t == "media_stop":
                keyboard.send("stop media")

            elif t == "volume_up":
                step = action.get("step", 5)
                set_volume(get_volume() + step)

            elif t == "volume_down":
                step = action.get("step", 5)
                set_volume(get_volume() - step)

            elif t == "volume_set":
                set_volume(int(action.get("value", 50)))

            elif t == "volume_mute" or t == "mute_toggle":
                set_mute(not get_mute())

            elif t == "volume_app":
                self._set_app_volume(action.get("app", ""), action.get("value", 50))

            elif t == "brightness":
                self._set_brightness(action.get("value", 50))

            elif t == "soundboard":
                path = action.get("path", "")
                if path:
                    subprocess.Popen(f"start \"\" \"{path}\"", shell=True)

            # ── 4. SPOTIFY / DEEZER / VLC ────────────────────────────────────
            elif t == "spotify_play_pause":
                keyboard.send("play/pause media")

            elif t == "spotify_next":
                keyboard.send("next track")

            elif t == "spotify_prev":
                keyboard.send("previous track")

            elif t == "vlc_play_pause":
                keyboard.send("space")

            elif t == "vlc_fullscreen":
                keyboard.send("f")

            # ── 5. OBS ───────────────────────────────────────────────────────
            elif t == "obs_scene":
                self._obs_cmd("SetCurrentScene", {"scene-name": action.get("scene", "")})

            elif t == "obs_stream_start":
                self._obs_cmd("StartStreaming", {})

            elif t == "obs_stream_stop":
                self._obs_cmd("StopStreaming", {})

            elif t == "obs_record_start":
                self._obs_cmd("StartRecording", {})

            elif t == "obs_record_stop":
                self._obs_cmd("StopRecording", {})

            elif t == "obs_mute" or t == "obs_mute_toggle":
                self._obs_cmd("ToggleMute", {"source": action.get("source", "Mic/Aux")})

            elif t == "obs_source_toggle":
                self._obs_cmd("SetSceneItemEnabled", {
                    "sceneName": action.get("scene", ""),
                    "sceneItemId": action.get("item_id", 0),
                    "sceneItemEnabled": action.get("enabled", True)
                })

            # ── 6. TWITCH ────────────────────────────────────────────────────
            elif t == "twitch_clip":
                self._twitch_api("POST", "/clips?broadcaster_id="+action.get("broadcaster_id",""),
                                 action.get("token",""), action.get("client_id",""))

            elif t == "twitch_chat":
                msg = action.get("message","")
                webbrowser.open(f"https://twitch.tv/popout/chat")   # fallback

            # ── 7. ZOOM ──────────────────────────────────────────────────────
            elif t == "zoom_mute":
                keyboard.send("alt+a")

            elif t == "zoom_camera":
                keyboard.send("alt+v")

            elif t == "zoom_raise_hand":
                keyboard.send("alt+y")

            elif t == "zoom_share":
                keyboard.send("alt+s")

            elif t == "zoom_leave":
                keyboard.send("alt+q")

            # ── 8. TEAMS ─────────────────────────────────────────────────────
            elif t == "teams_mute":
                keyboard.send("ctrl+shift+m")

            elif t == "teams_camera":
                keyboard.send("ctrl+shift+o")

            elif t == "teams_share":
                keyboard.send("ctrl+shift+e")

            elif t == "teams_reaction":
                keyboard.send("ctrl+shift+k")

            # ── 9. GOOGLE MEET ───────────────────────────────────────────────
            elif t == "meet_mute":
                keyboard.send("ctrl+d")

            elif t == "meet_camera":
                keyboard.send("ctrl+e")

            # ── 10. DISCORD ──────────────────────────────────────────────────
            elif t == "discord_mute":
                keyboard.send("ctrl+shift+m")

            elif t == "discord_deafen":
                keyboard.send("ctrl+shift+d")

            elif t == "discord_push_to_talk":
                key = action.get("key", "")
                if action.get("press", True):
                    keyboard.press(key)
                else:
                    keyboard.release(key)

            # ── 11. PRODUCTIVITÉ / OFFICE ────────────────────────────────────
            elif t == "office_new_doc":
                subprocess.Popen("winword /n", shell=True)

            elif t == "office_save":
                keyboard.send("ctrl+s")

            elif t == "office_save_pdf":
                keyboard.send("alt+f")
                time.sleep(0.3)
                keyboard.send("e")
                time.sleep(0.3)
                keyboard.send("p")

            elif t == "presentation_start":
                keyboard.send("f5")

            elif t == "presentation_next":
                keyboard.send("right")

            elif t == "presentation_prev":
                keyboard.send("left")

            elif t == "google_gmail":
                webbrowser.open("https://mail.google.com")

            elif t == "google_docs":
                webbrowser.open("https://docs.google.com/document/create")

            elif t == "google_sheets":
                webbrowser.open("https://sheets.google.com/create")

            elif t == "google_meet":
                webbrowser.open("https://meet.google.com/new")

            elif t == "google_calendar":
                webbrowser.open("https://calendar.google.com")

            # ── 12. DÉVELOPPEMENT ─────────────────────────────────────────────
            elif t == "vscode_open":
                path = action.get("path", ".")
                subprocess.Popen(f"code \"{path}\"", shell=True,
                    creationflags=subprocess.CREATE_NO_WINDOW)

            elif t == "git_pull":
                folder = action.get("folder", ".")
                subprocess.Popen(f"git -C \"{folder}\" pull", shell=True,
                    creationflags=subprocess.CREATE_NO_WINDOW)

            elif t == "git_push":
                folder = action.get("folder", ".")
                msg = action.get("message", "MacroDeck commit")
                subprocess.Popen(
                    f'git -C "{folder}" add -A && git -C "{folder}" commit -m "{msg}" && git -C "{folder}" push',
                    shell=True, creationflags=subprocess.CREATE_NO_WINDOW)

            elif t == "git_commit":
                folder = action.get("folder", ".")
                msg = action.get("message", "MacroDeck commit")
                subprocess.Popen(
                    f'git -C "{folder}" add -A && git -C "{folder}" commit -m "{msg}"',
                    shell=True, creationflags=subprocess.CREATE_NO_WINDOW)

            elif t == "docker_start":
                subprocess.Popen(
                    f"docker start {action.get('name','')}",
                    shell=True, creationflags=subprocess.CREATE_NO_WINDOW)

            elif t == "docker_stop":
                subprocess.Popen(
                    f"docker stop {action.get('name','')}",
                    shell=True, creationflags=subprocess.CREATE_NO_WINDOW)

            elif t == "docker_compose_up":
                folder = action.get("folder", ".")
                subprocess.Popen(f"docker-compose -f \"{folder}/docker-compose.yml\" up -d",
                    shell=True, creationflags=subprocess.CREATE_NO_WINDOW)

            elif t == "ssh":
                host = action.get("host", "")
                user = action.get("user", "")
                subprocess.Popen(f"start cmd /k ssh {user}@{host}", shell=True)

            elif t == "kubectl":
                cmd = action.get("command", "")
                subprocess.Popen(f"kubectl {cmd}", shell=True,
                    creationflags=subprocess.CREATE_NO_WINDOW)

            # ── 13. DOMOTIQUE / HOME ASSISTANT ────────────────────────────────
            elif t == "home_assistant":
                threading.Thread(target=self._ha_call, args=(action,), daemon=True).start()

            elif t == "hue_lights":
                threading.Thread(target=self._hue_call, args=(action,), daemon=True).start()

            # ── 14. IA / CHATGPT ──────────────────────────────────────────────
            elif t == "open_chatgpt":
                webbrowser.open("https://chatgpt.com")

            elif t == "chatgpt_prompt":
                webbrowser.open(
                    "https://chatgpt.com/?q=" +
                    action.get("prompt","").replace(" ", "+"))

            elif t == "translate_selection":
                keyboard.send("ctrl+c")
                time.sleep(0.2)
                import urllib.parse, tkinter as tk
                root = tk.Tk(); root.withdraw()
                txt = root.clipboard_get(); root.destroy()
                lang = action.get("lang", "fr")
                webbrowser.open(
                    f"https://translate.google.com/?sl=auto&tl={lang}&text=" +
                    urllib.parse.quote(txt))

            # ── 15. RÉSEAUX SOCIAUX ───────────────────────────────────────────
            elif t == "open_twitter":
                webbrowser.open("https://twitter.com")

            elif t == "open_linkedin":
                webbrowser.open("https://linkedin.com")

            elif t == "open_youtube":
                webbrowser.open("https://youtube.com")

            # ── 16. GESTION DU TEMPS ──────────────────────────────────────────
            elif t == "timer":
                seconds = int(action.get("seconds", 60))
                label   = action.get("label", f"Timer {seconds}s")
                threading.Thread(target=self._timer_fn, args=(seconds, label), daemon=True).start()

            elif t == "pomodoro":
                # 25 min travail
                threading.Thread(
                    target=self._timer_fn, args=(25*60, "🍅 Pomodoro terminé !"), daemon=True
                ).start()

            elif t == "stopwatch_start":
                self._sw_start = time.time()

            # ── 17. RÉSEAU / SERVEURS ─────────────────────────────────────────
            elif t == "ping":
                host = action.get("host", "8.8.8.8")
                subprocess.Popen(f"start cmd /k ping -t {host}", shell=True)

            elif t == "ping_silent":
                result = subprocess.run(
                    f"ping -n 4 {action.get('host','8.8.8.8')}",
                    shell=True, capture_output=True, text=True)
                log.info(result.stdout)

            elif t == "open_nas":
                webbrowser.open(action.get("url", ""))

            # ── 18. AUTOMATISATION AVANCÉE ────────────────────────────────────
            elif t == "multi_action":
                acts   = action.get("actions", [])
                delay  = action.get("delay", 0)
                threading.Thread(
                    target=self._run_multi, args=(acts, delay), daemon=True
                ).start()

            elif t == "delay":
                time.sleep(action.get("ms", 500) / 1000.0)

            elif t == "api_call":
                threading.Thread(target=self._api_call, args=(action,), daemon=True).start()

            elif t == "webhook":
                threading.Thread(target=self._webhook, args=(action,), daemon=True).start()

            elif t == "obs_mute_toggle":  # alias
                self._obs_cmd("ToggleMute", {"source": action.get("source", "Mic/Aux")})

            else:
                log.warning(f"Action inconnue: {t}")

        except Exception as e:
            log.error(f"Erreur action '{t}': {e}")

    # ── Helpers ─────────────────────────────────────────────────────────────────
    def _set_app_volume(self, app_name: str, level: int):
        ps = (f'$sessions = [activeds.audio]::GetAudioSessions(); '
              f'# fallback powershell')
        subprocess.Popen(
            ["powershell", "-Command",
             f'Get-Process "{app_name}" -ErrorAction SilentlyContinue | '
             f'ForEach-Object {{ [audio]::SetApplicationVolume($_.Id, {level/100}) }}'],
            creationflags=subprocess.CREATE_NO_WINDOW)

    def _set_brightness(self, level: int):
        subprocess.Popen(
            ["powershell", "-Command",
             f"(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods)"
             f".WmiSetBrightness(1,{level})"],
            creationflags=subprocess.CREATE_NO_WINDOW)

    def _obs_cmd(self, req_type: str, data: dict):
        try:
            import websocket
            ws = websocket.create_connection("ws://localhost:4444", timeout=3)
            ws.send(json.dumps({"request-type": req_type, "message-id": "md", **data}))
            ws.close()
        except Exception as e:
            log.warning(f"OBS WS: {e}")

    def _timer_fn(self, seconds: int, label: str):
        time.sleep(seconds)
        try:
            ctypes.windll.user32.MessageBoxW(0, label, "MacroDeck ⏱", 0x40 | 0x1000)
        except:
            pass

    def _run_multi(self, actions: list, delay_ms: int):
        for a in actions:
            self._run_one(a)
            if delay_ms:
                time.sleep(delay_ms / 1000.0)

    def _api_call(self, action: dict):
        import urllib.request
        url     = action.get("url", "")
        method  = action.get("method", "GET")
        headers = action.get("headers", {})
        body    = action.get("body")
        req = urllib.request.Request(url, method=method)
        for k, v in headers.items():
            req.add_header(k, v)
        if body:
            req.data = json.dumps(body).encode()
            req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                log.info(f"API {url} → {r.status}")
        except Exception as e:
            log.error(f"API call: {e}")

    def _webhook(self, action: dict):
        import urllib.request
        url     = action.get("url", "")
        payload = action.get("payload", {})
        req = urllib.request.Request(url,
            data=json.dumps(payload).encode(), method="POST")
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=10) as r:
                log.info(f"Webhook {url} → {r.status}")
        except Exception as e:
            log.error(f"Webhook: {e}")

    def _ha_call(self, action: dict):
        import urllib.request
        ha_url  = action.get("ha_url", "http://homeassistant.local:8123")
        token   = action.get("token", "")
        service = action.get("service", "").replace(".", "/")
        entity  = action.get("entity_id", "")
        url     = f"{ha_url}/api/services/{service}"
        req = urllib.request.Request(url,
            data=json.dumps({"entity_id": entity}).encode(), method="POST")
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("Content-Type", "application/json")
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                log.info(f"HA {service} {entity} → {r.status}")
        except Exception as e:
            log.error(f"Home Assistant: {e}")

    def _hue_call(self, action: dict):
        import urllib.request
        bridge = action.get("bridge_ip", "")
        token  = action.get("token", "")
        light  = action.get("light", "1")
        state  = action.get("state", {"on": True})
        url    = f"http://{bridge}/api/{token}/lights/{light}/state"
        req = urllib.request.Request(url,
            data=json.dumps(state).encode(), method="PUT")
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                log.info(f"Hue light {light} → {r.status}")
        except Exception as e:
            log.error(f"Hue: {e}")

    def _twitch_api(self, method, endpoint, token, client_id):
        import urllib.request
        url = "https://api.twitch.tv/helix" + endpoint
        req = urllib.request.Request(url, method=method)
        req.add_header("Authorization", f"Bearer {token}")
        req.add_header("Client-Id", client_id)
        try:
            with urllib.request.urlopen(req, timeout=5) as r:
                log.info(f"Twitch {endpoint} → {r.status}")
        except Exception as e:
            log.error(f"Twitch: {e}")

    def handle_pot(self, pot_idx: int, value: int, config: dict):
        action = config.get("action", "volume_system")
        if action == "volume_system":
            set_volume(value)
        elif action == "volume_app":
            self._set_app_volume(config.get("app", ""), value)
        elif action == "brightness":
            self._set_brightness(value)
        elif action == "custom":
            try:
                exec(config.get("script", ""), {"value": value})
            except Exception as e:
                log.error(f"Pot custom script: {e}")

# ─── APP WATCHER ──────────────────────────────────────────────────────────────
class AppWatcher:
    def __init__(self, on_change):
        self.on_change   = on_change
        self.current_app = ""
        self._running    = True
        threading.Thread(target=self._loop, daemon=True).start()

    def _get_active(self) -> str:
        if not WIN32_AVAILABLE:
            return ""
        try:
            hwnd = win32gui.GetForegroundWindow()
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            return psutil.Process(pid).name().lower().replace(".exe", "")
        except:
            return ""

    def _loop(self):
        while self._running:
            app = self._get_active()
            if app != self.current_app:
                self.current_app = app
                self.on_change(app)
            time.sleep(0.5)

# ─── MÉTRIQUES SYSTÈME (vraies valeurs) ──────────────────────────────────────
class MetricsCollector:
    AVAILABLE = ["cpu", "ram", "gpu_usage", "gpu_vram", "gpu_temp",
                 "cpu_temp", "ssd_usage", "ssd_temp", "net_up", "net_down"]

    def __init__(self):
        self._net_prev  = psutil.net_io_counters()
        self._net_time  = time.time()
        self._wmi_ohm   = None
        if WMI_AVAILABLE:
            try:
                self._wmi_ohm = wmilib.WMI(namespace="root\\OpenHardwareMonitor")
            except:
                pass

    def collect(self) -> dict:
        m = {}

        # CPU
        m["cpu"]      = psutil.cpu_percent(interval=None)
        m["cpu_cores"]= psutil.cpu_count(logical=True)
        freq = psutil.cpu_freq()
        m["cpu_freq"] = round(freq.current, 0) if freq else 0

        # CPU temp via OHM ou sensors
        m["cpu_temp"] = self._ohm_sensor("Temperature", "CPU")
        if m["cpu_temp"] is None:
            try:
                temps = psutil.sensors_temperatures() or {}
                for k, v in temps.items():
                    if v:
                        m["cpu_temp"] = round(v[0].current, 1)
                        break
            except: pass

        # RAM
        ram = psutil.virtual_memory()
        m["ram"]          = ram.percent
        m["ram_used_gb"]  = round(ram.used / 1e9, 1)
        m["ram_total_gb"] = round(ram.total / 1e9, 1)

        # GPU via GPUtil
        m["gpu_usage"] = 0; m["gpu_vram"] = 0; m["gpu_temp"] = None
        if GPU_AVAILABLE:
            try:
                gpus = GPUtil.getGPUs()
                if gpus:
                    g = gpus[0]
                    m["gpu_usage"] = round(g.load * 100, 1)
                    m["gpu_vram"]  = round(g.memoryUtil * 100, 1)
                    m["gpu_temp"]  = g.temperature
                    m["gpu_name"]  = g.name
            except: pass
        # fallback OHM
        if m["gpu_temp"] is None:
            m["gpu_temp"] = self._ohm_sensor("Temperature", "GPU")
        if m["gpu_usage"] == 0:
            v = self._ohm_sensor("Load", "GPU Core")
            if v: m["gpu_usage"] = v

        # SSD
        m["ssd_usage"] = 0; m["ssd_temp"] = None
        try:
            disk = psutil.disk_usage("/")
            m["ssd_usage"] = disk.percent
        except:
            try:
                disk = psutil.disk_usage("C:\\")
                m["ssd_usage"] = disk.percent
            except: pass
        try:
            temps = psutil.sensors_temperatures() or {}
            for k, v in temps.items():
                if "nvme" in k.lower() or "disk" in k.lower():
                    m["ssd_temp"] = round(v[0].current, 1)
                    break
        except: pass
        if m["ssd_temp"] is None:
            m["ssd_temp"] = self._ohm_sensor("Temperature", "SSD")

        # Disques détaillés
        disks = []
        for part in psutil.disk_partitions(all=False):
            try:
                u = psutil.disk_usage(part.mountpoint)
                disks.append({
                    "device": part.device,
                    "mountpoint": part.mountpoint,
                    "total_gb": round(u.total / 1e9, 1),
                    "used_gb":  round(u.used  / 1e9, 1),
                    "free_gb":  round(u.free  / 1e9, 1),
                    "percent":  u.percent
                })
            except: pass
        m["disks"] = disks

        # Réseau
        try:
            now = time.time()
            net = psutil.net_io_counters()
            dt  = now - self._net_time
            if dt > 0:
                m["net_up"]   = round((net.bytes_sent - self._net_prev.bytes_sent) / dt / 1024, 1)
                m["net_down"] = round((net.bytes_recv - self._net_prev.bytes_recv) / dt / 1024, 1)
            self._net_prev = net
            self._net_time = now
        except:
            m["net_up"] = 0; m["net_down"] = 0

        # Uptime
        m["uptime"] = str(datetime.timedelta(seconds=int(time.time() - psutil.boot_time())))

        # Volume
        m["volume"] = get_volume()
        m["muted"]  = get_mute()

        # Heure
        now_dt = datetime.datetime.now()
        m["time"] = now_dt.strftime("%H:%M:%S")
        m["date"] = now_dt.strftime("%d/%m/%Y")

        # Top processus CPU
        procs = []
        for p in sorted(
            psutil.process_iter(["name", "cpu_percent", "memory_percent"]),
            key=lambda x: (x.info.get("cpu_percent") or 0), reverse=True
        )[:8]:
            try:
                procs.append({
                    "name": p.info["name"],
                    "cpu":  round(p.info.get("cpu_percent") or 0, 1),
                    "mem":  round(p.info.get("memory_percent") or 0, 1)
                })
            except: pass
        m["top_processes"] = procs

        return m

    def _ohm_sensor(self, sensor_type: str, name_fragment: str) -> Optional[float]:
        """Lit une valeur depuis OpenHardwareMonitor WMI."""
        if not self._wmi_ohm:
            return None
        try:
            for s in self._wmi_ohm.Sensor():
                if s.SensorType == sensor_type and name_fragment.lower() in s.Name.lower():
                    return round(s.Value, 1)
        except: pass
        return None

    def metric_to_percent(self, key: str, value) -> int:
        if value is None:
            return 0
        caps = {"net_up": 10240, "net_down": 10240, "cpu_temp": 100,
                "gpu_temp": 100, "ssd_temp": 80}
        return min(100, int(float(value) / caps.get(key, 100) * 100))

# ─── TRANSPORT (Série + BLE) ──────────────────────────────────────────────────
class Transport:
    def __init__(self, on_message, config: dict):
        self.on_message  = on_message
        self.config      = config
        self.ser         = None
        self.ble_client  = None
        self._running    = True

    def start(self):
        self._connect_serial()

    def _connect_serial(self):
        port = self.config.get("serial_port", "AUTO")
        if port == "AUTO":
            port = self._auto_detect()
        if not port:
            return
        try:
            self.ser = serial.Serial(port, SERIAL_BAUD, timeout=0.1)
            threading.Thread(target=self._serial_loop, daemon=True).start()
        except Exception as e:
            log.error(f"Série: {e}")

    def _auto_detect(self) -> Optional[str]:
        keywords = ["USB", "CP210", "CH340", "FTDI", "Silicon"]
        for p in serial.tools.list_ports.comports():
            if any(k in p.description.upper() for k in keywords):
                return p.device
        ports = serial.tools.list_ports.comports()
        return ports[0].device if ports else None

    def _serial_loop(self):
        while self._running and self.ser and self.ser.is_open:
            try:
                line = self.ser.readline().decode("utf-8", errors="ignore").strip()
                if line:
                    self.on_message(line)
            except Exception as e:
                log.error(f"Série read: {e}")
                time.sleep(1)

    def send(self, obj: dict):
        raw = json.dumps(obj, separators=(",", ":")) + "\n"
        if self.ser and self.ser.is_open:
            try:
                self.ser.write(raw.encode())
            except Exception as e:
                log.error(f"Série write: {e}")

# ─── MACRODECK CORE ───────────────────────────────────────────────────────────
class MacroDeck:
    def __init__(self):
        self.cfg       = ConfigManager()
        self.engine    = ActionEngine()
        self.metrics   = MetricsCollector()
        self.transport = Transport(self._on_esp32_msg, self.cfg.data)
        self.ws_clients= set()
        self.watcher   = AppWatcher(self._on_app_change)

    def _on_app_change(self, app: str):
        for name, profile in self.cfg.data["profiles"].items():
            trigger = (profile.get("app_trigger") or "").lower()
            if trigger and trigger in app.lower():
                self.cfg.data["active_profile"] = name
                self._broadcast({"type": "profile_changed", "profile": name})
                return
        if self.cfg.data.get("active_profile") != "default":
            self.cfg.data["active_profile"] = "default"
            self._broadcast({"type": "profile_changed", "profile": "default"})

    def _on_esp32_msg(self, raw: str):
        try:
            msg = json.loads(raw)
        except:
            return
        t = msg.get("t")
        if t == "ready":
            self.transport.send({"t": "ping"})
        elif t in ("press", "long_press", "double_click"):
            idx     = msg.get("i", 0)
            profile = self.cfg.active_profile()
            actions = profile["buttons"].get(str(idx), {}).get(t, [])
            threading.Thread(target=self.engine.run_actions, args=(actions,), daemon=True).start()
            self._broadcast({"type": "button_event", "button": idx, "event": t})
        elif t == "pot":
            idx     = msg.get("i", 0)
            value   = msg.get("v", 0)
            profile = self.cfg.active_profile()
            pot_cfg = profile["pots"].get(str(idx), {})
            threading.Thread(target=self.engine.handle_pot, args=(idx, value, pot_cfg), daemon=True).start()
            self._broadcast({"type": "pot_event", "pot": idx, "value": value})

    async def _metrics_loop(self):
        # Premier appel pour init le compteur réseau
        self.metrics.collect()
        while True:
            await asyncio.sleep(METRICS_INTERVAL)
            m = self.metrics.collect()
            led_cfg = self.cfg.data.get("led_strips", {})
            for i in range(4):
                sc   = led_cfg.get(str(i), {})
                key  = sc.get("metric", ["cpu","ram","gpu_usage","ssd_usage"][i])
                pct  = self.metrics.metric_to_percent(key, m.get(key, 0))
                self.transport.send({"t": "led", "s": i, "v": pct})
            self._broadcast({"type": "metrics", "data": m})

    async def _ws_handler(self, ws: WebSocketServerProtocol):
        self.ws_clients.add(ws)
        await ws.send(json.dumps({"type": "config", "data": self.cfg.data}))
        try:
            async for raw in ws:
                await self._handle_gui_msg(json.loads(raw), ws)
        except:
            pass
        finally:
            self.ws_clients.discard(ws)

    async def _handle_gui_msg(self, msg: dict, ws):
        t = msg.get("type")
        if t == "save_config":
            self.cfg.data = msg["data"]
            self.cfg.save()
            await ws.send(json.dumps({"type": "config_saved"}))
        elif t == "set_profile":
            self.cfg.data["active_profile"] = msg["profile"]
            self._broadcast({"type": "profile_changed", "profile": msg["profile"]})
        elif t == "test_action":
            threading.Thread(target=self.engine.run_actions, args=(msg["actions"],), daemon=True).start()
        elif t == "get_ports":
            ports = [p.device for p in serial.tools.list_ports.comports()]
            await ws.send(json.dumps({"type": "ports", "data": ports}))
        elif t == "get_metrics_list":
            await ws.send(json.dumps({"type": "metrics_list", "data": MetricsCollector.AVAILABLE}))
        elif t == "led_test":
            self.transport.send({"t": "led", "s": msg["strip"], "v": msg["value"]})
        elif t == "get_apps":
            apps = get_installed_apps()
            await ws.send(json.dumps({"type": "apps", "data": apps}))

    def _broadcast(self, obj: dict):
        raw = json.dumps(obj)
        for ws in list(self.ws_clients):
            asyncio.ensure_future(ws.send(raw))

    async def run(self):
        self.transport.start()
        srv = await websockets.serve(self._ws_handler, "localhost", WS_PORT)
        await asyncio.gather(self._metrics_loop(), srv.wait_closed())

# ─── SERVEUR HTTP MINIMAL (sert gui.html) ─────────────────────────────────────
def _start_http_server():
    """Lance un serveur HTTP simple sur le port 8766 pour servir gui.html."""
    import http.server, socketserver

    # Aller dans le dossier du script pour trouver gui.html
    os.chdir(os.path.dirname(os.path.abspath(__file__)))

    class SilentHandler(http.server.SimpleHTTPRequestHandler):
        def log_message(self, *args):
            pass  # Pas de log dans la console

    with socketserver.TCPServer(("127.0.0.1", 8766), SilentHandler) as httpd:
        httpd.serve_forever()

# ─── ENTRY POINT ──────────────────────────────────────────────────────────────
if __name__ == "__main__":
    # Lancer le serveur HTTP dans un thread dédié
    http_thread = threading.Thread(target=_start_http_server, daemon=True)
    http_thread.start()

    # Ouvrir le navigateur après 1.5s
    def _open_gui():
        time.sleep(1.5)
        webbrowser.open("http://127.0.0.1:8766/gui.html")
    threading.Thread(target=_open_gui, daemon=True).start()

    deck = MacroDeck()
    try:
        asyncio.run(deck.run())
    except KeyboardInterrupt:
        pass
