"""
Imperium Backend
- Console cachée (SW_HIDE + FreeConsole)
- Fenêtre native via pywebview (Edge WebView2)
- Profils indépendants avec création/suppression/renommage
- WebSocket :8765 — HTTP :8766
"""
APP_VERSION = "dev"
import sys, os, ctypes, threading, time, asyncio, json, subprocess, re
import webbrowser, shutil, glob, logging, datetime
from pathlib import Path

# ── CACHER CONSOLE ──────────────────────────────────────────────────────────
if sys.platform == "win32":
    try:
        hwnd = ctypes.windll.kernel32.GetConsoleWindow()
        if hwnd: ctypes.windll.user32.ShowWindow(hwnd, 0)
        ctypes.windll.kernel32.FreeConsole()
    except: pass

CREATE_NO_WINDOW = 0x08000000
_SI = None
if sys.platform == "win32":
    _SI = subprocess.STARTUPINFO()
    _SI.dwFlags |= subprocess.STARTF_USESHOWWINDOW
    _SI.wShowWindow = 0

def run_hidden(cmd, **kwargs):
    kwargs.setdefault("creationflags", CREATE_NO_WINDOW)
    kwargs.setdefault("startupinfo", _SI)
    return subprocess.Popen(cmd, **kwargs)

def run_silent(cmd: str):
    return run_hidden(cmd, shell=True)

def open_url_default(url: str):
    """Ouvre une URL dans le vrai navigateur par défaut Windows (registre UserChoice)."""
    if not url: return
    if sys.platform == "win32":
        try:
            import winreg
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\http\UserChoice")
            prog_id, _ = winreg.QueryValueEx(key, "ProgId"); winreg.CloseKey(key)
            cmd_key = winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, fr"{prog_id}\shell\open\command")
            cmd, _ = winreg.QueryValueEx(cmd_key, ""); winreg.CloseKey(cmd_key)
            run_hidden(cmd.replace("%1", url) if "%1" in cmd else f'{cmd} "{url}"', shell=True)
            return
        except: pass
        try: os.startfile(url); return
        except: pass
    try: webbrowser.open(url)
    except: pass

import psutil, keyboard, mouse, websockets
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

GPU_OK = shutil.which("nvidia-smi") is not None

try:
    import wmi as wmilib; WMI_OK = True
except: WMI_OK = False

try:
    import serial, serial.tools.list_ports; SERIAL_OK = True
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
        return d.Activate(IAudioEndpointVolume._iid_, CLSCTX_ALL, None).QueryInterface(IAudioEndpointVolume)
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
    if not PYCAW_OK or not process_name: return
    try:
        from pycaw.pycaw import ISimpleAudioVolume
        target = process_name.lower().replace(".exe","")
        for session in AudioUtilities.GetAllSessions():
            if session.Process and session.Process.name().lower().replace(".exe","") == target:
                session._ctl.QueryInterface(ISimpleAudioVolume).SetMasterVolume(max(0,min(100,level))/100.0, None)
    except Exception as e: log.error(f"set_app_volume: {e}")

def list_audio_sessions():
    out, seen = [], set()
    if not PYCAW_OK: return out
    try:
        for s in AudioUtilities.GetAllSessions():
            if s.Process:
                n = s.Process.name()
                if n.lower() not in seen: seen.add(n.lower()); out.append(n)
    except: pass
    return sorted(out)

# ── APPS ─────────────────────────────────────────────────────────────────────
def get_installed_apps():
    apps, seen = [], set()
    def add(name, path, kind):
        k = name.lower().strip()
        if k and k not in seen: seen.add(k); apps.append({"name":name,"path":path,"type":kind})

    for base in [os.path.join(os.environ.get("APPDATA",""),"Microsoft","Windows","Start Menu","Programs"),
                 r"C:\ProgramData\Microsoft\Windows\Start Menu\Programs"]:
        try:
            for r,_,files in os.walk(base):
                for f in files:
                    if f.endswith(".lnk"): add(f[:-4], os.path.join(r,f), "lnk")
        except: pass

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
    except: pass

    for base in [r"C:\Program Files",r"C:\Program Files (x86)",
                 os.path.join(os.environ.get("LOCALAPPDATA",""),"Programs")]:
        try:
            for d in os.listdir(base):
                try:
                    full=os.path.join(base,d)
                    if os.path.isdir(full):
                        for f in os.listdir(full):
                            if f.endswith(".exe"): add(f[:-4],os.path.join(full,f),"exe")
                except: pass
        except: pass

    apps.sort(key=lambda x:x["name"].lower())
    return apps

# ── CONFIG ───────────────────────────────────────────────────────────────────
def empty_profile(name):
    return {
        "name": name, "app_trigger": "",
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
    "serial_port": "AUTO", "theme": "dark",
    "protocol": {
        "in_press": "btn{i}:on", "in_long_press": "", "in_double_click": "",
        "in_release": "btn{i}:off", "in_pot": "pot{i}:{v}", "out_led": "led{i}:{v}",
    },
    "serial_port2": "", "baud_rate": 115200, "baud_rate2": 115200
}

def pattern_to_regex(pattern: str) -> "re.Pattern":
    e = re.escape(pattern)
    e = e.replace(re.escape("{i}"), r"(?P<i>-?\d+)")
    e = e.replace(re.escape("{v}"), r"(?P<v>-?\d+)")
    return re.compile("^"+e+"$")

