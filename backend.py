"""
MacroDeck Backend
=================
- Connexion ESP32 via USB Série + BLE (NimBLE)
- Détection application active (Windows)
- Moteur d'actions : clavier, souris, médias, scripts, apps, texte, délais
- Envoi métriques PC → LEDs ESP32 (CPU, RAM, GPU, SSD, réseau, temp)
- Serveur WebSocket local → GUI Electron
- Config en JSON

Dépendances :
    pip install pyserial bleak psutil gputil pynput pywin32
                keyboard mouse websockets asyncio aiofiles

Lancer : python backend.py
"""

import asyncio
import json
import os
import sys
import time
import subprocess
import threading
import logging
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
    import win32gui
    import win32process
    WIN32_AVAILABLE = True
except ImportError:
    WIN32_AVAILABLE = False

try:
    from bleak import BleakClient, BleakScanner
    BLE_AVAILABLE = True
except ImportError:
    BLE_AVAILABLE = False

# ─── CONFIG ────────────────────────────────────────────────────────────────

CONFIG_PATH   = Path("config.json")
LOG_LEVEL     = logging.DEBUG
WS_PORT       = 8765
SERIAL_BAUD   = 115200
METRICS_INTERVAL = 1.0   # secondes

BLE_SERVICE_UUID = "12345678-1234-1234-1234-123456789abc"
BLE_TX_UUID      = "12345678-1234-1234-1234-123456789abd"
BLE_RX_UUID      = "12345678-1234-1234-1234-123456789abe"

logging.basicConfig(level=LOG_LEVEL, format="%(asctime)s [%(levelname)s] %(message)s")
log = logging.getLogger("MacroDeck")

