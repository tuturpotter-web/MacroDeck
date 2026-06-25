"""
MacroDeck Backend v15.1
- Console 100% cachée (SW_HIDE + FreeConsole)
- Pas d'ouverture automatique du navigateur au démarrage
- Profils indépendants avec création/suppression/renommage
- Action switch_profile
- Serveur HTTP silencieux sur 8766
- WebSocket sur 8765
"""
APP_VERSION = "dev"
import sys, os, ctypes, threading, time, asyncio, json, subprocess, re
import webbrowser, shutil, glob, logging, datetime
from pathlib import Path
from typing import Optional

# ── CACHER CONSOLE ──────────────────────────────────────────────────────────
if sys.platform == "win32":
    try:
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd:
            ctypes.windll.user32.ShowWindow(hwnd, 0)
        ctypes.windll.kernel32.FreeConsole()
    except: pass

# Flags pour qu'AUCUN sous-processus (os.system, shell=True, cmd.exe...)
# ne puisse jamais faire apparaître une fenêtre console, même brièvement.
CREATE_NO_WINDOW = 0x08000000
_SI = None
if sys.platform == "win32":
    _SI = subprocess.STARTUPINFO()
    _SI.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    _SI.wShowWindow = 0  # SW_HIDE

def run_hidden(cmd, **kwargs):
    """Remplace subprocess.Popen pour TOUJOURS cacher la fenêtre, shell=True ou non."""
    kwargs.setdefault("creationflags", CREATE_NO_WINDOW)
    kwargs.setdefault("startupinfo", _SI)
    return subprocess.Popen(cmd, **kwargs)

def run_silent(cmd: str):
    """Remplace os.system() par un appel qui ne crée jamais de fenêtre console."""
    return run_hidden(cmd, shell=True)

def _get_default_browser_command() -> Optional[str]:
    """Lit le VRAI navigateur par défaut choisi par l'utilisateur dans Windows
    10/11 (clé de registre UserChoice), et retourne la commande pour le
    lancer. C'est plus fiable que os.startfile()/webbrowser.open(), qui
    peuvent parfois retomber sur une association "http" legacy cassée
    (souvent Internet Explorer) au lieu du vrai navigateur configuré dans
    Paramètres Windows > Applications par défaut."""
    if sys.platform != "win32": return None
    try:
        import winreg
        # 1. Quel ProgId est choisi par l'utilisateur pour le protocole http
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\http\UserChoice"
        )
        prog_id, _ = winreg.QueryValueEx(key, "ProgId")
        winreg.CloseKey(key)

        # 2. Quelle commande correspond à ce ProgId
        cmd_key = winreg.OpenKey(
            winreg.HKEY_CLASSES_ROOT, fr"{prog_id}\shell\open\command"
        )
        command, _ = winreg.QueryValueEx(cmd_key, "")
        winreg.CloseKey(cmd_key)
        return command  # ex: '"C:\...\chrome.exe" --single-argument %1'
    except Exception as e:
        log.warning(f"Lecture navigateur par défaut: {e}")
        return None

def open_url_default(url: str):
    """Ouvre une URL avec le VRAI navigateur par défaut de Windows. Lit le
    réglage UserChoice du registre et lance l'exécutable directement plutôt
    que de passer par une association de protocole générique, qui peut
    retomber sur Internet Explorer sur certaines installations Windows
    (association "http" legacy non synchronisée avec le choix utilisateur
    moderne). Conserve un repli en cascade si la lecture registre échoue."""
    if not url: return
    if sys.platform == "win32":
        cmd = _get_default_browser_command()
        if cmd:
            try:
                if "%1" in cmd:
                    final_cmd = cmd.replace("%1", url)
                else:
                    final_cmd = f'{cmd} "{url}"'
                run_hidden(final_cmd, shell=True)
                return
            except Exception as e:
                log.error(f"Lancement navigateur via registre: {e}")
        # Repli : ShellExecute standard (peut, dans de rares cas, retomber
        # sur une association legacy, mais reste mieux que rien)
        try:
            os.startfile(url)
            return
        except Exception as e:
            log.error(f"open_url_default fallback os.startfile('{url}'): {e}")
    try:
        webbrowser.open(url)
    except Exception as e:
        log.error(f"open_url_default fallback webbrowser('{url}'): {e}")

import psutil
import keyboard
import mouse
import websockets
from websockets.server import WebSocketServerProtocol

try:
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    from comtypes import CLSCTX_ALL
    PYCAW_OK = True
except: PYCAW_OK = False

try:
    import win32gui, win32process
    WIN32_OK = True
except: WIN32_OK = False

# GPUtil est volontairement RETIRÉ : il lance "nvidia-smi" en interne via
# subprocess SANS masquer la fenêtre console, ce qui provoquait le
# clignotement répété (la boucle de métriques tourne chaque seconde).
# On lit nvidia-smi nous-mêmes avec run_hidden() qui garantit STARTF_USESHOWWINDOW.
GPU_OK = shutil.which("nvidia-smi") is not None

try:
    import wmi as wmilib
    WMI_OK = True
except: WMI_OK = False

try:
    import serial, serial.tools.list_ports
    SERIAL_OK = True
except: SERIAL_OK = False

logging.basicConfig(level=logging.WARNING)
log = logging.getLogger("MD")

WS_PORT   = 8765
HTTP_PORT = 8766
CONFIG_PATH = Path(os.path.expanduser("~")) / ".macrodeck" / "config.json"
CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)

# ── VOLUME ───────────────────────────────────────────────────────────────────
def _vif():
    if not PYCAW_OK: return None
    try:
        d = AudioUtilities.GetSpeakers()
        i = d.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None)
        return i.QueryInterface(IAudioEndpointVolume)
    except: return None

def get_volume():
    try: v=_vif(); return int(v.GetMasterVolumeLevelScalar()*100) if v else 0
    except: return 0

def set_volume(lv):
    try: v=_vif(); v and v.SetMasterVolumeLevelScalar(max(0,min(100,lv))/100.0, None)
    except: pass

def get_mute():
    try: v=_vif(); return bool(v.GetMute()) if v else False
    except: return False

def set_mute(s):
    try: v=_vif(); v and v.SetMute(s, None)
    except: pass

def set_app_volume(process_name: str, level: int):
    """Règle le volume d'une application précise via ses sessions audio (pycaw)."""
    if not PYCAW_OK or not process_name: return
    try:
        from pycaw.pycaw import ISimpleAudioVolume
        target = process_name.lower().replace(".exe","")
        for session in AudioUtilities.GetAllSessions():
            if session.Process and session.Process.name().lower().replace(".exe","") == target:
                vol = session._ctl.QueryInterface(ISimpleAudioVolume)
                vol.SetMasterVolume(max(0,min(100,level))/100.0, None)
    except Exception as e:
        log.error(f"set_app_volume: {e}")

def get_app_volume(process_name: str):
    if not PYCAW_OK or not process_name: return None
    try:
        from pycaw.pycaw import ISimpleAudioVolume
        target = process_name.lower().replace(".exe","")
        for session in AudioUtilities.GetAllSessions():
            if session.Process and session.Process.name().lower().replace(".exe","") == target:
                vol = session._ctl.QueryInterface(ISimpleAudioVolume)
                return round(vol.GetMasterVolume()*100)
    except: pass
    return None

def list_audio_sessions():
    """Liste les applications qui ont actuellement une session audio active (pour le picker)."""
    out = []
    if not PYCAW_OK: return out
    try:
        seen = set()
        for session in AudioUtilities.GetAllSessions():
            if session.Process:
                name = session.Process.name()
                if name.lower() not in seen:
                    seen.add(name.lower())
                    out.append(name)
    except: pass
    return sorted(out)