def pattern_format(pattern: str, i=None, v=None) -> str:
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
                    self.data.update(json.load(f))
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
        self.cfg = cfg; self.broadcast = broadcast_fn; self.plugins = plugins

    def run(self, actions: list):
        for a in actions:
            try: self._one(a)
            except Exception as e: log.error(f"Action {a.get('type')}: {e}")

    def run_pot(self, pot_cfg: dict, val: int):
        action = pot_cfg.get("action","volume_system")
        try:
            if   action == "volume_system":  set_volume(val)
            elif action == "volume_app":     set_app_volume(pot_cfg.get("app",""), val)
            elif action == "discord_volume": set_app_volume("Discord", val)
            elif action == "spotify_volume": set_app_volume("Spotify", val)
            elif action == "game_volume":    set_app_volume(pot_cfg.get("app",""), val)
            elif action == "mic_volume":     set_app_volume(pot_cfg.get("app","") or "Discord", val)
            elif action == "brightness":
                run_hidden(["powershell","-Command",
                    f"(Get-WmiObject -NS root/WMI -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1,{val})"],
                    creationflags=CREATE_NO_WINDOW)
            elif action == "obs_volume":
                self._obs_vol(pot_cfg.get("source","Mic/Aux"), val)
            elif action in ("scroll","zoom_level","media_seek","playback_speed"):
                last = pot_cfg.get("_last", 50); delta = val - last; pot_cfg["_last"] = val
                if not delta: return
                if   action == "scroll":        mouse.wheel(delta/8)
                elif action == "zoom_level":    keyboard.press("ctrl"); mouse.wheel(delta/10); keyboard.release("ctrl")
                elif action == "media_seek":
                    if delta > 2: keyboard.send("right")
                    elif delta < -2: keyboard.send("left")
                elif action == "playback_speed":
                    if delta > 3: keyboard.send("shift+.")
                    elif delta < -3: keyboard.send("shift+,")
            elif action == "led_strip_color":
                self.broadcast({"type":"led_strip_set","strip":pot_cfg.get("strip",0),"value":val})
            elif action == "custom":
                code = pot_cfg.get("script","")
                if code: exec(code, {"value": val})
            elif self.plugins and action in self.plugins.actions:
                params = {k:v for k,v in pot_cfg.items() if not k.startswith("_") and k != "action"}
                self.plugins.run(action, params, value=val)
        except Exception as e: log.error(f"Pot action '{action}': {e}")

    def _obs_vol(self, source, val):
        try:
            import websocket as _ws
            db = round((val/100)*100 - 100, 1)
            ws = _ws.create_connection("ws://localhost:4444", timeout=2)
            ws.send(json.dumps({"request-type":"SetVolume","message-id":"pot","source":source,"volume":db,"useDecibel":True}))
            ws.close()
        except: pass

    def _one(self, a: dict):
        if isinstance(a.get("params"), dict):
            merged = dict(a); merged.update(a["params"]); a = merged
        t = a.get("type","")

        # Profils
        if t in ("switch_profile","next_profile","prev_profile"):
            keys = list(self.cfg.data["profiles"].keys())
            cur  = self.cfg.data.get("active_profile","default")
            if   t == "switch_profile": name = a.get("profile","")
            elif t == "next_profile":   name = keys[(keys.index(cur)+1) % len(keys)] if cur in keys else keys[0]
            else:                       name = keys[(keys.index(cur)-1) % len(keys)] if cur in keys else keys[0]
            if name in self.cfg.data["profiles"]:
                self.cfg.data["active_profile"] = name
                self.cfg.save()
                self.broadcast({"type":"profile_changed","profile":name})

        # PC
        elif t == "open_app":     run_hidden(a.get("path",""), shell=True, creationflags=CREATE_NO_WINDOW)
        elif t == "close_app":
            n=a.get("name","").lower()
            [p.terminate() for p in psutil.process_iter(["name"]) if n in (p.info.get("name") or "").lower()]
        elif t == "open_folder":  os.startfile(a.get("path","."))
        elif t == "open_file":    os.startfile(a.get("path",""))
        elif t == "open_url":     open_url_default(a.get("url",""))
        elif t == "lock_session": keyboard.send("win+l")
        elif t == "shutdown":     run_silent("shutdown /s /t 0")
        elif t == "restart":      run_silent("shutdown /r /t 0")
        elif t == "sleep":        run_silent("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")
        elif t == "logoff":       run_silent("shutdown /l")
        elif t == "run_command":  run_hidden(a.get("command",""), shell=True, creationflags=CREATE_NO_WINDOW)
        elif t == "script_powershell": run_hidden(["powershell","-Command",a.get("code","")], creationflags=CREATE_NO_WINDOW)
        elif t == "script_python":     exec(a.get("code",""), {})
        elif t == "script_batch":
            tmp=os.path.join(os.environ.get("TEMP","."), "md_tmp.bat")
            open(tmp,"w").write(a.get("code","")); run_hidden(tmp, shell=True, creationflags=CREATE_NO_WINDOW)
        elif t == "clean_temp":
            for f in glob.glob(os.path.join(os.environ.get("TEMP",""),"*")):
                try: os.remove(f) if os.path.isfile(f) else shutil.rmtree(f,ignore_errors=True)
                except: pass
        elif t == "screenshot":       keyboard.send("win+shift+s")
        elif t == "win_minimize_all": keyboard.send("win+d")

        # Clavier / souris
        elif t == "hotkey":       keyboard.send(a.get("keys",""))
        elif t == "type_text":    keyboard.write(a.get("text",""), delay=a.get("delay",0.03))
        elif t == "key_sequence":
            for k in a.get("sequence","").split(","):
                keyboard.send(k.strip()); time.sleep(a.get("interval",0.05))
        elif t == "mouse_click":
            x,y=a.get("x"),a.get("y")
            if x is not None: mouse.move(x,y,absolute=True)
            mouse.click(a.get("button","left"))
        elif t == "mouse_move":   mouse.move(a.get("x",0),a.get("y",0),absolute=a.get("absolute",True))
        elif t == "mouse_scroll": mouse.wheel(a.get("delta",1))

        # Audio
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
                creationflags=CREATE_NO_WINDOW)

        # OBS
        elif t == "obs_scene":        self._obs("SetCurrentScene",{"scene-name":a.get("scene","")})
        elif t == "obs_stream_start": self._obs("StartStreaming",{})
        elif t == "obs_stream_stop":  self._obs("StopStreaming",{})
        elif t == "obs_record_start": self._obs("StartRecording",{})
        elif t == "obs_record_stop":  self._obs("StopRecording",{})
        elif t == "obs_mute_toggle":  self._obs("ToggleMute",{"source":a.get("source","Mic/Aux")})

        # Visio
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

        # Dev
        elif t == "vscode_open":  run_hidden(f'code "{a.get("path",".")}"', shell=True, creationflags=CREATE_NO_WINDOW)
        elif t == "git_pull":     run_hidden(f'git -C "{a.get("folder",".")}" pull', shell=True, creationflags=CREATE_NO_WINDOW)
        elif t == "git_push":
            f=a.get("folder","."); m=a.get("message","commit")
            run_hidden(f'git -C "{f}" add -A && git -C "{f}" commit -m "{m}" && git -C "{f}" push', shell=True, creationflags=CREATE_NO_WINDOW)
        elif t == "git_commit":
            f=a.get("folder","."); m=a.get("message","commit")
            run_hidden(f'git -C "{f}" add -A && git -C "{f}" commit -m "{m}"', shell=True, creationflags=CREATE_NO_WINDOW)
        elif t == "docker_start": run_hidden(f'docker start {a.get("name","")}', shell=True, creationflags=CREATE_NO_WINDOW)
        elif t == "docker_stop":  run_hidden(f'docker stop {a.get("name","")}', shell=True, creationflags=CREATE_NO_WINDOW)
        elif t == "ssh":          subprocess.Popen(f'start cmd /k ssh {a.get("user","")}@{a.get("host","")}', shell=True)

        # Web
        elif t == "open_chatgpt":    open_url_default("https://chatgpt.com")
        elif t == "google_gmail":    open_url_default("https://mail.google.com")
        elif t == "google_meet":     open_url_default("https://meet.google.com/new")
        elif t == "google_calendar": open_url_default("https://calendar.google.com")

        # Timer
        elif t == "timer":
            s=int(a.get("seconds",60)); lbl=a.get("label","Timer terminé !")
            threading.Thread(target=lambda:(_timer(s,lbl)), daemon=True).start()
        elif t == "pomodoro":
            threading.Thread(target=lambda:(_timer(25*60,"🍅 Pomodoro terminé !")), daemon=True).start()

        # Réseau / Auto
        elif t == "ping":    subprocess.Popen(f'start cmd /k ping -t {a.get("host","8.8.8.8")}', shell=True)
        elif t == "api_call":       threading.Thread(target=self._api, args=(a,), daemon=True).start()
        elif t == "webhook":        threading.Thread(target=self._webhook, args=(a,), daemon=True).start()
        elif t == "home_assistant": threading.Thread(target=self._ha, args=(a,), daemon=True).start()
        elif t == "delay":          time.sleep(a.get("ms",500)/1000.0)
        elif t == "multi_action":
            delay=a.get("delay",0)
            def _run():
                for act in a.get("actions",[]): self._one(act); time.sleep(delay/1000.0) if delay else None
            threading.Thread(target=_run, daemon=True).start()

        elif self.plugins and t in self.plugins.actions:
            self.plugins.run(t, {k:v for k,v in a.items() if k != "type"})
        else:
            log.warning(f"Action inconnue : {t}")

    def _obs(self, req, data):
        try:
            import websocket
            ws=websocket.create_connection("ws://localhost:4444",timeout=3)
            ws.send(json.dumps({"request-type":req,"message-id":"md",**data})); ws.close()
        except: pass

    def _api(self, a):
        import urllib.request
        req=urllib.request.Request(a.get("url",""),method=a.get("method","GET"))
        for k,v in a.get("headers",{}).items(): req.add_header(k,v)
        if a.get("body"): req.data=json.dumps(a["body"]).encode(); req.add_header("Content-Type","application/json")
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
        req.add_header("Authorization",f"Bearer {a.get('token','')}"); req.add_header("Content-Type","application/json")
        try:
            with urllib.request.urlopen(req,timeout=5) as r: log.info(f"HA {r.status}")
        except Exception as e: log.error(f"HA: {e}")