# ─── CONFIG MANAGER ────────────────────────────────────────────────────────

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
        str(i): {"metric": ["cpu", "ram", "gpu", "ssd"][i], "thresholds": [50, 80]} for i in range(4)
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
                log.info("Config chargée")
            except Exception as e:
                log.error(f"Erreur config: {e}")

    def save(self):
        with open(CONFIG_PATH, "w", encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    def get_profile(self, name: str) -> dict:
        return self.data["profiles"].get(name, self.data["profiles"]["default"])

    def active_profile(self) -> dict:
        return self.get_profile(self.data.get("active_profile", "default"))

# ─── ACTION ENGINE ─────────────────────────────────────────────────────────

class ActionEngine:
    """Exécute toutes les actions définies dans le profil."""

    def run_actions(self, actions: list):
        """Chaîne une liste d'actions séquentiellement."""
        for action in actions:
            self._run_one(action)

    def _run_one(self, action: dict):
        t = action.get("type")
        try:
            if t == "hotkey":
                keyboard.send(action["keys"])

            elif t == "type_text":
                keyboard.write(action["text"], delay=action.get("delay", 0.05))

            elif t == "launch":
                subprocess.Popen(action["path"], shell=True)

            elif t == "script_python":
                exec(action["code"], {"action": action})

            elif t == "script_powershell":
                subprocess.Popen(["powershell", "-Command", action["code"]], shell=False)

            elif t == "script_ahk":
                subprocess.Popen(["AutoHotkey.exe", action["path"]], shell=False)

            elif t == "media_play_pause":
                keyboard.send("play/pause media")

            elif t == "media_next":
                keyboard.send("next track")

            elif t == "media_prev":
                keyboard.send("previous track")

            elif t == "volume_up":
                keyboard.send("volume up")

            elif t == "volume_down":
                keyboard.send("volume down")

            elif t == "volume_mute":
                keyboard.send("volume mute")

            elif t == "volume_set":
                self._set_volume(action["value"])

            elif t == "delay":
                time.sleep(action["ms"] / 1000)

            elif t == "mouse_click":
                mouse.click(action.get("button", "left"))

            elif t == "mouse_move":
                mouse.move(action["x"], action["y"], absolute=action.get("absolute", True))

            elif t == "mouse_scroll":
                mouse.wheel(action.get("delta", 1))

            elif t == "open_url":
                import webbrowser
                webbrowser.open(action["url"])

            elif t == "discord_mute":
                keyboard.send("ctrl+shift+m")

            elif t == "discord_deafen":
                keyboard.send("ctrl+shift+d")

            elif t == "obs_scene":
                # Via OBS WebSocket (plugin obs-websocket)
                self._obs_switch_scene(action["scene"])

            elif t == "win_minimize_all":
                keyboard.send("win+d")

            elif t == "win_lock":
                keyboard.send("win+l")

            else:
                log.warning(f"Action inconnue: {t}")

        except Exception as e:
            log.error(f"Erreur action {t}: {e}")

    def _set_volume(self, level: int):
        """Définit le volume système (0-100) via PowerShell."""
        ps = f"(New-Object -ComObject WScript.Shell).SendKeys([char]174 * 50); " \
             f"$vol = {level}; " \
             f"$obj = New-Object -ComObject WScript.Shell"
        subprocess.Popen(
            ["powershell", "-Command",
             f"$wsh = New-Object -ComObject WScript.Shell; "
             f"[audio]::Volume = {level/100}"],
            shell=False
        )

    def _obs_switch_scene(self, scene: str):
        """Bascule de scène OBS via WebSocket."""
        try:
            import obsws_python as obs
            cl = obs.ReqClient(host="localhost", port=4455, password="", timeout=3)
            cl.set_current_program_scene(scene)
        except Exception as e:
            log.error(f"OBS: {e}")

    def handle_pot(self, pot_idx: int, value: int, config: dict):
        """Gère un mouvement de potentiomètre (value: 0-100)."""
        action = config.get("action", "volume_system")

        if action == "volume_system":
            self._set_volume(value)

        elif action == "volume_app":
            self._set_app_volume(config.get("app", ""), value)

        elif action == "brightness":
            self._set_brightness(value)

        elif action == "scroll":
            # Convertit en défilement relatif
            pass

        elif action == "custom":
            exec(config.get("script", ""), {"value": value})

    def _set_app_volume(self, app_name: str, level: int):
        ps = f'$app = "{app_name}"; ' \
             f'$vol = {level / 100}; ' \
             f'Get-Process $app | ForEach-Object {{ ' \
             f'  [audio]::SetApplicationVolume($_.Id, $vol) }}'
        subprocess.Popen(["powershell", "-Command", ps], shell=False)

    def _set_brightness(self, level: int):
        ps = f"(Get-WmiObject -Namespace root/WMI -Class WmiMonitorBrightnessMethods)" \
             f".WmiSetBrightness(1,{level})"
        subprocess.Popen(["powershell", "-Command", ps], shell=False)

# ─── APP WATCHER ───────────────────────────────────────────────────────────

class AppWatcher:
    """Détecte l'application active sous Windows."""

    def __init__(self, on_change):
        self.on_change    = on_change
        self.current_app  = ""
        self._running     = True
        self._thread      = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def _get_active_app(self) -> str:
        if not WIN32_AVAILABLE:
            return ""
        try:
            hwnd = win32gui.GetForegroundWindow()
            _, pid = win32process.GetWindowThreadProcessId(hwnd)
            proc = psutil.Process(pid)
            return proc.name().lower().replace(".exe", "")
        except Exception:
            return ""

    def _loop(self):
        while self._running:
            app = self._get_active_app()
            if app != self.current_app:
                self.current_app = app
                self.on_change(app)
            time.sleep(0.5)

# ─── METRICS ───────────────────────────────────────────────────────────────

class MetricsCollector:
    """Collecte les métriques système."""

    AVAILABLE_METRICS = [
        "cpu", "ram", "gpu_usage", "gpu_vram", "gpu_temp",
        "cpu_temp", "ssd_usage", "ssd_temp",
        "net_up", "net_down"
    ]

    def __init__(self):
        self._net_prev = psutil.net_io_counters()
        self._net_time = time.time()

    def collect(self) -> dict:
        m = {}

        # CPU
        m["cpu"] = psutil.cpu_percent(interval=None)

        # RAM
        ram = psutil.virtual_memory()
        m["ram"] = ram.percent

        # GPU
        if GPU_AVAILABLE:
            try:
                gpus = GPUtil.getGPUs()
                if gpus:
                    g = gpus[0]
                    m["gpu_usage"] = g.load * 100
                    m["gpu_vram"]  = g.memoryUtil * 100
                    m["gpu_temp"]  = g.temperature
            except Exception:
                pass

        # SSD
        try:
            disk = psutil.disk_usage("/")
            m["ssd_usage"] = disk.percent
            temps = psutil.sensors_temperatures() or {}
            for name, entries in temps.items():
                if "nvme" in name.lower() or "disk" in name.lower():
                    m["ssd_temp"] = entries[0].current
                    break
        except Exception:
            pass

        # CPU temp
        try:
            temps = psutil.sensors_temperatures() or {}
            for name, entries in temps.items():
                if "coretemp" in name.lower() or "k10temp" in name.lower():
                    m["cpu_temp"] = entries[0].current
                    break
        except Exception:
            pass

        # Réseau
        try:
            now = time.time()
            net = psutil.net_io_counters()
            dt  = now - self._net_time
            if dt > 0:
                m["net_up"]   = (net.bytes_sent - self._net_prev.bytes_sent) / dt / 1024
                m["net_down"] = (net.bytes_recv - self._net_prev.bytes_recv) / dt / 1024
            self._net_prev = net
            self._net_time = now
        except Exception:
            pass

        return m

    def metric_to_percent(self, key: str, value: float) -> int:
        """Normalise une métrique en 0-100 pour les LEDs."""
        caps = {
            "net_up":   10240,  # 10 MB/s = 100%
            "net_down": 10240,
            "cpu_temp": 100,
            "gpu_temp": 100,
            "ssd_temp": 80,
        }
        cap = caps.get(key, 100)
        return min(100, int(value / cap * 100))

# ─── TRANSPORT (Série + BLE) ────────────────────────────────────────────────

class Transport:
    """Gère la communication série et BLE avec l'ESP32."""

    def __init__(self, on_message, config: dict):
        self.on_message  = on_message
        self.config      = config
        self.ser: Optional[serial.Serial] = None
        self.ble_client: Optional[BleakClient] = None
        self._ser_thread = None
        self._running    = True

    def start(self):
        self._connect_serial()
        asyncio.get_event_loop().create_task(self._ble_loop())

    def _connect_serial(self):
        port = self.config.get("serial_port", "AUTO")
        if port == "AUTO":
            port = self._auto_detect_port()
        if not port:
            log.warning("Aucun port série trouvé")
            return
        try:
            self.ser = serial.Serial(port, SERIAL_BAUD, timeout=0.1)
            log.info(f"Série connectée: {port}")
            self._ser_thread = threading.Thread(target=self._serial_loop, daemon=True)
            self._ser_thread.start()
        except Exception as e:
            log.error(f"Série: {e}")

    def _auto_detect_port(self) -> Optional[str]:
        for p in serial.tools.list_ports.comports():
            if "USB" in p.description.upper() or "CP210" in p.description.upper() \
               or "CH340" in p.description.upper() or "FTDI" in p.description.upper():
                return p.device
        ports = serial.tools.list_ports.comports()
        return ports[0].device if ports else None

    def _serial_loop(self):
        buf = ""
        while self._running and self.ser and self.ser.is_open:
            try:
                line = self.ser.readline().decode("utf-8", errors="ignore").strip()
                if line:
                    self.on_message(line)
            except Exception as e:
                log.error(f"Série read: {e}")
                time.sleep(1)

    async def _ble_loop(self):
        if not BLE_AVAILABLE:
            return
        name = self.config.get("ble_device", "MacroDeck")
        while self._running:
            try:
                log.info("Scan BLE...")
                device = await BleakScanner.find_device_by_name(name, timeout=10)
                if not device:
                    await asyncio.sleep(5)
                    continue
                async with BleakClient(device) as client:
                    self.ble_client = client
                    log.info(f"BLE connecté: {device.address}")
                    await client.start_notify(BLE_TX_UUID, self._ble_notify)
                    while client.is_connected:
                        await asyncio.sleep(1)
                    self.ble_client = None
            except Exception as e:
                log.error(f"BLE: {e}")
                await asyncio.sleep(5)

    def _ble_notify(self, sender, data: bytearray):
        try:
            msg = data.decode("utf-8").strip()
            if msg:
                self.on_message(msg)
        except Exception as e:
            log.error(f"BLE notify: {e}")

    def send(self, obj: dict):
        raw = json.dumps(obj, separators=(",", ":")) + "\n"
        # Série
        if self.ser and self.ser.is_open:
            try:
                self.ser.write(raw.encode())
            except Exception as e:
                log.error(f"Série write: {e}")
        # BLE
        if self.ble_client and self.ble_client.is_connected:
            asyncio.ensure_future(
                self.ble_client.write_gatt_char(BLE_RX_UUID, raw.encode())
            )

# ─── MACRODECK CORE ────────────────────────────────────────────────────────

class MacroDeck:
    def __init__(self):
        self.cfg        = ConfigManager()
        self.engine     = ActionEngine()
        self.metrics    = MetricsCollector()
        self.transport  = Transport(self._on_esp32_message, self.cfg.data)
        self.ws_clients = set()
        self.active_app = ""
        self.watcher    = AppWatcher(self._on_app_change)

    def _on_app_change(self, app: str):
        self.active_app = app
        log.info(f"App active: {app}")
        # Cherche un profil correspondant
        for name, profile in self.cfg.data["profiles"].items():
            trigger = profile.get("app_trigger", "")
            if trigger and trigger.lower() in app.lower():
                self.cfg.data["active_profile"] = name
                log.info(f"Profil auto: {name}")
                self._broadcast({"type": "profile_changed", "profile": name})
                return
        # Revenir au profil default si aucun match
        if self.cfg.data["active_profile"] != "default":
            self.cfg.data["active_profile"] = "default"
            self._broadcast({"type": "profile_changed", "profile": "default"})

    def _on_esp32_message(self, raw: str):
        try:
            msg = json.loads(raw)
        except Exception:
            return

        t = msg.get("t")
        log.debug(f"ESP32 → {msg}")

        if t == "ready":
            log.info("ESP32 prêt !")
            self.transport.send({"t": "ping"})

        elif t in ("press", "long_press", "double_click"):
            idx     = msg.get("i", 0)
            profile = self.cfg.active_profile()
            btn_cfg = profile["buttons"].get(str(idx), {})
            actions = btn_cfg.get(t, [])
            log.info(f"Bouton {idx} [{t}] → {len(actions)} action(s)")
            threading.Thread(target=self.engine.run_actions, args=(actions,), daemon=True).start()
            self._broadcast({"type": "button_event", "button": idx, "event": t})

        elif t == "pot":
            idx     = msg.get("i", 0)
            value   = msg.get("v", 0)
            profile = self.cfg.active_profile()
            pot_cfg = profile["pots"].get(str(idx), {})
            threading.Thread(
                target=self.engine.handle_pot,
                args=(idx, value, pot_cfg),
                daemon=True
            ).start()
            self._broadcast({"type": "pot_event", "pot": idx, "value": value})

    async def _metrics_loop(self):
        """Collecte les métriques et met à jour les LEDs + GUI."""
        while True:
            m = self.metrics.collect()
            led_cfg = self.cfg.data.get("led_strips", {})

            for strip_idx in range(4):
                strip_conf = led_cfg.get(str(strip_idx), {})
                metric_key = strip_conf.get("metric", "cpu")
                raw_val    = m.get(metric_key, 0)
                pct        = self.metrics.metric_to_percent(metric_key, raw_val)
                self.transport.send({"t": "led", "s": strip_idx, "v": pct})

            self._broadcast({"type": "metrics", "data": m})
            await asyncio.sleep(METRICS_INTERVAL)

    # ─── WebSocket (GUI) ───────────────────────────────────────────────────

    async def _ws_handler(self, ws: WebSocketServerProtocol):
        self.ws_clients.add(ws)
        log.info(f"GUI connectée: {ws.remote_address}")
        # Envoie la config initiale
        await ws.send(json.dumps({"type": "config", "data": self.cfg.data}))
        try:
            async for msg in ws:
                await self._handle_gui_message(json.loads(msg), ws)
        except Exception:
            pass
        finally:
            self.ws_clients.discard(ws)

    async def _handle_gui_message(self, msg: dict, ws):
        t = msg.get("type")

        if t == "save_config":
            self.cfg.data = msg["data"]
            self.cfg.save()
            await ws.send(json.dumps({"type": "config_saved"}))

        elif t == "set_profile":
            self.cfg.data["active_profile"] = msg["profile"]
            self._broadcast({"type": "profile_changed", "profile": msg["profile"]})

        elif t == "test_action":
            threading.Thread(
                target=self.engine.run_actions,
                args=(msg["actions"],),
                daemon=True
            ).start()

        elif t == "get_ports":
            ports = [p.device for p in serial.tools.list_ports.comports()]
            await ws.send(json.dumps({"type": "ports", "data": ports}))

        elif t == "get_metrics_list":
            await ws.send(json.dumps({
                "type": "metrics_list",
                "data": MetricsCollector.AVAILABLE_METRICS
            }))

        elif t == "led_test":
            self.transport.send({"t": "led", "s": msg["strip"], "v": msg["value"]})

    def _broadcast(self, obj: dict):
        raw = json.dumps(obj)
        for ws in list(self.ws_clients):
            asyncio.ensure_future(ws.send(raw))

    async def run(self):
        self.transport.start()
        ws_server = await websockets.serve(self._ws_handler, "localhost", WS_PORT)
        log.info(f"WebSocket sur ws://localhost:{WS_PORT}")
        await asyncio.gather(
            self._metrics_loop(),
            ws_server.wait_closed()
        )

# ─── ENTRY POINT ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    deck = MacroDeck()
    try:
        asyncio.run(deck.run())
    except KeyboardInterrupt:
        log.info("Arrêt.")