# ── APPS ─────────────────────────────────────────────────────────────────────
def get_installed_apps():
    apps=[]; seen=set()
    def add(name, path, kind):
        try:
            k=name.lower().strip()
            if k and k not in seen:
                seen.add(k); apps.append({"name":name,"path":path,"type":kind})
        except: pass

    # Menu Démarrer (.lnk) — protégé : un dossier verrouillé ou un raccourci
    # corrompu ne doit jamais faire planter tout le scan.
    try:
        for base in [
            os.path.join(os.environ.get("APPDATA",""),"Microsoft","Windows","Start Menu","Programs"),
            r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs"]:
            try:
                if os.path.isdir(base):
                    for r,_,files in os.walk(base):
                        for f in files:
                            if f.endswith(".lnk"): add(f[:-4], os.path.join(r,f), "lnk")
            except Exception as e:
                log.warning(f"get_installed_apps menu démarrer '{base}': {e}")
    except Exception as e:
        log.error(f"get_installed_apps menu démarrer: {e}")

    # Registre Windows (apps installées avec DisplayName/DisplayIcon)
    try:
        import winreg
        for hive in [winreg.HKEY_LOCAL_MACHINE, winreg.HKEY_CURRENT_USER]:
            for p in [r"SOFTWARE\Microsoft\Windows\CurrentVersion\Uninstall",
                      r"SOFTWARE\WOW6432Node\Microsoft\Windows\CurrentVersion\Uninstall"]:
                try:
                    key=winreg.OpenKey(hive,p); i=0
                    while True:
                        try:
                            sub=winreg.OpenKey(key,winreg.EnumKey(key,i))
                            try:
                                n=winreg.QueryValueEx(sub,"DisplayName")[0]
                                e=winreg.QueryValueEx(sub,"DisplayIcon")[0].split(",")[0].strip('"')
                                if e.endswith(".exe") and os.path.isfile(e): add(n,e,"exe")
                            except: pass
                            i+=1
                        except OSError: break
                except: pass
    except Exception as e:
        log.warning(f"get_installed_apps registre: {e}")

    # Program Files / dossiers locaux — protégé individuellement par dossier,
    # un sous-dossier inaccessible (permissions) ne bloque pas les suivants.
    for base in [r"C:\Program Files",r"C:\Program Files (x86)",
                 os.path.join(os.environ.get("LOCALAPPDATA",""),"Programs")]:
        try:
            if os.path.isdir(base):
                for d in os.listdir(base):
                    try:
                        full=os.path.join(base,d)
                        if os.path.isdir(full):
                            for f in os.listdir(full):
                                if f.endswith(".exe"): add(f[:-4],os.path.join(full,f),"exe")
                    except Exception as e:
                        log.warning(f"get_installed_apps '{d}': {e}")
        except Exception as e:
            log.warning(f"get_installed_apps base '{base}': {e}")

    apps.sort(key=lambda x:x["name"].lower())
    return apps

# ── CONFIG ───────────────────────────────────────────────────────────────────
def empty_profile(name):
    return {
        "name": name,
        "app_trigger": "",
        "buttons": {str(i):{"icon":"⭐","label":"Bouton "+str(i+1),"press":[],"long_press":[],"double_click":[]} for i in range(8)},
        "pots": {str(i):{"name":["Volume","App Vol","Luminosité","Custom"][i],"action":["volume_system","volume_app","brightness","custom"][i]} for i in range(4)}
    }

DEFAULT_CONFIG = {
    "profiles": {
        "default": empty_profile("Global"),
        "obs": empty_profile("OBS"),
        "discord": empty_profile("Discord"),
    },
    "active_profile": "default",
    "led_strips": {str(i):{"metric":["cpu","ram","gpu_usage","ssd_usage"][i]} for i in range(4)},
    "serial_port": "AUTO",
    "theme": "dark",
    # ── PROTOCOLE ESP32 ──────────────────────────────────────────────────────
    # Patrons texte définissant le format des trames série échangées avec
    # l'ESP32. {i} = index du bouton/potard (0-7 ou 0-3), {v} = valeur (0-100).
    # Le format par défaut reste le JSON historique pour ne rien casser, mais
    # tout est personnalisable depuis les Paramètres sans toucher au code.
    "protocol": {
        "in_press":        "{\"t\":\"press\",\"i\":{i}}",
        "in_long_press":   "{\"t\":\"long_press\",\"i\":{i}}",
        "in_double_click": "{\"t\":\"double_click\",\"i\":{i}}",
        "in_release":      "{\"t\":\"release\",\"i\":{i}}",
        "in_pot":          "{\"t\":\"pot\",\"i\":{i},\"v\":{v}}",
        "out_led":         "{\"t\":\"led\",\"s\":{i},\"v\":{v}}",
    }
}

def pattern_to_regex(pattern: str) -> "re.Pattern":
    """Convertit un patron du type 'BTN{i}:PRESS' en regex capturant {i} et {v}
    comme groupes nommés, pour parser les trames brutes reçues de l'ESP32
    quel que soit le format texte choisi par l'utilisateur (pas que du JSON)."""
    # Échappe tout le texte du patron sauf nos placeholders, qu'on remplace
    # ensuite par des groupes de capture numériques.
    escaped = re.escape(pattern)
    escaped = escaped.replace(re.escape("{i}"), r"(?P<i>-?\d+)")
    escaped = escaped.replace(re.escape("{v}"), r"(?P<v>-?\d+)")
    return re.compile("^"+escaped+"$")

def pattern_format(pattern: str, i=None, v=None) -> str:
    """Remplace {i} et {v} dans un patron de trame sortante (LED) par leurs
    valeurs réelles, pour générer la ligne exacte à envoyer à l'ESP32."""
    out = pattern
    if i is not None: out = out.replace("{i}", str(i))
    if v is not None: out = out.replace("{v}", str(v))
    return out

class ConfigManager:
    def __init__(self):
        self.data = DEFAULT_CONFIG.copy()
        self.load()

    def load(self):
        if CONFIG_PATH.exists():
            try:
                with open(CONFIG_PATH,"r",encoding="utf-8") as f:
                    saved = json.load(f)
                    # Merge profond pour pas écraser les nouvelles clés
                    self.data.update(saved)
            except: pass

    def save(self):
        with open(CONFIG_PATH,"w",encoding="utf-8") as f:
            json.dump(self.data, f, indent=2, ensure_ascii=False)

    def active(self):
        name = self.data.get("active_profile","default")
        return self.data["profiles"].get(name, list(self.data["profiles"].values())[0])

# ── MOTEUR D'ACTIONS ─────────────────────────────────────────────────────────
class ActionEngine:
    def __init__(self, cfg: ConfigManager, broadcast_fn, plugins=None):
        self.cfg = cfg
        self.broadcast = broadcast_fn
        self.plugins = plugins

    def run(self, actions: list):
        for a in actions:
            try: self._one(a)
            except Exception as e: log.error(f"Action {a.get('type')}: {e}")

    def run_pot(self, pot_cfg: dict, val: int):
        """Applique l'action configurée sur un potard, avec la valeur 0-100 reçue."""
        action = pot_cfg.get("action","volume_system")
        try:
            if action == "volume_system":
                set_volume(val)

            elif action == "volume_app":
                set_app_volume(pot_cfg.get("app",""), val)

            elif action == "brightness":
                run_hidden(["powershell","-Command",
                    f"(Get-WmiObject -NS root/WMI -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1,{val})"],
                    creationflags=subprocess.CREATE_NO_WINDOW)

            elif action == "obs_volume":
                # Volume d'une source OBS (0-100 → -100dB..0dB approximatif)
                self._obs(pot_cfg.get("source","Mic/Aux"), val)

            elif action == "scroll":
                # Défilement proportionnel à l'écart depuis le dernier appel
                last = pot_cfg.get("_last", 50)
                delta = val - last
                pot_cfg["_last"] = val
                if delta:
                    mouse.wheel(delta/8)

            elif action == "zoom_level":
                # Ctrl + molette pour zoomer (navigateur, éditeurs...)
                last = pot_cfg.get("_last", 50)
                delta = val - last
                pot_cfg["_last"] = val
                if delta:
                    keyboard.press("ctrl"); mouse.wheel(delta/10); keyboard.release("ctrl")

            elif action == "media_seek":
                # Avance/recule la lecture média (touches fléchées)
                last = pot_cfg.get("_last", 50)
                delta = val - last
                pot_cfg["_last"] = val
                if delta > 2: keyboard.send("right")
                elif delta < -2: keyboard.send("left")

            elif action == "playback_speed":
                # Vitesse lecture VLC/YouTube ([ et ] sont les raccourcis usuels)
                last = pot_cfg.get("_last", 50)
                delta = val - last
                pot_cfg["_last"] = val
                if delta > 3: keyboard.send("shift+.")
                elif delta < -3: keyboard.send("shift+,")

            elif action == "discord_volume":
                set_app_volume("Discord", val)

            elif action == "spotify_volume":
                set_app_volume("Spotify", val)

            elif action == "game_volume":
                set_app_volume(pot_cfg.get("app",""), val)

            elif action == "mic_volume":
                set_app_volume(pot_cfg.get("app","")or "Discord", val)  # fallback simple

            elif action == "led_strip_color":
                # Envoie une teinte vers une LED ESP32 (idx fourni via config)
                strip = pot_cfg.get("strip", 0)
                self.broadcast({"type":"led_strip_set","strip":strip,"value":val})

            elif action == "custom":
                code = pot_cfg.get("script","")
                if code:
                    exec(code, {"value": val})

            elif self.plugins and action in self.plugins.actions:
                params = {k:v for k,v in pot_cfg.items() if not k.startswith("_") and k != "action"}
                self.plugins.run(action, params, value=val)

        except Exception as e:
            log.error(f"Pot action '{action}': {e}")

    def _obs(self, source, val):
        try:
            import websocket as _ws
            db = round((val/100)*100 - 100, 1)  # 0-100 → -100dB..0dB
            ws = _ws.create_connection("ws://localhost:4444", timeout=2)
            ws.send(json.dumps({"request-type":"SetVolume","message-id":"pot","source":source,"volume":db,"useDecibel":True}))
            ws.close()
        except: pass

    def _one(self, a: dict):
        # Le frontend stocke chaque action sous la forme {"type": "...", "params": {...}}.
        # Tout le dispatch ci-dessous lit ses paramètres directement sur l'objet
        # (a.get("path"), a.get("url")...), donc on aplatit "params" ici une bonne
        # fois pour toutes : sans ça, open_url/open_app/open_folder/etc. recevaient
        # toujours une chaîne vide et semblaient ne "rien faire".
        if isinstance(a.get("params"), dict):
            merged = dict(a)
            merged.update(a["params"])
            a = merged

        t = a.get("type","")

        # ── PROFILS ─────────────────────────────────────────────────────────
        if t == "switch_profile":
            name = a.get("profile","")
            if name in self.cfg.data["profiles"]:
                self.cfg.data["active_profile"] = name
                self.cfg.save()
                self.broadcast({"type":"profile_changed","profile":name})
        elif t == "next_profile":
            keys = list(self.cfg.data["profiles"].keys())
            cur  = self.cfg.data.get("active_profile","default")
            idx  = (keys.index(cur)+1) % len(keys) if cur in keys else 0
            self.cfg.data["active_profile"] = keys[idx]
            self.cfg.save()
            self.broadcast({"type":"profile_changed","profile":keys[idx]})
        elif t == "prev_profile":
            keys = list(self.cfg.data["profiles"].keys())
            cur  = self.cfg.data.get("active_profile","default")
            idx  = (keys.index(cur)-1) % len(keys) if cur in keys else 0
            self.cfg.data["active_profile"] = keys[idx]
            self.cfg.save()
            self.broadcast({"type":"profile_changed","profile":keys[idx]})

        # ── PC ──────────────────────────────────────────────────────────────
        elif t == "open_app":
            run_hidden(a.get("path",""), shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
        elif t == "close_app":
            n=a.get("name","").lower()
            [p.terminate() for p in psutil.process_iter(["name"]) if n in (p.info.get("name") or "").lower()]
        elif t == "open_folder": os.startfile(a.get("path","."))
        elif t == "open_file":   os.startfile(a.get("path",""))
        elif t == "open_url":    open_url_default(a.get("url",""))
        elif t == "lock_session": keyboard.send("win+l")
        elif t == "shutdown":    run_silent("shutdown /s /t 0")
        elif t == "restart":     run_silent("shutdown /r /t 0")
        elif t == "sleep":       run_silent("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")
        elif t == "logoff":      run_silent("shutdown /l")
        elif t == "run_command":
            run_hidden(a.get("command",""), shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
        elif t == "script_powershell":
            run_hidden(["powershell","-Command",a.get("code","")], creationflags=subprocess.CREATE_NO_WINDOW)
        elif t == "script_python":
            exec(a.get("code",""), {})
        elif t == "script_batch":
            tmp=os.path.join(os.environ.get("TEMP","."), "md_tmp.bat")
            open(tmp,"w").write(a.get("code",""))
            run_hidden(tmp, shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
        elif t == "clean_temp":
            tmp=os.environ.get("TEMP","")
            for f in glob.glob(os.path.join(tmp,"*")):
                try:
                    os.remove(f) if os.path.isfile(f) else shutil.rmtree(f,ignore_errors=True)
                except: pass
        elif t == "screenshot":  keyboard.send("win+shift+s")
        elif t == "win_minimize_all": keyboard.send("win+d")

        # ── CLAVIER / SOURIS ────────────────────────────────────────────────
        elif t == "hotkey":      keyboard.send(a.get("keys",""))
        elif t == "type_text":   keyboard.write(a.get("text",""), delay=a.get("delay",0.03))
        elif t == "key_sequence":
            for k in (a.get("sequence","")).split(","):
                keyboard.send(k.strip()); time.sleep(a.get("interval",0.05))
        elif t == "mouse_click":
            x,y=a.get("x"),a.get("y")
            if x is not None: mouse.move(x,y,absolute=True)
            mouse.click(a.get("button","left"))
        elif t == "mouse_move":  mouse.move(a.get("x",0),a.get("y",0),absolute=a.get("absolute",True))
        elif t == "mouse_scroll": mouse.wheel(a.get("delta",1))

        # ── AUDIO ───────────────────────────────────────────────────────────
        elif t == "volume_up":   set_volume(get_volume()+a.get("step",5))
        elif t == "volume_down": set_volume(get_volume()-a.get("step",5))
        elif t == "volume_set":  set_volume(int(a.get("value",50)))
        elif t == "mute_toggle": set_mute(not get_mute())
        elif t == "media_play_pause": keyboard.send("play/pause media")
        elif t == "media_next":  keyboard.send("next track")
        elif t == "media_prev":  keyboard.send("previous track")
        elif t == "media_stop":  keyboard.send("stop media")
        elif t == "brightness":
            run_hidden(["powershell","-Command",
                f"(Get-WmiObject -NS root/WMI -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1,{a.get('value',75)})"],
                creationflags=subprocess.CREATE_NO_WINDOW)

        # ── OBS ─────────────────────────────────────────────────────────────
        elif t == "obs_scene":        self._obs("SetCurrentScene",{"scene-name":a.get("scene","")})
        elif t == "obs_stream_start": self._obs("StartStreaming",{})
        elif t == "obs_stream_stop":  self._obs("StopStreaming",{})
        elif t == "obs_record_start": self._obs("StartRecording",{})
        elif t == "obs_record_stop":  self._obs("StopRecording",{})
        elif t == "obs_mute_toggle":  self._obs("ToggleMute",{"source":a.get("source","Mic/Aux")})

        # ── VISIO ───────────────────────────────────────────────────────────
        elif t == "zoom_mute":     keyboard.send("alt+a")
        elif t == "zoom_camera":   keyboard.send("alt+v")
        elif t == "zoom_hand":     keyboard.send("alt+y")
        elif t == "zoom_share":    keyboard.send("alt+s")
        elif t == "zoom_leave":    keyboard.send("alt+q")
        elif t == "teams_mute":    keyboard.send("ctrl+shift+m")
        elif t == "teams_camera":  keyboard.send("ctrl+shift+o")
        elif t == "teams_share":   keyboard.send("ctrl+shift+e")
        elif t == "meet_mute":     keyboard.send("ctrl+d")
        elif t == "meet_camera":   keyboard.send("ctrl+e")
        elif t == "discord_mute":  keyboard.send("ctrl+shift+m")
        elif t == "discord_deafen":keyboard.send("ctrl+shift+d")

        # ── DEV ─────────────────────────────────────────────────────────────
        elif t == "vscode_open":
            run_hidden(f'code "{a.get("path",".")}"', shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
        elif t == "git_pull":
            run_hidden(f'git -C "{a.get("folder",".")}" pull', shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
        elif t == "git_push":
            f=a.get("folder","."); m=a.get("message","commit")
            run_hidden(f'git -C "{f}" add -A && git -C "{f}" commit -m "{m}" && git -C "{f}" push',
                shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
        elif t == "git_commit":
            f=a.get("folder","."); m=a.get("message","commit")
            run_hidden(f'git -C "{f}" add -A && git -C "{f}" commit -m "{m}"',
                shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
        elif t == "docker_start":
            run_hidden(f'docker start {a.get("name","")}', shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
        elif t == "docker_stop":
            run_hidden(f'docker stop {a.get("name","")}', shell=True, creationflags=subprocess.CREATE_NO_WINDOW)
        elif t == "ssh":
            subprocess.Popen(f'start cmd /k ssh {a.get("user","")}@{a.get("host","")}', shell=True)

        # ── WEB / IA ────────────────────────────────────────────────────────
        elif t == "open_chatgpt":    open_url_default(a.get("url","https://chatgpt.com"))
        elif t == "google_gmail":    open_url_default("https://mail.google.com")
        elif t == "google_meet":     open_url_default("https://meet.google.com/new")
        elif t == "google_calendar": open_url_default("https://calendar.google.com")

        # ── TIMER ───────────────────────────────────────────────────────────
        elif t == "timer":
            s=int(a.get("seconds",60)); lbl=a.get("label","Timer terminé !")
            threading.Thread(target=lambda:(_timer(s,lbl)), daemon=True).start()
        elif t == "pomodoro":
            threading.Thread(target=lambda:(_timer(25*60,"🍅 Pomodoro terminé !")), daemon=True).start()

        # ── RÉSEAU / AUTO ───────────────────────────────────────────────────
        elif t == "ping":
            subprocess.Popen(f'start cmd /k ping -t {a.get("host","8.8.8.8")}', shell=True)
        elif t == "api_call":
            threading.Thread(target=self._api, args=(a,), daemon=True).start()
        elif t == "webhook":
            threading.Thread(target=self._webhook, args=(a,), daemon=True).start()
        elif t == "home_assistant":
            threading.Thread(target=self._ha, args=(a,), daemon=True).start()
        elif t == "delay":
            time.sleep(a.get("ms",500)/1000.0)
        elif t == "multi_action":
            delay=a.get("delay",0)
            def _run():
                for act in a.get("actions",[]):
                    self._one(act)
                    if delay: time.sleep(delay/1000.0)
            threading.Thread(target=_run, daemon=True).start()

        # ── PLUGINS (actions non reconnues ci-dessus) ─────────────────────────
        elif self.plugins and t in self.plugins.actions:
            params = {k:v for k,v in a.items() if k != "type"}
            self.plugins.run(t, params)

        else:
            log.warning(f"Action inconnue (ni native, ni plugin) : {t}")

    # ── Helpers ─────────────────────────────────────────────────────────────
    def _obs(self, req, data):
        try:
            import websocket
            ws=websocket.create_connection("ws://localhost:4444",timeout=3)
            ws.send(json.dumps({"request-type":req,"message-id":"md",**data}))
            ws.close()
        except: pass

    def _api(self, a):
        import urllib.request
        url=a.get("url",""); method=a.get("method","GET")
        req=urllib.request.Request(url,method=method)
        for k,v in a.get("headers",{}).items(): req.add_header(k,v)
        if a.get("body"):
            req.data=json.dumps(a["body"]).encode(); req.add_header("Content-Type","application/json")
        try:
            with urllib.request.urlopen(req,timeout=10) as r: log.info(f"API {r.status}")
        except Exception as e: log.error(f"API: {e}")

    def _webhook(self, a):
        import urllib.request
        req=urllib.request.Request(a.get("url",""),data=json.dumps(a.get("payload",{})).encode(),method="POST")
        req.add_header("Content-Type","application/json")
        try:
            with urllib.request.urlopen(req,timeout=10) as r: log.info(f"Webhook {r.status}")
        except Exception as e: log.error(f"Webhook: {e}")

    def _ha(self, a):
        import urllib.request
        url=f"{a.get('ha_url','http://homeassistant.local:8123')}/api/services/{a.get('service','').replace('.','/')}"
        req=urllib.request.Request(url,data=json.dumps({"entity_id":a.get("entity_id","")}).encode(),method="POST")
        req.add_header("Authorization",f"Bearer {a.get('token','')}")
        req.add_header("Content-Type","application/json")
        try:
            with urllib.request.urlopen(req,timeout=5) as r: log.info(f"HA {r.status}")
        except Exception as e: log.error(f"HA: {e}")

def _timer(s, lbl):
    time.sleep(s)
    try: ctypes.windll.user32.MessageBoxW(0,lbl,"MacroDeck ⏱",0x40|0x1000)
    except: pass

# ── MÉTRIQUES ────────────────────────────────────────────────────────────────
class Metrics:
    def __init__(self):
        self._net_prev=psutil.net_io_counters(); self._net_t=time.time()
        self._ohm=None
        if WMI_OK:
            try: self._ohm=wmilib.WMI(namespace="root\\OpenHardwareMonitor")
            except: pass

    def _read_nvidia_smi(self):
        """Lit usage/vram/temp/nom GPU via nvidia-smi, fenêtre TOUJOURS cachée."""
        try:
            p = run_hidden(
                ["nvidia-smi",
                 "--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu,name",
                 "--format=csv,noheader,nounits"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True
            )
            out, _ = p.communicate(timeout=2)
            line = out.strip().split("\n")[0]
            usage, mem_used, mem_total, temp, name = [x.strip() for x in line.split(",")]
            vram_pct = round(float(mem_used) / float(mem_total) * 100, 1) if float(mem_total) else 0
            return {"usage": float(usage), "vram": vram_pct, "temp": float(temp), "name": name}
        except Exception:
            return None

    def collect(self):
        m={}
        m["cpu"]       = psutil.cpu_percent(interval=None)
        m["cpu_cores"] = psutil.cpu_count(logical=True)
        freq=psutil.cpu_freq(); m["cpu_freq"]=round(freq.current,0) if freq else 0
        m["cpu_temp"]  = self._ohm_val("Temperature","CPU")

        ram=psutil.virtual_memory()
        m["ram"]         = ram.percent
        m["ram_used_gb"] = round(ram.used/1e9,1)
        m["ram_total_gb"]= round(ram.total/1e9,1)

        m["gpu_usage"]=0; m["gpu_vram"]=0; m["gpu_temp"]=None; m["gpu_name"]=""
        if GPU_OK:
            try:
                gpu = self._read_nvidia_smi()
                if gpu:
                    m["gpu_usage"]=gpu["usage"]; m["gpu_vram"]=gpu["vram"]
                    m["gpu_temp"]=gpu["temp"]; m["gpu_name"]=gpu["name"]
            except: pass

        m["ssd_usage"]=0
        try: m["ssd_usage"]=psutil.disk_usage("C:\\").percent
        except:
            try: m["ssd_usage"]=psutil.disk_usage("/").percent
            except: pass

        disks=[]
        for p in psutil.disk_partitions(all=False):
            try:
                u=psutil.disk_usage(p.mountpoint)
                disks.append({"device":p.device,"mountpoint":p.mountpoint,
                    "total_gb":round(u.total/1e9,1),"used_gb":round(u.used/1e9,1),"percent":u.percent})
            except: pass
        m["disks"]=disks

        now=time.time(); net=psutil.net_io_counters(); dt=now-self._net_t
        m["net_up"]=round((net.bytes_sent-self._net_prev.bytes_sent)/dt/1024,1) if dt>0 else 0
        m["net_down"]=round((net.bytes_recv-self._net_prev.bytes_recv)/dt/1024,1) if dt>0 else 0
        self._net_prev=net; self._net_t=now

        m["uptime"]=str(datetime.timedelta(seconds=int(time.time()-psutil.boot_time())))
        m["volume"]=get_volume(); m["muted"]=get_mute()
        n=datetime.datetime.now(); m["time"]=n.strftime("%H:%M:%S"); m["date"]=n.strftime("%d/%m/%Y")

        procs=[]
        for p in sorted(psutil.process_iter(["name","cpu_percent","memory_percent"]),
                        key=lambda x:(x.info.get("cpu_percent") or 0),reverse=True)[:8]:
            try: procs.append({"name":p.info["name"],"cpu":round(p.info.get("cpu_percent") or 0,1),"mem":round(p.info.get("memory_percent") or 0,1)})
            except: pass
        m["top_processes"]=procs
        return m

    def _ohm_val(self, typ, frag):
        if not self._ohm: return None
        try:
            for s in self._ohm.Sensor():
                if s.SensorType==typ and frag.lower() in s.Name.lower():
                    return round(s.Value,1)
        except: pass
        return None

# ── OVERLAY SYSTÈME (mini-streamdeck au changement de profil) ────────────────
# Une popup DOM dans le navigateur ne peut jamais s'afficher au-dessus
# d'autres applications Windows (jeu en plein écran, Discord, etc.). On utilise
# donc une vraie fenêtre native Tkinter, sans bordure, toujours au premier
# plan, qui tourne dans son propre thread avec sa propre boucle d'événements
# (Tk doit avoir sa boucle dédiée, on ne peut pas la mélanger avec asyncio).
class ProfileOverlayWindow:
    def __init__(self):
        self._queue = None
        self._root = None
        self._popup = None
        self._close_timer = None
        self._ready = threading.Event()
        threading.Thread(target=self._run, daemon=True).start()
        self._ready.wait(timeout=5)

    def _run(self):
        try:
            import tkinter as tk
            import queue as _queue
        except Exception as e:
            log.warning(f"Tkinter indisponible, overlay système désactivé: {e}")
            self._ready.set()
            return

        self._queue = _queue.Queue()
        try:
            root = tk.Tk()
            root.withdraw()  # pas de fenêtre principale visible, juste le moteur Tk
        except Exception as e:
            log.warning(f"Impossible d'initialiser Tkinter, overlay système désactivé: {e}")
            self._queue = None
            self._ready.set()
            return
        self._root = root
        self._ready.set()

        def poll():
            try:
                while True:
                    item = self._queue.get_nowait()
                    profile, ov_cfg = item if isinstance(item, tuple) else (item, {})
                    try:
                        self._show(profile, ov_cfg)
                    except Exception as e:
                        log.warning(f"Overlay _show: {e}")
            except _queue.Empty:
                pass
            root.after(100, poll)

        root.after(100, poll)
        root.mainloop()

    def _show(self, profile: dict, ov_cfg: dict = None):
        import tkinter as tk
        root = self._root
        if not root: return

        if getattr(self, "_close_timer", None):
            try: root.after_cancel(self._close_timer)
            except: pass
            self._close_timer = None
        if getattr(self, "_popup", None):
            try: self._popup.destroy()
            except: pass
            self._popup = None

        ov       = ov_cfg or {}
        CELL     = max(32, min(100, int(ov.get("cell_size", 56))))
        DELAY    = max(1,  min(30,  int(ov.get("delay", 3)))) * 1000
        POSITION = ov.get("position", "br")
        ALPHA    = max(0.2, min(1.0, int(ov.get("alpha", 97)) / 100))
        OV_POTS  = ov.get("pots", {})

        BG  = "#0d0e12"; CARD = "#1c1f29"; ACC = "#6366f1"
        FG  = "#f1f5f9"; FG3  = "#94a3b8"; BG3 = "#181b22"
        BG4 = "#1e212b"; BDR  = "#2a2d3a"
        PAD=10; GAP=4; COLS=4
        W = COLS*CELL + (COLS-1)*GAP + PAD*2
        H = 38 + 1 + 8 + CELL*2 + GAP + 8 + 1 + 8 + CELL + 12

        sw = root.winfo_screenwidth(); sh = root.winfo_screenheight()
        mg = 20
        if   POSITION=="br": X=sw-W-mg; Y=sh-H-60
        elif POSITION=="bl": X=mg;       Y=sh-H-60
        elif POSITION=="tr": X=sw-W-mg; Y=mg+40
        else:                 X=mg;       Y=mg+40

        win = tk.Toplevel(root)
        self._popup = win
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        try: win.attributes("-alpha", ALPHA)
        except: pass
        win.configure(bg=ACC)
        win.geometry(f"{W}x{H}+{X}+{Y}")

        main = tk.Frame(win, bg=BG)
        main.pack(padx=1, pady=1, fill="both", expand=True)
        win._imgs = []  # Evite le GC des PhotoImage

        # ── Header ────────────────────────────────────────────────────────
        hdr = tk.Frame(main, bg=BG)
        hdr.pack(fill="x", padx=PAD, pady=(7,4))
        dot = tk.Canvas(hdr, width=8, height=8, bg=BG, highlightthickness=0)
        dot.pack(side="left", pady=1)
        dot.create_oval(0,0,8,8, fill=ACC, outline="")
        tk.Label(hdr, text=profile.get("name","Profil"), fg=FG, bg=BG,
                 font=("Segoe UI",10,"bold")).pack(side="left", padx=(6,0))
        tk.Label(hdr, text="PROFIL", fg=ACC, bg=BG,
                 font=("Segoe UI",7,"bold")).pack(side="right")
        tk.Frame(main, bg=BDR, height=1).pack(fill="x")

        # ── Boutons 4×2 ───────────────────────────────────────────────────
        bf = tk.Frame(main, bg=BG)
        bf.pack(padx=PAD, pady=(8,0))
        buttons = profile.get("buttons", {})
        for i in range(8):
            b   = buttons.get(str(i), {})
            r,c = divmod(i, COLS)
            outer = tk.Frame(bf, bg=BDR)
            outer.grid(row=r, column=c, padx=GAP//2, pady=GAP//2)
            cell = tk.Frame(outer, bg=CARD, width=CELL-2, height=CELL-2)
            cell.pack(padx=1, pady=1)
            cell.pack_propagate(False)
            label = (b.get("label") or f"Btn {i+1}")[:9]
            img_data = b.get("iconImage","")
            placed = False
            if img_data and img_data.startswith("data:image"):
                try:
                    import io, base64 as b64
                    raw = b64.b64decode(img_data[img_data.index(",")+1:])
                    sz  = max(CELL-16, 18)
                    tkimg = None
                    try:
                        from PIL import Image as PI, ImageTk
                        tkimg = ImageTk.PhotoImage(PI.open(io.BytesIO(raw)).resize((sz,sz), PI.LANCZOS))
                    except ImportError:
                        # Fallback tk natif — fonctionne uniquement PNG
                        try:
                            tkimg = tk.PhotoImage(data=b64.b64encode(raw).decode())
                            # subsample si trop grand
                            tw, th = tkimg.width(), tkimg.height()
                            if tw > sz or th > sz:
                                f = max(tw//sz, th//sz, 1)
                                if f > 1: tkimg = tkimg.subsample(f, f)
                        except Exception as e2:
                            log.warning(f"Overlay tk.PhotoImage btn{i}: {e2}")
                    if tkimg:
                        win._imgs.append(tkimg)
                        tk.Label(cell, image=tkimg, bg=CARD).place(relx=.5, rely=.36, anchor="center")
                        tk.Label(cell, text=label, fg=FG3, bg=CARD,
                                 font=("Segoe UI",6)).place(relx=.5, rely=.82, anchor="center")
                        placed = True
                except Exception as e:
                    log.warning(f"Overlay img btn{i}: {e}")
            if not placed:
                icon = b.get("icon","") or "●"
                tk.Label(cell, text=icon,  fg=FG,  bg=CARD,
                         font=("Segoe UI Emoji",15)).place(relx=.5, rely=.36, anchor="center")
                tk.Label(cell, text=label, fg=FG3, bg=CARD,
                         font=("Segoe UI",6)).place(relx=.5, rely=.78, anchor="center")

        tk.Frame(main, bg=BDR, height=1).pack(fill="x", padx=PAD, pady=(8,0))

        # ── Potards ───────────────────────────────────────────────────────
        POT_LABELS = {
            "volume_system":"Vol.sys","volume_app":"Vol.app","brightness":"Luminosité",
            "scroll":"Scroll","zoom_level":"Zoom","media_seek":"Seek",
            "discord_volume":"Discord","spotify_volume":"Spotify","game_volume":"Jeu",
            "mic_volume":"Micro","obs_volume":"OBS","led_strip_color":"LED","custom":"Custom",
        }
        pf = tk.Frame(main, bg=BG)
        pf.pack(padx=PAD, pady=(8,12))
        pots = profile.get("pots", {})
        for i in range(COLS):
            p       = pots.get(str(i), {})
            pot_ov  = OV_POTS.get(str(i), OV_POTS.get(i, {}))
            name    = (p.get("name") or f"Pot {i+1}")[:8]
            action  = POT_LABELS.get(p.get("action",""), (p.get("action","") or "—")[:8])
            custom_text = pot_ov.get("text","") if isinstance(pot_ov, dict) else ""
            img_data    = pot_ov.get("image","") if isinstance(pot_ov, dict) else ""

            outer = tk.Frame(pf, bg=BDR)
            outer.grid(row=0, column=i, padx=GAP//2)
            cell = tk.Frame(outer, bg=BG3, width=CELL-2, height=CELL-2)
            cell.pack(padx=1, pady=1)
            cell.pack_propagate(False)

            placed = False
            if img_data and img_data.startswith("data:image"):
                try:
                    import io, base64 as b64
                    raw = b64.b64decode(img_data[img_data.index(",")+1:])
                    sz  = max(CELL-22, 14)
                    tkimg = None
                    try:
                        from PIL import Image as PI, ImageTk
                        tkimg = ImageTk.PhotoImage(PI.open(io.BytesIO(raw)).resize((sz,sz), PI.LANCZOS))
                    except ImportError:
                        try:
                            tkimg = tk.PhotoImage(data=b64.b64encode(raw).decode())
                            tw, th = tkimg.width(), tkimg.height()
                            if tw > sz or th > sz:
                                f = max(tw//sz, th//sz, 1)
                                if f > 1: tkimg = tkimg.subsample(f, f)
                        except Exception as e2:
                            log.warning(f"Overlay tk.PhotoImage pot{i}: {e2}")
                    if tkimg:
                        win._imgs.append(tkimg)
                        tk.Label(cell, image=tkimg, bg=BG3).place(relx=.5, rely=.28, anchor="center")
                        lbl = custom_text or name
                        tk.Label(cell, text=lbl, fg=FG, bg=BG3,
                                 font=("Segoe UI",5,"bold")).place(relx=.5, rely=.80, anchor="center")
                        placed = True
                except Exception as e:
                    log.warning(f"Overlay img pot{i}: {e}")
            if not placed:
                cv = tk.Canvas(cell, width=26, height=26, bg=BG3, highlightthickness=0)
                cv.place(relx=.5, rely=.26, anchor="center")
                cv.create_oval(1,1,25,25, outline=FG3, width=1,   fill=BG4)
                cv.create_oval(5,5,21,21, outline=ACC, width=1.5, fill=BG3)
                cv.create_oval(10,10,16,16, fill=ACC, outline="")
                disp = custom_text or name
                tk.Label(cell, text=disp,   fg=FG,  bg=BG3,
                         font=("Segoe UI",6,"bold")).place(relx=.5, rely=.65, anchor="center")
                if not custom_text:
                    tk.Label(cell, text=action, fg=FG3, bg=BG3,
                             font=("Segoe UI",5)).place(relx=.5, rely=.83, anchor="center")

        def _close():
            self._close_timer = None
            try:
                if win.winfo_exists(): win.destroy()
            except: pass
            if self._popup is win: self._popup = None
        self._close_timer = root.after(DELAY, _close)

    def show_profile(self, profile: dict, ov_cfg: dict = None):
        """Affiche l'overlay pour ce profil. Thread-safe."""
        if self._queue is not None:
            try: self._queue.put_nowait((profile, ov_cfg or {}))
            except Exception as e: log.warning(f"Overlay queue: {e}")

# ── APP WATCHER ──────────────────────────────────────────────────────────────
class AppWatcher:
    def __init__(self, on_change):
        self._cb=on_change; self._cur=""; threading.Thread(target=self._loop,daemon=True).start()

    def _loop(self):
        while True:
            app=""
            if WIN32_OK:
                try:
                    hwnd=win32gui.GetForegroundWindow()
                    _,pid=win32process.GetWindowThreadProcessId(hwnd)
                    app=psutil.Process(pid).name().lower().replace(".exe","")
                except: pass
            if app!=self._cur:
                self._cur=app; self._cb(app)
            time.sleep(0.5)

# ── SERIAL ────────────────────────────────────────────────────────────────────
class Transport:
    def __init__(self, on_msg):
        self._cb=on_msg; self.ser=None; self.port_name=None

    def start(self, port="AUTO"):
        if not SERIAL_OK: return
        if port=="AUTO":
            ports=serial.tools.list_ports.comports()
            port=next((p.device for p in ports if any(k in p.description.upper() for k in ["CP210","CH340","USB","FTDI"])),
                      ports[0].device if ports else None)
        if not port: return
        try:
            self.ser=serial.Serial(port,115200,timeout=0.1)
            self.port_name=port
            threading.Thread(target=self._loop,daemon=True).start()
        except Exception as e:
            log.error(f"Serial: {e}")
            self.port_name=None

    def is_connected(self) -> bool:
        return bool(self.ser and self.ser.is_open)

    def _loop(self):
        while self.ser and self.ser.is_open:
            try:
                line=self.ser.readline().decode("utf-8",errors="ignore").strip()
                if line: self._cb(line)
            except:
                time.sleep(1)
        self.port_name=None

    def send(self, obj):
        if self.ser and self.ser.is_open:
            try: self.ser.write((json.dumps(obj,separators=(",",":"))+"\n").encode())
            except: pass

    def send_raw(self, line: str):
        """Envoie une ligne texte brute déjà formatée (utilisé pour le
        protocole LED configurable, qui peut être du JSON ou tout autre
        format texte selon ce que le firmware ESP32 attend)."""
        if self.ser and self.ser.is_open:
            try: self.ser.write((line+"\n").encode())
            except: pass

# ── MACRODECK CORE ────────────────────────────────────────────────────────────
# ── PLUGINS ────────────────────────────────────────────────────────────────────
# Système de plugins sans recompilation : chaque plugin est un simple fichier
# .json posé dans le dossier "plugins" (à côté de l'exe ou du .py). Il déclare
# une ou plusieurs actions custom, exécutées via une commande shell/PowerShell
# avec des variables substituées (ex: {value} pour la valeur d'un potard).
#
# Exemple de plugin "plugins/discord_bot.json" :
# {
#   "name": "Discord Bot Webhook",
#   "version": "1.0",
#   "actions": [
#     {
#       "type": "plugin_discord_say",
#       "name": "Discord : Envoyer message webhook",
#       "icon": "💬",
#       "desc": "Poste un message via un webhook Discord",
#       "params": [
#         {"key":"webhook_url","lbl":"URL Webhook","ph":"https://discord.com/api/webhooks/..."},
#         {"key":"message","lbl":"Message","ph":"Bonjour !"}
#       ],
#       "run": {
#         "kind": "http",
#         "method": "POST",
#         "url": "{webhook_url}",
#         "body": {"content": "{message}"}
#       }
#     }
#   ]
# }
#
# "run.kind" peut être :
#   "shell"      → exécute "command" (fenêtre toujours cachée)
#   "powershell" → exécute "command" via powershell -Command (fenêtre cachée)
#   "http"       → fait une requête HTTP (url/method/body, utile pour webhooks/API locales)
# Les valeurs {param_key} et {value} (pour les potards) sont substituées dans
# command / url / body avant exécution.

class PluginManager:
    def __init__(self):
        self.plugins = []     # liste de manifestes chargés
        self.actions = {}     # type -> définition d'action (pour le catalogue GUI)
        self.reload()

    def _plugins_dir(self) -> Path:
        base = Path(_app_dir_persistent())
        d = base / "plugins"
        d.mkdir(exist_ok=True)
        return d

    def reload(self):
        self.plugins = []
        self.actions = {}
        d = self._plugins_dir()
        for f in sorted(d.glob("*.json")):
            try:
                with open(f, "r", encoding="utf-8") as fp:
                    manifest = json.load(fp)
                manifest["_file"] = f.name
                self.plugins.append(manifest)
                for act in manifest.get("actions", []):
                    t = act.get("type")
                    if t:
                        self.actions[t] = act
                log.info(f"Plugin chargé: {manifest.get('name', f.name)}")
            except Exception as e:
                log.error(f"Plugin invalide {f.name}: {e}")

    def catalog(self) -> list:
        """Retourne le catalogue d'actions exposées par tous les plugins, pour la GUI."""
        out = []
        for p in self.plugins:
            for act in p.get("actions", []):
                out.append({
                    "cat": "Plugins",
                    "icon": act.get("icon","🧩"),
                    "type": act.get("type"),
                    "name": act.get("name","Action plugin"),
                    "desc": act.get("desc", p.get("name","")),
                    "params": act.get("params", []),
                    "plugin": p.get("name", p.get("_file","")),
                })
        return out

    def run(self, action_type: str, params: dict, value=None):
        act = self.actions.get(action_type)
        if not act: return
        run_def = act.get("run", {})
        kind = run_def.get("kind", "shell")

        def _sub(s):
            if not isinstance(s, str): return s
            out = s
            for k, v in params.items():
                out = out.replace("{"+k+"}", str(v))
            if value is not None:
                out = out.replace("{value}", str(value))
            return out

        try:
            if kind == "shell":
                cmd = _sub(run_def.get("command",""))
                if cmd: run_silent(cmd)

            elif kind == "powershell":
                cmd = _sub(run_def.get("command",""))
                if cmd:
                    run_hidden(["powershell","-NoProfile","-Command", cmd],
                        creationflags=subprocess.CREATE_NO_WINDOW)

            elif kind == "http":
                import urllib.request
                url = _sub(run_def.get("url",""))
                method = run_def.get("method","GET")
                body = run_def.get("body")
                req = urllib.request.Request(url, method=method)
                if body:
                    body_sub = json.loads(_sub(json.dumps(body)))
                    req.data = json.dumps(body_sub).encode()
                    req.add_header("Content-Type","application/json")
                with urllib.request.urlopen(req, timeout=10) as r:
                    log.info(f"Plugin HTTP {url} → {r.status}")
        except Exception as e:
            log.error(f"Plugin run '{action_type}': {e}")

class MacroDeck:
    def __init__(self):
        self.cfg       = ConfigManager()
        self.ws_clients= set()
        self.plugins   = PluginManager()
        self.engine    = ActionEngine(self.cfg, self._broadcast, self.plugins)
        self.metrics   = Metrics()
        self.transport = Transport(self._on_esp32)
        self.watcher   = AppWatcher(self._on_app)
        self.overlay   = ProfileOverlayWindow()

    def _broadcast(self, obj):
        # Déclenche l'overlay système au-dessus de toutes les fenêtres pour
        # CHAQUE changement de profil, peu importe la source (bouton dédié,
        # détection auto par app active, sélection manuelle dans la GUI...) :
        # on centralise ici plutôt que de dupliquer l'appel à 5 endroits.
        if obj.get("type") == "profile_changed":
            key = obj.get("profile")
            profile = self.cfg.data.get("profiles", {}).get(key)
            if profile and self.overlay:
                ov_cfg = self.cfg.data.get("overlay", {})
                self.overlay.show_profile(profile, ov_cfg)
        raw=json.dumps(obj)
        for ws in list(self.ws_clients):
            asyncio.ensure_future(ws.send(raw))

    def _on_app(self, app):
        for name,profile in self.cfg.data["profiles"].items():
            trigger=(profile.get("app_trigger") or "").lower()
            if trigger and trigger in app.lower():
                if self.cfg.data.get("active_profile")!=name:
                    self.cfg.data["active_profile"]=name
                    self._broadcast({"type":"profile_changed","profile":name})
                return

    def _on_esp32(self, raw: str):
        raw = raw.strip()
        if not raw: return
        proto = self.cfg.data.get("protocol", {})

        # Essaie chaque patron configuré dans l'ordre, et route vers le bon
        # traitement dès qu'un patron correspond à la ligne brute reçue.
        # Garde aussi un fallback JSON historique pour ne jamais casser un
        # firmware déjà en place tant que l'utilisateur n'a rien reconfiguré.
        for ev_key, ev_name in [("in_press","press"),("in_long_press","long_press"),
                                  ("in_double_click","double_click"),("in_release","release")]:
            pat = proto.get(ev_key, "")
            if not pat: continue
            try:
                m = pattern_to_regex(pat).match(raw)
            except Exception as e:
                log.error(f"Patron '{ev_key}' invalide: {e}"); continue
            if m:
                idx = int(m.group("i"))
                if ev_name == "release":
                    self._broadcast({"type":"button_event","button":idx,"event":"release"})
                    return
                profile=self.cfg.active()
                actions=profile["buttons"].get(str(idx),{}).get(ev_name,[])
                threading.Thread(target=self.engine.run,args=(actions,),daemon=True).start()
                self._broadcast({"type":"button_event","button":idx,"event":ev_name})
                return

        pat = proto.get("in_pot","")
        if pat:
            try:
                m = pattern_to_regex(pat).match(raw)
                if m:
                    idx=int(m.group("i")); val=int(m.group("v"))
                    pot_cfg=self.cfg.active()["pots"].get(str(idx),{})
                    self.engine.run_pot(pot_cfg, val)
                    self._broadcast({"type":"pot_event","pot":idx,"value":val})
                    return
            except Exception as e:
                log.error(f"Patron 'in_pot' invalide: {e}")

        # Fallback JSON historique (rétrocompatibilité avec un firmware déjà
        # flashé sur l'ancien protocole, même si "protocol" a été modifié).
        try:
            msg=json.loads(raw)
        except: return
        t=msg.get("t")
        if t in ("press","long_press","double_click"):
            idx=msg.get("i",0)
            profile=self.cfg.active()
            actions=profile["buttons"].get(str(idx),{}).get(t,[])
            threading.Thread(target=self.engine.run,args=(actions,),daemon=True).start()
            self._broadcast({"type":"button_event","button":idx,"event":t})
        elif t=="pot":
            idx=msg.get("i",0); val=msg.get("v",0)
            pot_cfg=self.cfg.active()["pots"].get(str(idx),{})
            self.engine.run_pot(pot_cfg, val)
            self._broadcast({"type":"pot_event","pot":idx,"value":val})

    async def _metrics_loop(self):
        self.metrics.collect()  # init réseau
        while True:
            await asyncio.sleep(1)
            m=self.metrics.collect()
            self._broadcast({"type":"metrics","data":m})
            # Envoi LED → ESP32, au format défini dans protocol.out_led
            # (ex: '{"t":"led","s":0,"v":42}' ou tout autre format texte
            # comme 'LED0:42%' selon ce que le firmware attend).
            keys=["cpu","ram","gpu_usage","ssd_usage"]
            out_pat = self.cfg.data.get("protocol",{}).get("out_led", '{"t":"led","s":{i},"v":{v}}')
            for i in range(4):
                k=self.cfg.data.get("led_strips",{}).get(str(i),{}).get("metric",keys[i])
                v=min(100,int(float(m.get(k,0) or 0)))
                self.transport.send_raw(pattern_format(out_pat, i=i, v=v))

    async def _ws_handler(self, ws: WebSocketServerProtocol):
        self.ws_clients.add(ws)
        # Envoyer la config complète à la connexion
        await ws.send(json.dumps({"type":"config","data":self.cfg.data}))
        try:
            async for raw in ws:
                await self._handle(json.loads(raw), ws)
        except: pass
        finally: self.ws_clients.discard(ws)

    async def _handle(self, msg, ws):
        t=msg.get("type")
        if t=="save_config":
            self.cfg.data=msg["data"]
            self.cfg.save()
            await ws.send(json.dumps({"type":"config_saved"}))

        elif t=="create_profile":
            name=msg.get("key",""); label=msg.get("label","Nouveau profil")
            if name and name not in self.cfg.data["profiles"]:
                self.cfg.data["profiles"][name]=empty_profile(label)
                self.cfg.save()
                self._broadcast({"type":"config","data":self.cfg.data})

        elif t=="delete_profile":
            name=msg.get("key","")
            if name in self.cfg.data["profiles"] and name!="default":
                del self.cfg.data["profiles"][name]
                if self.cfg.data.get("active_profile")==name:
                    self.cfg.data["active_profile"]="default"
                self.cfg.save()
                self._broadcast({"type":"config","data":self.cfg.data})

        elif t=="rename_profile":
            name=msg.get("key",""); label=msg.get("label","")
            if name in self.cfg.data["profiles"] and label:
                self.cfg.data["profiles"][name]["name"]=label
                self.cfg.save()
                self._broadcast({"type":"config","data":self.cfg.data})

        elif t=="set_profile":
            name=msg.get("profile","")
            if name in self.cfg.data["profiles"]:
                self.cfg.data["active_profile"]=name
                self.cfg.save()
                self._broadcast({"type":"profile_changed","profile":name})

        elif t=="test_action":
            threading.Thread(target=self.engine.run,args=(msg.get("actions",[]),),daemon=True).start()

        elif t=="get_ports":
            ports=[]
            if SERIAL_OK: ports=[p.device for p in serial.tools.list_ports.comports()]
            await ws.send(json.dumps({"type":"ports","data":ports}))

        elif t=="get_apps":
            # Le scan complet (menu démarrer + registre + Program Files) peut
            # prendre plusieurs secondes : on l'exécute dans un thread pour ne
            # jamais geler la boucle asyncio (sinon plus rien ne répond pendant
            # le scan, donnant l'impression que le picker ne s'affiche jamais).
            async def _do_get_apps():
                loop = asyncio.get_event_loop()
                try:
                    apps = await loop.run_in_executor(None, get_installed_apps)
                except Exception as e:
                    log.error(f"get_apps: {e}")
                    apps = []
                await ws.send(json.dumps({"type":"apps","data":apps}))
            asyncio.ensure_future(_do_get_apps())

        elif t=="get_plugins":
            await ws.send(json.dumps({"type":"plugins","data":self.plugins.catalog(),
                "meta":[{"name":p.get("name"),"file":p.get("_file"),"version":p.get("version","")} for p in self.plugins.plugins]}))

        elif t=="reload_plugins":
            self.plugins.reload()
            await ws.send(json.dumps({"type":"plugins","data":self.plugins.catalog(),
                "meta":[{"name":p.get("name"),"file":p.get("_file"),"version":p.get("version","")} for p in self.plugins.plugins]}))
            self._broadcast({"type":"toast","message":f"✓ {len(self.plugins.plugins)} plugin(s) chargé(s)"})

        elif t=="get_processes":
            # Processus en cours (pour "fermer une application", choisir une fenêtre...)
            procs=[]
            seen=set()
            for p in psutil.process_iter(["name"]):
                try:
                    n=p.info["name"]
                    if n and n.lower() not in seen:
                        seen.add(n.lower()); procs.append(n)
                except: pass
            await ws.send(json.dumps({"type":"processes","data":sorted(procs)}))

        elif t=="get_audio_sessions":
            # Applications ayant une session audio active (pour volume_app)
            sessions=list_audio_sessions()
            await ws.send(json.dumps({"type":"audio_sessions","data":sessions}))

        elif t=="pick_folder":
            # Ouvre le sélecteur de dossier natif Windows dans un thread (non bloquant
            # pour la boucle asyncio) et renvoie le chemin choisi une fois sélectionné.
            field = msg.get("field","")
            async def _do_pick_folder():
                loop = asyncio.get_event_loop()
                path = await loop.run_in_executor(None, self._native_picker, True)
                await ws.send(json.dumps({"type":"picked_path","field":field,"path":path}))
            asyncio.ensure_future(_do_pick_folder())

        elif t=="pick_file":
            field = msg.get("field","")
            async def _do_pick_file():
                loop = asyncio.get_event_loop()
                path = await loop.run_in_executor(None, self._native_picker, False)
                await ws.send(json.dumps({"type":"picked_path","field":field,"path":path}))
            asyncio.ensure_future(_do_pick_file())

        elif t=="connect_serial":
            self.transport.start(msg.get("port","AUTO"))
            await ws.send(json.dumps({"type":"serial_status",
                "connected":self.transport.is_connected(), "port":self.transport.port_name}))

        elif t=="get_serial_status":
            await ws.send(json.dumps({"type":"serial_status",
                "connected":self.transport.is_connected(), "port":self.transport.port_name}))

        elif t=="save_protocol":
            # Valide chaque patron avant de sauvegarder : un regex invalide
            # ne doit jamais planter le parsing des trames série en live.
            proto = msg.get("protocol", {})
            errors = {}
            for key, pat in proto.items():
                try: pattern_to_regex(pat) if key.startswith("in_") else pattern_format(pat, i=0, v=0)
                except Exception as e: errors[key] = str(e)
            if errors:
                await ws.send(json.dumps({"type":"protocol_saved","ok":False,"errors":errors}))
            else:
                self.cfg.data["protocol"] = proto
                self.cfg.save()
                await ws.send(json.dumps({"type":"protocol_saved","ok":True}))

        elif t=="test_protocol_pattern":
            # Permet de tester un patron entrant en simulant une trame brute
            # sans avoir besoin de l'ESP32 physiquement connecté.
            pattern = msg.get("pattern","")
            sample = msg.get("sample","")
            try:
                m = pattern_to_regex(pattern).match(sample.strip())
                if m:
                    await ws.send(json.dumps({"type":"protocol_test_result","ok":True,
                        "groups":{k:v for k,v in m.groupdict().items()}}))
                else:
                    await ws.send(json.dumps({"type":"protocol_test_result","ok":False,"error":"La trame d'exemple ne correspond pas au patron"}))
            except Exception as e:
                await ws.send(json.dumps({"type":"protocol_test_result","ok":False,"error":str(e)}))

        elif t=="simulate_esp32_frame":
            raw = msg.get("raw","").strip()
            if not raw:
                await ws.send(json.dumps({"type":"protocol_test_result","ok":False,"error":"Trame vide"}))
                return
            # On teste d'abord quel patron correspond (pour l'affichage),
            # puis on exécute vraiment la trame comme si elle venait de l'ESP32.
            proto = self.cfg.data.get("protocol", {})
            matched_event = None
            matched_groups = {}
            for ev_key, ev_name in [("in_press","press"),("in_long_press","long_press"),
                                     ("in_double_click","double_click"),("in_release","release"),
                                     ("in_pot","pot")]:
                pat = proto.get(ev_key,"")
                if not pat: continue
                try:
                    m2 = pattern_to_regex(pat).match(raw)
                    if m2:
                        matched_event = ev_name
                        matched_groups = m2.groupdict()
                        break
                except: continue
            # Tente aussi le fallback JSON
            if not matched_event:
                try:
                    parsed = json.loads(raw)
                    t2 = parsed.get("t","")
                    if t2 in ("press","long_press","double_click","release","pot"):
                        matched_event = t2
                        matched_groups = {k:v for k,v in parsed.items() if k!="t"}
                except: pass
            # Exécute la trame
            self._on_esp32(raw)
            if matched_event:
                await ws.send(json.dumps({"type":"protocol_test_result","ok":True,
                    "event":matched_event,"groups":matched_groups,
                    "message":f"Trame reconnue comme '{matched_event}' et exécutée ✓"}))
            else:
                await ws.send(json.dumps({"type":"protocol_test_result","ok":False,
                    "error":"Aucun patron ne correspond à cette trame (trame envoyée quand même)"}))

        elif t=="open_update_url":
            download_url = msg.get("download_url","")
            async def _do_download(dl_url):
                import urllib.request, urllib.error, tempfile
                GITHUB_REPO = "tuturpotter-web/Imperium"
                try:
                    # Récupère l'URL de téléchargement si pas fournie
                    if not dl_url:
                        api = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
                        req = urllib.request.Request(api, headers={"User-Agent":"Imperium-updater"})
                        with urllib.request.urlopen(req, timeout=8) as r:
                            release = json.loads(r.read())
                        assets = release.get("assets", [])
                        exe_asset = next((a for a in assets if a["name"].endswith(".exe")), None)
                        if not exe_asset:
                            await ws.send(json.dumps({"type":"update_progress","error":"Aucun .exe trouvé dans la release GitHub"}))
                            return
                        dl_url = exe_asset["browser_download_url"]
                        filename = exe_asset["name"]
                        total_size = exe_asset.get("size", 0)
                    else:
                        filename = dl_url.split("/")[-1]
                        total_size = 0

                    await ws.send(json.dumps({"type":"update_progress","status":"downloading","pct":0,"filename":filename}))

                    tmp_path = os.path.join(tempfile.gettempdir(), filename)
                    downloaded = 0
                    last_pct = -1

                    def _report(block_num, block_size, file_size):
                        nonlocal downloaded, last_pct
                        downloaded = block_num * block_size
                        pct = min(100, int(downloaded / file_size * 100)) if file_size > 0 else 0
                        if pct != last_pct:
                            last_pct = pct
                            asyncio.ensure_future(ws.send(json.dumps({"type":"update_progress","status":"downloading","pct":pct,"filename":filename})))

                    loop = asyncio.get_event_loop()
                    await loop.run_in_executor(None, lambda: urllib.request.urlretrieve(dl_url, tmp_path, _report))

                    await ws.send(json.dumps({"type":"update_progress","status":"launching","pct":100,"filename":filename}))
                    await asyncio.sleep(0.5)

                    # Lance le setup et quitte
                    subprocess.Popen([tmp_path], creationflags=subprocess.CREATE_NO_WINDOW)
                    await asyncio.sleep(1)
                    os._exit(0)

                except Exception as e:
                    await ws.send(json.dumps({"type":"update_progress","error":str(e)}))
            asyncio.ensure_future(_do_download(download_url))

        elif t=="check_update":
            async def _do_check_update():
                import urllib.request, urllib.error
                GITHUB_REPO = "tuturpotter-web/Imperium"
                try:
                    url = f"https://api.github.com/repos/{GITHUB_REPO}/releases/latest"
                    req = urllib.request.Request(url, headers={"User-Agent": "Imperium-updater"})
                    with urllib.request.urlopen(req, timeout=8) as r:
                        data = json.loads(r.read())
                    latest = data.get("tag_name", "").lstrip("v")
                    current = APP_VERSION
                    assets = data.get("assets", [])
                    exe_asset = next((a for a in assets if a["name"].endswith(".exe")), None)
                    download_url = exe_asset["browser_download_url"] if exe_asset else ""
                    if latest and latest != current:
                        await ws.send(json.dumps({"type":"update_available","current":current,"latest":latest,"download_url":download_url}))
                    else:
                        await ws.send(json.dumps({"type":"toast","message":f"✓ Imperium {current} est à jour"}))
                except urllib.error.URLError as e:
                    await ws.send(json.dumps({"type":"toast","message":f"⚠ Vérification MAJ impossible : {e.reason}"}))
                except Exception as e:
                    await ws.send(json.dumps({"type":"toast","message":f"⚠ Vérification MAJ : {e}"}))
            asyncio.ensure_future(_do_check_update())

        elif t=="preview_overlay":
            key = self.cfg.data.get("active_profile","default")
            profile = self.cfg.data.get("profiles",{}).get(key)
            if profile and self.overlay:
                ov_cfg = self.cfg.data.get("overlay",{})
                self.overlay.show_profile(profile, ov_cfg)

        elif t=="update_button":
            pid=msg.get("profile","default"); bid=str(msg.get("button",0))
            data=msg.get("data",{})
            if pid in self.cfg.data["profiles"]:
                self.cfg.data["profiles"][pid]["buttons"][bid]=data
                self.cfg.save()

    def _native_picker(self, folder: bool) -> str:
        """Ouvre une boîte de dialogue Windows native pour choisir un dossier ou fichier.
        Tourne dans un script PowerShell séparé (bloquant) pour ne jamais geler
        la boucle asyncio principale, fenêtre cachée par défaut sauf le dialog lui-même."""
        try:
            if folder:
                ps = (
                    "Add-Type -AssemblyName System.Windows.Forms;"
                    "$f=New-Object System.Windows.Forms.FolderBrowserDialog;"
                    "if($f.ShowDialog() -eq 'OK'){Write-Output $f.SelectedPath}"
                )
            else:
                ps = (
                    "Add-Type -AssemblyName System.Windows.Forms;"
                    "$f=New-Object System.Windows.Forms.OpenFileDialog;"
                    "if($f.ShowDialog() -eq 'OK'){Write-Output $f.FileName}"
                )
            result = subprocess.run(
                ["powershell","-NoProfile","-Command", ps],
                capture_output=True, text=True, timeout=120
            )
            return result.stdout.strip()
        except Exception as e:
            log.error(f"native_picker: {e}")
            return ""

    async def run(self):
        self.transport.start(self.cfg.data.get("serial_port","AUTO"))
        # max_size augmenté : la config peut contenir des icônes de boutons
        # personnalisées encodées en base64 (plusieurs dizaines de Ko chacune,
        # potentiellement nombreuses avec plusieurs profils/pages). La limite
        # par défaut de la lib (1 Mo) suffirait en usage normal mais on prend
        # de la marge pour ne jamais subir de déconnexion silencieuse.
        srv=await websockets.serve(self._ws_handler,"localhost",WS_PORT,max_size=10*1024*1024)
        await asyncio.gather(self._metrics_loop(), srv.wait_closed())

# ── HTTP SERVER ───────────────────────────────────────────────────────────────
def _app_dir() -> str:
    """Retourne le dossier où se trouve gui.html, que l'app tourne en .py
    ou compilée en .exe (PyInstaller --onefile extrait dans sys._MEIPASS,
    un dossier TEMPORAIRE recréé à chaque lancement — bon pour des
    ressources en lecture seule comme gui.html, mauvais pour tout ce qui
    doit persister, voir _app_dir_persistent() ci-dessous)."""
    if getattr(sys, "frozen", False):
        return getattr(sys, "_MEIPASS", os.path.dirname(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))

def _app_dir_persistent() -> str:
    """Retourne le dossier RÉEL et STABLE à côté de l'exécutable (ou du .py),
    par opposition à _app_dir() qui pointe vers un dossier temporaire en
    mode .exe compilé. À utiliser pour tout ce qui doit survivre entre deux
    lancements : dossier plugins/, etc. (la config elle-même est dans
    ~/.macrodeck/, donc indépendante de l'emplacement de l'exe)."""
    if getattr(sys, "frozen", False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def _http_server():
    import http.server, socketserver
    web_dir = _app_dir()
    class Q(http.server.SimpleHTTPRequestHandler):
        def __init__(self, *args, **kwargs):
            super().__init__(*args, directory=web_dir, **kwargs)
        def log_message(self, *a): pass
        def end_headers(self):
            # Désactive complètement le cache navigateur pour gui.html :
            # sans ça, le navigateur sert l'ancien fichier mis en cache
            # même après un rebuild/redéploiement, ce qui donnait l'impression
            # que les corrections CSS n'étaient pas appliquées.
            self.send_header("Cache-Control", "no-store, no-cache, must-revalidate, max-age=0")
            self.send_header("Pragma", "no-cache")
            self.send_header("Expires", "0")
            super().end_headers()
    try:
        with socketserver.TCPServer(("127.0.0.1", HTTP_PORT), Q) as h:
            h.serve_forever()
    except OSError:
        pass

# ── VÉRIF INSTANCE UNIQUE ────────────────────────────────────────────────────
def _port_is_free(port: int) -> bool:
    import socket as _socket
    s = _socket.socket(_socket.AF_INET, _socket.SOCK_STREAM)
    try:
        s.bind(("127.0.0.1", port))
        s.close()
        return True
    except OSError:
        s.close()
        return False

def _notify_already_running():
    """Affiche une popup native si une instance tourne déjà (sinon échec silencieux car console cachée)."""
    if sys.platform == "win32":
        try:
            ctypes.windll.user32.MessageBoxW(
                0,
                "MacroDeck est déjà lancé en arrière-plan.\n\n"
                "Ouvre http://127.0.0.1:8766/gui.html dans ton navigateur pour l'utiliser.\n\n"
                "Si ce n'est pas le cas, ouvre le Gestionnaire des tâches et termine\n"
                "le processus MacroDeck.exe existant avant de relancer.",
                "MacroDeck — déjà en cours",
                0x40 | 0x1000  # MB_ICONINFORMATION | MB_TOPMOST
            )
        except: pass

def _open_browser_when_ready():
    """Attend que le serveur HTTP réponde puis ouvre le navigateur sur la GUI."""
    import urllib.request
    url = f"http://127.0.0.1:{HTTP_PORT}/gui.html"
    for _ in range(40):  # ~10s max
        try:
            urllib.request.urlopen(url, timeout=0.5)
            webbrowser.open(url)
            return
        except Exception:
            time.sleep(0.25)
    # Dernier recours : on ouvre quand même, au cas où le check ait raté
    webbrowser.open(url)

# ── MAIN ──────────────────────────────────────────────────────────────────────
if __name__=="__main__":
    if not _port_is_free(WS_PORT):
        _notify_already_running()
        sys.exit(0)

    threading.Thread(target=_http_server, daemon=True).start()
    threading.Thread(target=_open_browser_when_ready, daemon=True).start()

    deck=MacroDeck()
    try:
        asyncio.run(deck.run())
    except KeyboardInterrupt:
        pass
    except OSError as e:
        # Sécurité supplémentaire si le port se libère/reprend entre la vérif et le bind réel
        _notify_already_running()
        sys.exit(0)
    finally:
        # Sauvegarde finale en sécurité : chaque modification est déjà écrite
        # sur disque immédiatement (cfg.save() est synchrone), mais on
        # s'assure ici qu'aucun état en mémoire ne se perd à la fermeture
        # (Ctrl+C, fermeture du processus, arrêt système...).
        try: deck.cfg.save()
        except: pass