def _timer(s, lbl):
    time.sleep(s)
    try: ctypes.windll.user32.MessageBoxW(0,lbl,"Imperium ⏱",0x40|0x1000)
    except: pass

# ── MÉTRIQUES ────────────────────────────────────────────────────────────────
class Metrics:
    def __init__(self):
        self._net_prev=psutil.net_io_counters(); self._net_t=time.time()
        self._ohm=None; self._thermal_wmi=None
        if WMI_OK:
            try: self._ohm=wmilib.WMI(namespace="root\\OpenHardwareMonitor")
            except: pass
            try: self._thermal_wmi=wmilib.WMI(namespace="root\\wmi")
            except: pass

    def _read_nvidia_smi(self):
        try:
            p = run_hidden(["nvidia-smi","--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu,name",
                "--format=csv,noheader,nounits"], stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)
            out, _ = p.communicate(timeout=2)
            usage, mem_used, mem_total, temp, name = [x.strip() for x in out.strip().split("\n")[0].split(",")]
            return {"usage":float(usage),"vram":round(float(mem_used)/float(mem_total)*100,1) if float(mem_total) else 0,
                    "temp":float(temp),"name":name}
        except: return None

    def collect(self):
        m = {}
        m["cpu"] = psutil.cpu_percent(interval=None)
        m["cpu_cores"] = psutil.cpu_count(logical=True)
        freq=psutil.cpu_freq(); m["cpu_freq"]=round(freq.current,0) if freq else 0
        m["cpu_temp"] = self._ohm_val("Temperature","CPU")

        ram=psutil.virtual_memory()
        m["ram"]=ram.percent; m["ram_used_gb"]=round(ram.used/1e9,1); m["ram_total_gb"]=round(ram.total/1e9,1)

        m["gpu_usage"]=0; m["gpu_vram"]=0; m["gpu_temp"]=None; m["gpu_name"]=""
        if GPU_OK:
            gpu=self._read_nvidia_smi()
            if gpu: m["gpu_usage"]=gpu["usage"]; m["gpu_vram"]=gpu["vram"]; m["gpu_temp"]=gpu["temp"]; m["gpu_name"]=gpu["name"]

        m["ssd_usage"]=0
        try: m["ssd_usage"]=psutil.disk_usage("C:\\").percent
        except:
            try: m["ssd_usage"]=psutil.disk_usage("/").percent
            except: pass

        m["disks"]=[]
        for p in psutil.disk_partitions(all=False):
            try:
                u=psutil.disk_usage(p.mountpoint)
                m["disks"].append({"device":p.device,"mountpoint":p.mountpoint,
                    "total_gb":round(u.total/1e9,1),"used_gb":round(u.used/1e9,1),"percent":u.percent})
            except: pass

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
        if self._ohm:
            try:
                for s in self._ohm.Sensor():
                    if s.SensorType==typ and frag.lower() in s.Name.lower(): return round(s.Value,1)
            except: pass
        if typ == "Temperature" and self._thermal_wmi:
            try:
                for zone in self._thermal_wmi.MSAcpi_ThermalZoneTemperature():
                    k=zone.CurrentTemperature
                    if k and k > 0: return round(k/10.0-273.15,1)
            except: pass
        return None

# ── OVERLAY (mini-streamdeck Tkinter, au-dessus de tout) ─────────────────────
class ProfileOverlayWindow:
    def __init__(self):
        self._queue = None; self._root = None; self._popup = None; self._close_timer = None
        self._ready = threading.Event()
        threading.Thread(target=self._run, daemon=True).start()
        self._ready.wait(timeout=5)

    def _run(self):
        try:
            import tkinter as tk, queue as _queue
        except Exception as e:
            log.warning(f"Tkinter indisponible: {e}"); self._ready.set(); return
        self._queue = _queue.Queue()
        try:
            root = tk.Tk(); root.withdraw()
        except Exception as e:
            log.warning(f"Tkinter init échoué: {e}"); self._queue=None; self._ready.set(); return
        self._root = root; self._ready.set()

        def poll():
            try:
                while True:
                    item = self._queue.get_nowait()
                    profile, ov_cfg = item if isinstance(item, tuple) else (item, {})
                    try: self._show(profile, ov_cfg)
                    except Exception as e: log.warning(f"Overlay show: {e}")
            except _queue.Empty: pass
            root.after(30, poll)

        root.after(30, poll); root.mainloop()

    def _show(self, profile: dict, ov_cfg: dict = None):
        import tkinter as tk
        root = self._root
        if not root: return
        if self._close_timer:
            try: root.after_cancel(self._close_timer)
            except: pass
            self._close_timer = None
        if self._popup:
            try: self._popup.destroy()
            except: pass
            self._popup = None

        ov       = ov_cfg or {}
        CELL     = max(32, min(100, int(ov.get("cell_size", 56))))
        DELAY    = max(1,  min(30,  int(ov.get("delay", 3)))) * 1000
        POSITION = ov.get("position", "br")
        ALPHA    = max(0.2, min(1.0, int(ov.get("alpha", 97)) / 100))
        OV_POTS  = ov.get("pots", {})
        
        ACC="#6366f1"; FG="#f1f5f9"; BG="#0d0e12"; CARD="#1c1f29"; FG3="#94a3b8"; BG3="#181b22"; BG4="#1e212b"; BDR="#2a2d3a"
        PAD=10; GAP=4; COLS=4
        W = COLS*CELL + (COLS-1)*GAP + PAD*2
        H = 38 + 1 + 8 + CELL*2 + GAP + 8 + 1 + 8 + CELL + 12
        sw=root.winfo_screenwidth(); sh=root.winfo_screenheight(); mg=20
        X,Y = {"br":(sw-W-mg,sh-H-60),"bl":(mg,sh-H-60),"tr":(sw-W-mg,mg+40)}.get(POSITION,(mg,mg+40))

        win = tk.Toplevel(root); self._popup = win
        win.overrideredirect(True); win.attributes("-topmost",True)
        try: win.attributes("-alpha",ALPHA)
        except: pass
        win.configure(bg=ACC); win.geometry(f"{W}x{H}+{X}+{Y}"); win.update_idletasks()

        main = tk.Frame(win,bg=BG); main.pack(padx=1,pady=1,fill="both",expand=True)
        win._imgs = []

        # Header
        hdr=tk.Frame(main,bg=BG); hdr.pack(fill="x",padx=PAD,pady=(7,4))
        dot=tk.Canvas(hdr,width=8,height=8,bg=BG,highlightthickness=0); dot.pack(side="left",pady=1)
        dot.create_oval(0,0,8,8,fill=ACC,outline="")
        tk.Label(hdr,text=profile.get("name","Profil"),fg=FG,bg=BG,font=("Segoe UI",10,"bold")).pack(side="left",padx=(6,0))
        tk.Label(hdr,text="PROFIL",fg=ACC,bg=BG,font=("Segoe UI",7,"bold")).pack(side="right")
        tk.Frame(main,bg=BDR,height=1).pack(fill="x")

        def _tk_img(data_url, sz):
            """Charge une data:image/* en PhotoImage Tkinter, avec PIL si dispo."""
            import io, base64 as b64
            raw = b64.b64decode(data_url[data_url.index(",")+1:])
            try:
                from PIL import Image as PI, ImageTk
                return ImageTk.PhotoImage(PI.open(io.BytesIO(raw)).resize((sz,sz), PI.LANCZOS))
            except ImportError: pass
            try:
                tkimg = tk.PhotoImage(data=b64.b64encode(raw).decode())
                tw,th = tkimg.width(),tkimg.height()
                if tw>sz or th>sz:
                    f=max(tw//sz,th//sz,1)
                    if f>1: tkimg=tkimg.subsample(f,f)
                return tkimg
            except: return None

        # Boutons 4×2
        bf=tk.Frame(main,bg=BG); bf.pack(padx=PAD,pady=(8,0))
        buttons=profile.get("buttons",{})
        for i in range(8):
            b=buttons.get(str(i),{}); r,c=divmod(i,COLS)
            outer=tk.Frame(bf,bg=BDR); outer.grid(row=r,column=c,padx=GAP//2,pady=GAP//2)
            cell=tk.Frame(outer,bg=CARD,width=CELL-2,height=CELL-2); cell.pack(padx=1,pady=1); cell.pack_propagate(False)
            label=(b.get("label") or f"Btn {i+1}")[:9]; img_data=b.get("iconImage",""); placed=False
            if img_data and img_data.startswith("data:image"):
                try:
                    tkimg=_tk_img(img_data,max(CELL-16,18))
                    if tkimg:
                        win._imgs.append(tkimg)
                        tk.Label(cell,image=tkimg,bg=CARD).place(relx=.5,rely=.36,anchor="center")
                        tk.Label(cell,text=label,fg=FG3,bg=CARD,font=("Segoe UI",6)).place(relx=.5,rely=.82,anchor="center")
                        placed=True
                except Exception as e: log.warning(f"Overlay btn{i} img: {e}")
            if not placed:
                tk.Label(cell,text=b.get("icon","") or "●",fg=FG,bg=CARD,font=("Segoe UI Emoji",15)).place(relx=.5,rely=.36,anchor="center")
                tk.Label(cell,text=label,fg=FG3,bg=CARD,font=("Segoe UI",6)).place(relx=.5,rely=.78,anchor="center")

        tk.Frame(main,bg=BDR,height=1).pack(fill="x",padx=PAD,pady=(8,0))

        # Potards
        POT_LABELS={"volume_system":"Vol.sys","volume_app":"Vol.app","brightness":"Luminosité",
            "scroll":"Scroll","zoom_level":"Zoom","media_seek":"Seek","discord_volume":"Discord",
            "spotify_volume":"Spotify","game_volume":"Jeu","mic_volume":"Micro","obs_volume":"OBS",
            "led_strip_color":"LED","custom":"Custom"}
        pf=tk.Frame(main,bg=BG); pf.pack(padx=PAD,pady=(8,12))
        pots=profile.get("pots",{})
        for i in range(COLS):
            p=pots.get(str(i),{})
            pot_ov=OV_POTS.get(str(i),OV_POTS.get(i,{})) if isinstance(OV_POTS,dict) else {}
            name=(p.get("name") or f"Pot {i+1}")[:8]
            action=POT_LABELS.get(p.get("action",""), (p.get("action","") or "—")[:8])
            custom_text=pot_ov.get("text","") if isinstance(pot_ov,dict) else ""
            img_data=p.get("image","") or (pot_ov.get("image","") if isinstance(pot_ov,dict) else "")

            outer=tk.Frame(pf,bg=BDR); outer.grid(row=0,column=i,padx=GAP//2)
            cell=tk.Frame(outer,bg=BG3,width=CELL-2,height=CELL-2); cell.pack(padx=1,pady=1); cell.pack_propagate(False)
            placed=False
            if img_data and img_data.startswith("data:image"):
                try:
                    tkimg=_tk_img(img_data,max(CELL-22,14))
                    if tkimg:
                        win._imgs.append(tkimg)
                        tk.Label(cell,image=tkimg,bg=BG3).place(relx=.5,rely=.28,anchor="center")
                        tk.Label(cell,text=custom_text or name,fg=FG,bg=BG3,font=("Segoe UI",5,"bold")).place(relx=.5,rely=.80,anchor="center")
                        placed=True
                except Exception as e: log.warning(f"Overlay pot{i} img: {e}")
            if not placed:
                cv=tk.Canvas(cell,width=26,height=26,bg=BG3,highlightthickness=0); cv.place(relx=.5,rely=.26,anchor="center")
                cv.create_oval(1,1,25,25,outline=FG3,width=1,fill=BG4)
                cv.create_oval(5,5,21,21,outline=ACC,width=1.5,fill=BG3)
                cv.create_oval(10,10,16,16,fill=ACC,outline="")
                tk.Label(cell,text=custom_text or name,fg=FG,bg=BG3,font=("Segoe UI",6,"bold")).place(relx=.5,rely=.65,anchor="center")
                if not custom_text:
                    tk.Label(cell,text=action,fg=FG3,bg=BG3,font=("Segoe UI",5)).place(relx=.5,rely=.83,anchor="center")

        def _close():
            self._close_timer=None
            try:
                if win.winfo_exists(): win.destroy()
            except: pass
            if self._popup is win: self._popup=None
        self._close_timer=root.after(DELAY,_close)
        win.update_idletasks()

    def show_profile(self, profile: dict, ov_cfg: dict = None):
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
            if app!=self._cur: self._cur=app; self._cb(app)
            time.sleep(0.5)

# ── SERIAL ────────────────────────────────────────────────────────────────────
class Transport:
    LONG_MS=400; DOUBLE_MS=300

    def __init__(self, on_msg):
        self._cb=on_msg; self._slots=[None,None]; self._port_names=[None,None]; self._btn_state={}

    def start(self, port="AUTO", baud=115200, slot=0):
        if not SERIAL_OK: return
        old=self._slots[slot]
        if old:
            try: old.close()
            except: pass
            self._slots[slot]=None; self._port_names[slot]=None
        if port=="AUTO":
            ports=serial.tools.list_ports.comports()
            other=self._port_names[1-slot]
            candidates=[p.device for p in ports if any(k in p.description.upper() for k in ["CP210","CH340","USB","FTDI"]) and p.device!=other]
            if not candidates: candidates=[p.device for p in ports if p.device!=other]
            port=candidates[0] if candidates else None
        if not port: return
        try:
            ser=serial.Serial(port,baud,timeout=0.1)
            self._slots[slot]=ser; self._port_names[slot]=port
            threading.Thread(target=self._loop,args=(ser,slot),daemon=True).start()
            log.info(f"Serial slot {slot}: {port} @ {baud}")
        except Exception as e: log.error(f"Serial slot {slot}: {e}")

    def is_connected(self, slot=0):
        s=self._slots[slot]; return bool(s and s.is_open)

    def _loop(self, ser, slot):
        while ser and ser.is_open:
            try:
                line=ser.readline().decode("utf-8",errors="ignore").strip()
                if line: self._cb(line,slot)
            except: time.sleep(1)
        if self._slots[slot] is ser:
            self._slots[slot]=None; self._port_names[slot]=None

    def _handle_timing(self, btn_idx, event, on_msg_fn):
        now=time.time(); st=self._btn_state.setdefault(btn_idx,{})
        if event=="on":
            last_on=st.get("last_on"); st["on_t"]=now; st["last_on"]=now
            if last_on and (now-last_on)*1000 < self.DOUBLE_MS:
                st["last_on"]=None; on_msg_fn(btn_idx,"double_click")
        elif event=="off":
            on_t=st.get("on_t")
            if on_t is None: return
            st["on_t"]=None
            on_msg_fn(btn_idx,"long_press" if (now-on_t)*1000>=self.LONG_MS else "press")

    def send_raw(self, line: str, slot=0):
        ser=self._slots[slot]
        if ser and ser.is_open:
            try: ser.write((line+"\n").encode())
            except: pass

# ── PLUGINS ────────────────────────────────────────────────────────────────────
class PluginManager:
    def __init__(self):
        self.plugins=[]; self.actions={}; self.reload()

    def _plugins_dir(self):
        d=Path(_app_dir_persistent())/"plugins"; d.mkdir(exist_ok=True); return d

    def reload(self):
        self.plugins=[]; self.actions={}
        for f in sorted(self._plugins_dir().glob("*.json")):
            try:
                with open(f,"r",encoding="utf-8") as fp: manifest=json.load(fp)
                manifest["_file"]=f.name; self.plugins.append(manifest)
                for act in manifest.get("actions",[]):
                    if act.get("type"): self.actions[act["type"]]=act
                log.info(f"Plugin: {manifest.get('name',f.name)}")
            except Exception as e: log.error(f"Plugin {f.name}: {e}")

    def catalog(self):
        out=[]
        for p in self.plugins:
            for act in p.get("actions",[]):
                out.append({"cat":"Plugins","icon":act.get("icon","🧩"),"type":act.get("type"),
                    "name":act.get("name","Action plugin"),"desc":act.get("desc",p.get("name","")),
                    "params":act.get("params",[]),"plugin":p.get("name",p.get("_file",""))})
        return out

    def run(self, action_type, params, value=None):
        act=self.actions.get(action_type)
        if not act: return
        run_def=act.get("run",{}); kind=run_def.get("kind","shell")
        def _sub(s):
            if not isinstance(s,str): return s
            for k,v in params.items(): s=s.replace("{"+k+"}",str(v))
            if value is not None: s=s.replace("{value}",str(value))
            return s
        try:
            if kind=="shell":
                cmd=_sub(run_def.get("command",""))
                if cmd: run_silent(cmd)
            elif kind=="powershell":
                cmd=_sub(run_def.get("command",""))
                if cmd: run_hidden(["powershell","-NoProfile","-Command",cmd],creationflags=CREATE_NO_WINDOW)
            elif kind=="http":
                import urllib.request
                url=_sub(run_def.get("url","")); body=run_def.get("body")
                req=urllib.request.Request(url,method=run_def.get("method","GET"))
                if body:
                    req.data=json.dumps(json.loads(_sub(json.dumps(body)))).encode()
                    req.add_header("Content-Type","application/json")
                with urllib.request.urlopen(req,timeout=10) as r: log.info(f"Plugin HTTP {r.status}")
        except Exception as e: log.error(f"Plugin '{action_type}': {e}")

# ── MACRODECK CORE ────────────────────────────────────────────────────────────
class MacroDeck:
    def __init__(self):
        self.cfg=ConfigManager(); self.ws_clients=set()
        self.plugins=PluginManager()
        self.engine=ActionEngine(self.cfg,self._broadcast,self.plugins)
        self.metrics=Metrics(); self.transport=Transport(self._on_esp32)
        self.watcher=AppWatcher(self._on_app); self.overlay=ProfileOverlayWindow()

    def _broadcast(self, obj):
        if obj.get("type")=="profile_changed":
            key=obj.get("profile")
            profile=self.cfg.data.get("profiles",{}).get(key)
            if profile and self.overlay:
                self.overlay.show_profile(profile,self.cfg.data.get("overlay",{}))
        raw=json.dumps(obj)
        for ws in list(self.ws_clients):
            asyncio.ensure_future(ws.send(raw))

    def _on_app(self, app):
        for name,profile in self.cfg.data["profiles"].items():
            trigger=(profile.get("app_trigger") or "").lower()
            if trigger and trigger in app.lower() and self.cfg.data.get("active_profile")!=name:
                self.cfg.data["active_profile"]=name
                self._broadcast({"type":"profile_changed","profile":name})
                return

    def _on_esp32(self, raw: str, slot: int = 0):
        raw=raw.strip()
        if not raw: return
        proto=self.cfg.data.get("protocol",{})

        pat_pot=proto.get("in_pot","")
        if pat_pot:
            try:
                m=pattern_to_regex(pat_pot).match(raw)
                if m:
                    idx=int(m.group("i")); val=int(m.group("v"))
                    self.engine.run_pot(self.cfg.active()["pots"].get(str(idx),{}),val)
                    self._broadcast({"type":"pot_event","pot":idx,"value":val}); return
            except Exception as e: log.error(f"in_pot: {e}")

        pat_on=proto.get("in_press","btn{i}:on"); pat_off=proto.get("in_release","btn{i}:off")
        def _dispatch(idx,ev):
            actions=self.cfg.active()["buttons"].get(str(idx),{}).get(ev,[])
            if actions: threading.Thread(target=self.engine.run,args=(actions,),daemon=True).start()
            self._broadcast({"type":"button_event","button":idx,"event":ev})

        if pat_on:
            try:
                m=pattern_to_regex(pat_on).match(raw)
                if m: self.transport._handle_timing(int(m.group("i")),"on",_dispatch); return
            except Exception as e: log.error(f"in_press: {e}")
        if pat_off:
            try:
                m=pattern_to_regex(pat_off).match(raw)
                if m:
                    self.transport._handle_timing(int(m.group("i")),"off",_dispatch)
                    self._broadcast({"type":"button_event","button":int(m.group("i")),"event":"release"}); return
            except Exception as e: log.error(f"in_release: {e}")

        for ev_key,ev_name in [("in_long_press","long_press"),("in_double_click","double_click")]:
            pat=proto.get(ev_key,"")
            if not pat: continue
            try:
                m=pattern_to_regex(pat).match(raw)
                if m: _dispatch(int(m.group("i")),ev_name); return
            except Exception as e: log.error(f"{ev_key}: {e}")

        # Fallback JSON rétrocompat
        try:
            msg=json.loads(raw); t=msg.get("t")
            if t in ("press","long_press","double_click"):
                idx=msg.get("i",0)
                actions=self.cfg.active()["buttons"].get(str(idx),{}).get(t,[])
                threading.Thread(target=self.engine.run,args=(actions,),daemon=True).start()
                self._broadcast({"type":"button_event","button":idx,"event":t})
            elif t=="pot":
                idx=msg.get("i",0); val=msg.get("v",0)
                self.engine.run_pot(self.cfg.active()["pots"].get(str(idx),{}),val)
                self._broadcast({"type":"pot_event","pot":idx,"value":val})
        except: pass

    async def _metrics_loop(self):
        self.metrics.collect()
        while True:
            await asyncio.sleep(1)
            m=self.metrics.collect(); self._broadcast({"type":"metrics","data":m})
            keys=["cpu","ram","gpu_usage","ssd_usage"]
            out_pat=self.cfg.data.get("protocol",{}).get("out_led",'{"t":"led","s":{i},"v":{v}}')
            for i in range(4):
                k=self.cfg.data.get("led_strips",{}).get(str(i),{}).get("metric",keys[i])
                self.transport.send_raw(pattern_format(out_pat,i=i,v=min(100,int(float(m.get(k,0) or 0)))))

    async def _ws_handler(self, ws: WebSocketServerProtocol):
        self.ws_clients.add(ws)
        await ws.send(json.dumps({"type":"config","data":self.cfg.data}))
        try:
            async for raw in ws: await self._handle(json.loads(raw),ws)
        except: pass
        finally: self.ws_clients.discard(ws)

    def _serial_status(self):
        return {"type":"serial_status","connected":self.transport.is_connected(0),
            "connected2":self.transport.is_connected(1),
            "port":self.transport._port_names[0],"port2":self.transport._port_names[1]}

    def _plugins_msg(self):
        return {"type":"plugins","data":self.plugins.catalog(),
            "meta":[{"name":p.get("name"),"file":p.get("_file"),"version":p.get("version","")} for p in self.plugins.plugins]}

    async def _handle(self, msg, ws):
        t=msg.get("type")

        if t=="save_config":
            self.cfg.data=msg["data"]; self.cfg.save()
            await ws.send(json.dumps({"type":"config_saved"}))
        elif t=="create_profile":
            name=msg.get("key",""); label=msg.get("label","Nouveau profil")
            if name and name not in self.cfg.data["profiles"]:
                self.cfg.data["profiles"][name]=empty_profile(label); self.cfg.save()
                self._broadcast({"type":"config","data":self.cfg.data})
        elif t=="delete_profile":
            name=msg.get("key","")
            if name in self.cfg.data["profiles"] and name!="default":
                del self.cfg.data["profiles"][name]
                if self.cfg.data.get("active_profile")==name: self.cfg.data["active_profile"]="default"
                self.cfg.save(); self._broadcast({"type":"config","data":self.cfg.data})
        elif t=="rename_profile":
            name=msg.get("key",""); label=msg.get("label","")
            if name in self.cfg.data["profiles"] and label:
                self.cfg.data["profiles"][name]["name"]=label; self.cfg.save()
                self._broadcast({"type":"config","data":self.cfg.data})
        elif t=="set_profile":
            name=msg.get("profile","")
            if name in self.cfg.data["profiles"]:
                self.cfg.data["active_profile"]=name; self.cfg.save()
                self._broadcast({"type":"profile_changed","profile":name})
        elif t=="test_action":
            threading.Thread(target=self.engine.run,args=(msg.get("actions",[]),),daemon=True).start()
        elif t=="get_ports":
            ports=[p.device for p in serial.tools.list_ports.comports()] if SERIAL_OK else []
            await ws.send(json.dumps({"type":"ports","data":ports}))
        elif t=="get_apps":
            async def _do():
                apps=await asyncio.get_event_loop().run_in_executor(None,get_installed_apps)
                await ws.send(json.dumps({"type":"apps","data":apps}))
            asyncio.ensure_future(_do())
        elif t=="get_plugins":
            await ws.send(json.dumps(self._plugins_msg()))
        elif t=="reload_plugins":
            self.plugins.reload(); await ws.send(json.dumps(self._plugins_msg()))
            self._broadcast({"type":"toast","message":f"✓ {len(self.plugins.plugins)} plugin(s) chargé(s)"})
        elif t=="get_processes":
            seen=set(); procs=[]
            for p in psutil.process_iter(["name"]):
                try:
                    n=p.info["name"]
                    if n and n.lower() not in seen: seen.add(n.lower()); procs.append(n)
                except: pass
            await ws.send(json.dumps({"type":"processes","data":sorted(procs)}))
        elif t=="get_audio_sessions":
            await ws.send(json.dumps({"type":"audio_sessions","data":list_audio_sessions()}))
        elif t in ("pick_folder","pick_file"):
            field=msg.get("field","")
            async def _do():
                path=await asyncio.get_event_loop().run_in_executor(None,self._native_picker,t=="pick_folder")
                await ws.send(json.dumps({"type":"picked_path","field":field,"path":path}))
            asyncio.ensure_future(_do())
        elif t=="connect_serial":
            self.transport.start(msg.get("port","AUTO"),baud=int(msg.get("baud",115200)),slot=int(msg.get("slot",0)))
            await ws.send(json.dumps(self._serial_status()))
        elif t=="get_serial_status":
            await ws.send(json.dumps(self._serial_status()))
        elif t=="save_protocol":
            proto=msg.get("protocol",{}); errors={}
            for key,pat in proto.items():
                try: pattern_to_regex(pat) if key.startswith("in_") else pattern_format(pat,i=0,v=0)
                except Exception as e: errors[key]=str(e)
            if errors: await ws.send(json.dumps({"type":"protocol_saved","ok":False,"errors":errors}))
            else:
                self.cfg.data["protocol"]=proto; self.cfg.save()
                await ws.send(json.dumps({"type":"protocol_saved","ok":True}))
        elif t=="test_protocol_pattern":
            pattern=msg.get("pattern",""); sample=msg.get("sample","")
            try:
                m=pattern_to_regex(pattern).match(sample.strip())
                if m: await ws.send(json.dumps({"type":"protocol_test_result","ok":True,"groups":m.groupdict()}))
                else: await ws.send(json.dumps({"type":"protocol_test_result","ok":False,"error":"Trame ne correspond pas"}))
            except Exception as e: await ws.send(json.dumps({"type":"protocol_test_result","ok":False,"error":str(e)}))
        elif t=="simulate_esp32_frame":
            raw=msg.get("raw","").strip()
            if not raw:
                await ws.send(json.dumps({"type":"protocol_test_result","ok":False,"error":"Trame vide"})); return
            proto=self.cfg.data.get("protocol",{}); matched_event=None; matched_groups={}
            for ev_key,ev_name in [("in_press","press"),("in_long_press","long_press"),
                                    ("in_double_click","double_click"),("in_release","release"),("in_pot","pot")]:
                pat=proto.get(ev_key,"")
                if not pat: continue
                try:
                    m2=pattern_to_regex(pat).match(raw)
                    if m2: matched_event=ev_name; matched_groups=m2.groupdict(); break
                except: continue
            if not matched_event:
                try:
                    parsed=json.loads(raw); t2=parsed.get("t","")
                    if t2 in ("press","long_press","double_click","release","pot"):
                        matched_event=t2; matched_groups={k:v for k,v in parsed.items() if k!="t"}
                except: pass
            self._on_esp32(raw)
            if matched_event:
                await ws.send(json.dumps({"type":"protocol_test_result","ok":True,
                    "event":matched_event,"groups":matched_groups,"message":f"Trame '{matched_event}' exécutée ✓"}))
            else:
                await ws.send(json.dumps({"type":"protocol_test_result","ok":False,
                    "error":"Aucun patron ne correspond (trame envoyée quand même)"}))
        elif t=="open_update_url":
            dl_url=msg.get("download_url","")
            async def _do_dl(dl_url):
                import urllib.request, tempfile
                REPO="tuturpotter-web/Imperium"
                try:
                    if not dl_url:
                        req=urllib.request.Request(f"https://api.github.com/repos/{REPO}/releases/latest",
                            headers={"User-Agent":"Imperium-updater"})
                        with urllib.request.urlopen(req,timeout=8) as r: release=json.loads(r.read())
                        asset=next((a for a in release.get("assets",[]) if a["name"].endswith(".exe")),None)
                        if not asset:
                            await ws.send(json.dumps({"type":"update_progress","error":"Aucun .exe dans la release"})); return
                        dl_url=asset["browser_download_url"]; filename=asset["name"]
                    else:
                        filename=dl_url.split("/")[-1]
                    await ws.send(json.dumps({"type":"update_progress","status":"downloading","pct":0,"filename":filename}))
                    tmp=os.path.join(tempfile.gettempdir(),filename)
                    last_pct=-1
                    def _rep(bn,bs,fs):
                        nonlocal last_pct
                        pct=min(100,int(bn*bs/fs*100)) if fs>0 else 0
                        if pct!=last_pct:
                            last_pct=pct
                            asyncio.ensure_future(ws.send(json.dumps({"type":"update_progress","status":"downloading","pct":pct,"filename":filename})))
                    await asyncio.get_event_loop().run_in_executor(None,lambda:urllib.request.urlretrieve(dl_url,tmp,_rep))
                    await ws.send(json.dumps({"type":"update_progress","status":"launching","pct":100,"filename":filename}))
                    await asyncio.sleep(0.5)
                    subprocess.Popen([tmp],creationflags=CREATE_NO_WINDOW)
                    await asyncio.sleep(1); os._exit(0)
                except Exception as e: await ws.send(json.dumps({"type":"update_progress","error":str(e)}))
            asyncio.ensure_future(_do_dl(dl_url))
        elif t=="check_update":
            async def _do_check():
                import urllib.request, urllib.error
                REPO="tuturpotter-web/Imperium"
                try:
                    req=urllib.request.Request(f"https://api.github.com/repos/{REPO}/releases/latest",
                        headers={"User-Agent":"Imperium-updater"})
                    with urllib.request.urlopen(req,timeout=8) as r: data=json.loads(r.read())
                    latest=data.get("tag_name","").lstrip("v")
                    asset=next((a for a in data.get("assets",[]) if a["name"].endswith(".exe")),None)
                    dl_url=asset["browser_download_url"] if asset else ""
                    if latest and latest!=APP_VERSION:
                        await ws.send(json.dumps({"type":"update_available","current":APP_VERSION,"latest":latest,"download_url":dl_url}))
                    else:
                        await ws.send(json.dumps({"type":"toast","message":f"✓ Imperium {APP_VERSION} est à jour"}))
                except urllib.error.URLError as e:
                    await ws.send(json.dumps({"type":"toast","message":f"⚠ MAJ impossible : {e.reason}"}))
                except Exception as e:
                    await ws.send(json.dumps({"type":"toast","message":f"⚠ MAJ : {e}"}))
            asyncio.ensure_future(_do_check())
        elif t=="preview_overlay":
            key=self.cfg.data.get("active_profile","default")
            profile=self.cfg.data.get("profiles",{}).get(key)
            if profile and self.overlay:
                self.overlay.show_profile(profile,self.cfg.data.get("overlay",{}))
        elif t=="update_button":
            pid=msg.get("profile","default"); bid=str(msg.get("button",0))
            if pid in self.cfg.data["profiles"]:
                self.cfg.data["profiles"][pid]["buttons"][bid]=msg.get("data",{}); self.cfg.save()

    def _native_picker(self, folder: bool) -> str:
        try:
            if folder:
                ps=("Add-Type -AssemblyName System.Windows.Forms;"
                    "$f=New-Object System.Windows.Forms.FolderBrowserDialog;"
                    "if($f.ShowDialog() -eq 'OK'){Write-Output $f.SelectedPath}")
            else:
                ps=("Add-Type -AssemblyName System.Windows.Forms;"
                    "$f=New-Object System.Windows.Forms.OpenFileDialog;"
                    "if($f.ShowDialog() -eq 'OK'){Write-Output $f.FileName}")
            return subprocess.run(["powershell","-NoProfile","-Command",ps],
                capture_output=True,text=True,timeout=120).stdout.strip()
        except Exception as e: log.error(f"picker: {e}"); return ""

    async def run(self):
        self.transport.start(self.cfg.data.get("serial_port","AUTO"))
        srv=await websockets.serve(self._ws_handler,"localhost",WS_PORT,max_size=10*1024*1024)
        await asyncio.gather(self._metrics_loop(),srv.wait_closed())

# ── HTTP SERVER ───────────────────────────────────────────────────────────────
def _app_dir():
    if getattr(sys,"frozen",False): return getattr(sys,"_MEIPASS",os.path.dirname(sys.executable))
    return os.path.dirname(os.path.abspath(__file__))

def _app_dir_persistent():
    if getattr(sys,"frozen",False): return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

def _http_server():
    import http.server, socketserver
    class Q(http.server.SimpleHTTPRequestHandler):
        def __init__(self,*a,**kw): super().__init__(*a,directory=_app_dir(),**kw)
        def log_message(self,*a): pass
        def end_headers(self):
            self.send_header("Cache-Control","no-store, no-cache, must-revalidate, max-age=0")
            self.send_header("Pragma","no-cache"); self.send_header("Expires","0")
            super().end_headers()
    try:
        with socketserver.TCPServer(("127.0.0.1",HTTP_PORT),Q) as h: h.serve_forever()
    except OSError: pass

def _port_is_free(port):
    import socket as _s
    s=_s.socket(_s.AF_INET,_s.SOCK_STREAM)
    try: s.bind(("127.0.0.1",port)); s.close(); return True
    except OSError: s.close(); return False

def _notify_already_running():
    if sys.platform=="win32":
        try:
            ctypes.windll.user32.MessageBoxW(0,
                "Imperium est déjà lancé.\n\nVérifie la barre des tâches.",
                "Imperium — déjà en cours",0x40|0x1000)
        except: pass

def _wait_for_http():
    import urllib.request
    url = f"http://127.0.0.1:{HTTP_PORT}/gui.html"
    for _ in range(40):
        try: urllib.request.urlopen(url, timeout=0.5); return
        except: time.sleep(0.25)

def _run_backend(deck):
    try:
        asyncio.run(deck.run())
    except KeyboardInterrupt: pass
    except OSError: _notify_already_running()
    finally:
        try: deck.cfg.save()
        except: pass
    os._exit(0)

# ── MAIN ──────────────────────────────────────────────────────────────────────
if __name__=="__main__":
    if not _port_is_free(WS_PORT):
        _notify_already_running(); sys.exit(0)

    threading.Thread(target=_http_server, daemon=True).start()
    deck = MacroDeck()
    threading.Thread(target=_run_backend, args=(deck,), daemon=True).start()

    # webview.start() DOIT etre sur le thread principal (contrainte COM Windows)
    _wait_for_http()
    try:
        import webview
        webview.create_window(
            "Imperium",
            f"http://127.0.0.1:{HTTP_PORT}/gui.html",
            width=820, height=680, min_size=(640, 480)
        )
        webview.start(gui="edgechromium")
        try: deck.cfg.save()
        except: pass
        os._exit(0)
    except Exception as e:
        log.warning(f"pywebview indisponible ({e}), fallback navigateur")
        try: webbrowser.open(f"http://127.0.0.1:{HTTP_PORT}/gui.html")
        except: pass
        try:
            while True: time.sleep(1)
        except KeyboardInterrupt: pass
        finally:
            try: deck.cfg.save()
            except: pass
