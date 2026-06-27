"""
Imperium — Application Windows native (tkinter)
Zéro navigateur, zéro HTML, zéro WebSocket.
"""
APP_VERSION = "dev"
import sys, os, ctypes, threading, time, json, subprocess, re
import shutil, glob, logging, datetime, webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import ttk, messagebox, colorchooser, filedialog
import tkinter.font as tkfont

# ── CACHER CONSOLE ───────────────────────────────────────────────────────────
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

def run_hidden(cmd, **kw):
    kw.setdefault("creationflags", CREATE_NO_WINDOW)
    kw.setdefault("startupinfo", _SI)
    return subprocess.Popen(cmd, **kw)

def run_silent(cmd):
    return run_hidden(cmd, shell=True)

import psutil, keyboard, mouse

try:
    from pycaw.pycaw import AudioUtilities, IAudioEndpointVolume
    from comtypes import CLSCTX_ALL; PYCAW_OK = True
except: PYCAW_OK = False

try:
    import win32gui, win32process; WIN32_OK = True
except: WIN32_OK = False

try:
    import wmi as wmilib; WMI_OK = True
except: WMI_OK = False

try:
    import serial, serial.tools.list_ports; SERIAL_OK = True
except: SERIAL_OK = False

GPU_OK = shutil.which("nvidia-smi") is not None
logging.basicConfig(level=logging.WARNING)
log = logging.getLogger("IMP")

CONFIG_PATH = Path(os.path.expanduser("~")) / ".macrodeck" / "config.json"
CONFIG_PATH.parent.mkdir(parents=True, exist_ok=True)

# ══════════════════════════════════════════════════════════════════════════════
# THÈME
# ══════════════════════════════════════════════════════════════════════════════
TH = {
    "bg":      "#0d0e12",
    "bg1":     "#11131a",
    "bg2":     "#161820",
    "bg3":     "#181b22",
    "bg4":     "#1e212b",
    "card":    "#1c1f29",
    "border":  "#2a2d3a",
    "border2": "#23263200",
    "accent":  "#6366f1",
    "accent2": "#818cf8",
    "text":    "#f1f5f9",
    "text2":   "#cbd5e1",
    "text3":   "#94a3b8",
    "text4":   "#64748b",
    "green":   "#22c55e",
    "red":     "#ef4444",
    "yellow":  "#f59e0b",
}

def th(k): return TH[k]

# ══════════════════════════════════════════════════════════════════════════════
# AUDIO
# ══════════════════════════════════════════════════════════════════════════════
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

def set_app_volume(name, level):
    if not PYCAW_OK or not name: return
    try:
        from pycaw.pycaw import ISimpleAudioVolume
        t = name.lower().replace(".exe","")
        for s in AudioUtilities.GetAllSessions():
            if s.Process and s.Process.name().lower().replace(".exe","") == t:
                s._ctl.QueryInterface(ISimpleAudioVolume).SetMasterVolume(max(0,min(100,level))/100.0, None)
    except: pass

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

def open_url(url):
    if not url: return
    if sys.platform == "win32":
        try:
            import winreg
            k=winreg.OpenKey(winreg.HKEY_CURRENT_USER, r"Software\Microsoft\Windows\Shell\Associations\UrlAssociations\http\UserChoice")
            pid,_=winreg.QueryValueEx(k,"ProgId"); winreg.CloseKey(k)
            ck=winreg.OpenKey(winreg.HKEY_CLASSES_ROOT, fr"{pid}\shell\open\command")
            cmd,_=winreg.QueryValueEx(ck,""); winreg.CloseKey(ck)
            run_hidden(cmd.replace("%1",url) if "%1" in cmd else f'{cmd} "{url}"', shell=True)
            return
        except: pass
        try: os.startfile(url); return
        except: pass
    webbrowser.open(url)

# ══════════════════════════════════════════════════════════════════════════════
# CONFIG
# ══════════════════════════════════════════════════════════════════════════════
def empty_profile(name):
    return {
        "name": name, "app_trigger": "",
        "buttons": {str(i):{"icon":"⭐","label":f"Bouton {i+1}","press":[],"long_press":[],"double_click":[]} for i in range(8)},
        "pots": {str(i):{"name":["Volume","App Vol","Luminosité","Custom"][i],"action":["volume_system","volume_app","brightness","custom"][i]} for i in range(4)}
    }

DEFAULT_CONFIG = {
    "profiles": {"default":empty_profile("Global"),"obs":empty_profile("OBS"),"discord":empty_profile("Discord")},
    "active_profile": "default",
    "led_strips": {str(i):{"metric":["cpu","ram","gpu_usage","ssd_usage"][i]} for i in range(4)},
    "serial_port": "AUTO", "theme": "dark",
    "protocol": {"in_press":"btn{i}:on","in_long_press":"","in_double_click":"","in_release":"btn{i}:off","in_pot":"pot{i}:{v}","out_led":"led{i}:{v}"},
    "serial_port2":"","baud_rate":115200,"baud_rate2":115200,
    "overlay":{"cell_size":56,"delay":3,"position":"br","alpha":97}
}

def pattern_to_regex(p):
    e=re.escape(p)
    e=e.replace(re.escape("{i}"),r"(?P<i>-?\d+)")
    e=e.replace(re.escape("{v}"),r"(?P<v>-?\d+)")
    return re.compile("^"+e+"$")

def pattern_format(p,i=None,v=None):
    o=p
    if i is not None: o=o.replace("{i}",str(i))
    if v is not None: o=o.replace("{v}",str(v))
    return o

class ConfigManager:
    def __init__(self):
        self.data = json.loads(json.dumps(DEFAULT_CONFIG))
        self.load()

    def load(self):
        if CONFIG_PATH.exists():
            try:
                saved = json.loads(CONFIG_PATH.read_text(encoding="utf-8"))
                self._deep_merge(self.data, saved)
            except: pass

    def _deep_merge(self, base, override):
        for k,v in override.items():
            if k in base and isinstance(base[k],dict) and isinstance(v,dict):
                self._deep_merge(base[k],v)
            else:
                base[k]=v

    def save(self):
        CONFIG_PATH.write_text(json.dumps(self.data,indent=2,ensure_ascii=False),encoding="utf-8")

    def active(self):
        n=self.data.get("active_profile","default")
        return self.data["profiles"].get(n, list(self.data["profiles"].values())[0])

# ══════════════════════════════════════════════════════════════════════════════
# MÉTRIQUES
# ══════════════════════════════════════════════════════════════════════════════
class Metrics:
    def __init__(self):
        self._net_prev=psutil.net_io_counters(); self._net_t=time.time()
        self._ohm=None; self._twmi=None
        if WMI_OK:
            try: self._ohm=wmilib.WMI(namespace="root\\OpenHardwareMonitor")
            except: pass
            try: self._twmi=wmilib.WMI(namespace="root\\wmi")
            except: pass

    def _nvidia(self):
        try:
            p=run_hidden(["nvidia-smi","--query-gpu=utilization.gpu,memory.used,memory.total,temperature.gpu,name",
                "--format=csv,noheader,nounits"],stdout=subprocess.PIPE,stderr=subprocess.PIPE,text=True)
            out,_=p.communicate(timeout=2)
            u,mu,mt,t,n=[x.strip() for x in out.strip().split("\n")[0].split(",")]
            return {"usage":float(u),"vram":round(float(mu)/float(mt)*100,1) if float(mt) else 0,"temp":float(t),"name":n}
        except: return None

    def collect(self):
        m={}
        m["cpu"]=psutil.cpu_percent(interval=None)
        m["cpu_cores"]=psutil.cpu_count(logical=True)
        f=psutil.cpu_freq(); m["cpu_freq"]=round(f.current,0) if f else 0
        m["cpu_temp"]=self._temp("Temperature","CPU")
        ram=psutil.virtual_memory()
        m["ram"]=ram.percent; m["ram_used_gb"]=round(ram.used/1e9,1); m["ram_total_gb"]=round(ram.total/1e9,1)
        m["gpu_usage"]=0; m["gpu_vram"]=0; m["gpu_temp"]=None; m["gpu_name"]=""
        if GPU_OK:
            g=self._nvidia()
            if g: m["gpu_usage"]=g["usage"]; m["gpu_vram"]=g["vram"]; m["gpu_temp"]=g["temp"]; m["gpu_name"]=g["name"]
        m["ssd_usage"]=0
        try: m["ssd_usage"]=psutil.disk_usage("C:\\").percent
        except:
            try: m["ssd_usage"]=psutil.disk_usage("/").percent
            except: pass
        now=time.time(); net=psutil.net_io_counters(); dt=now-self._net_t
        m["net_up"]=round((net.bytes_sent-self._net_prev.bytes_sent)/dt/1024,1) if dt>0 else 0
        m["net_down"]=round((net.bytes_recv-self._net_prev.bytes_recv)/dt/1024,1) if dt>0 else 0
        self._net_prev=net; self._net_t=now
        m["uptime"]=str(datetime.timedelta(seconds=int(time.time()-psutil.boot_time())))
        m["volume"]=get_volume(); m["muted"]=get_mute()
        n=datetime.datetime.now(); m["time"]=n.strftime("%H:%M:%S"); m["date"]=n.strftime("%d/%m/%Y")
        return m

    def _temp(self,typ,frag):
        if self._ohm:
            try:
                for s in self._ohm.Sensor():
                    if s.SensorType==typ and frag.lower() in s.Name.lower(): return round(s.Value,1)
            except: pass
        if typ=="Temperature" and self._twmi:
            try:
                for z in self._twmi.MSAcpi_ThermalZoneTemperature():
                    k=z.CurrentTemperature
                    if k and k>0: return round(k/10.0-273.15,1)
            except: pass
        return None

# ══════════════════════════════════════════════════════════════════════════════
# TRANSPORT SÉRIE
# ══════════════════════════════════════════════════════════════════════════════
class Transport:
    LONG_MS=400; DOUBLE_MS=300
    def __init__(self,on_msg):
        self._cb=on_msg; self._slots=[None,None]; self._port_names=[None,None]; self._btn_state={}

    def start(self,port="AUTO",baud=115200,slot=0):
        if not SERIAL_OK: return
        old=self._slots[slot]
        if old:
            try: old.close()
            except: pass
            self._slots[slot]=None; self._port_names[slot]=None
        if port=="AUTO":
            ports=serial.tools.list_ports.comports()
            other=self._port_names[1-slot]
            cands=[p.device for p in ports if any(k in p.description.upper() for k in ["CP210","CH340","USB","FTDI"]) and p.device!=other]
            if not cands: cands=[p.device for p in ports if p.device!=other]
            port=cands[0] if cands else None
        if not port: return
        try:
            ser=serial.Serial(port,baud,timeout=0.1)
            self._slots[slot]=ser; self._port_names[slot]=port
            threading.Thread(target=self._loop,args=(ser,slot),daemon=True).start()
        except Exception as e: log.error(f"Serial {slot}: {e}")

    def is_connected(self,slot=0): s=self._slots[slot]; return bool(s and s.is_open)

    def _loop(self,ser,slot):
        while ser and ser.is_open:
            try:
                line=ser.readline().decode("utf-8",errors="ignore").strip()
                if line: self._cb(line,slot)
            except: time.sleep(1)
        if self._slots[slot] is ser: self._slots[slot]=None; self._port_names[slot]=None

    def _handle_timing(self,idx,event,dispatch):
        now=time.time(); st=self._btn_state.setdefault(idx,{})
        if event=="on":
            last=st.get("last_on"); st["on_t"]=now; st["last_on"]=now
            if last and (now-last)*1000<self.DOUBLE_MS: st["last_on"]=None; dispatch(idx,"double_click")
        elif event=="off":
            on_t=st.get("on_t")
            if on_t is None: return
            st["on_t"]=None
            dispatch(idx,"long_press" if (now-on_t)*1000>=self.LONG_MS else "press")

    def send_raw(self,line,slot=0):
        ser=self._slots[slot]
        if ser and ser.is_open:
            try: ser.write((line+"\n").encode())
            except: pass

# ══════════════════════════════════════════════════════════════════════════════
# ACTIONS
# ══════════════════════════════════════════════════════════════════════════════
ALL_ACTIONS = [
    # Profils
    {"cat":"Profils","icon":"◈","type":"switch_profile","name":"Changer de profil","params":[{"key":"profile","lbl":"Clé du profil","ph":"obs"}]},
    {"cat":"Profils","icon":"▶","type":"next_profile","name":"Profil suivant","params":[]},
    {"cat":"Profils","icon":"◀","type":"prev_profile","name":"Profil précédent","params":[]},
    # PC
    {"cat":"PC","icon":"🚀","type":"open_app","name":"Lancer une appli","params":[{"key":"path","lbl":"Chemin / nom","ph":"notepad.exe"}]},
    {"cat":"PC","icon":"✕","type":"close_app","name":"Fermer une appli","params":[{"key":"name","lbl":"Nom du process","ph":"notepad"}]},
    {"cat":"PC","icon":"📁","type":"open_folder","name":"Ouvrir dossier","params":[{"key":"path","lbl":"Chemin","ph":"C:\\"}]},
    {"cat":"PC","icon":"📄","type":"open_file","name":"Ouvrir fichier","params":[{"key":"path","lbl":"Chemin","ph":"C:\\file.pdf"}]},
    {"cat":"PC","icon":"🔒","type":"lock_session","name":"Verrouiller","params":[]},
    {"cat":"PC","icon":"⭕","type":"shutdown","name":"Éteindre le PC","params":[]},
    {"cat":"PC","icon":"🔄","type":"restart","name":"Redémarrer","params":[]},
    {"cat":"PC","icon":"💤","type":"sleep","name":"Veille","params":[]},
    {"cat":"PC","icon":"🧹","type":"clean_temp","name":"Nettoyer temp","params":[]},
    {"cat":"PC","icon":"📷","type":"screenshot","name":"Capture d'écran","params":[]},
    {"cat":"PC","icon":"🗕","type":"win_minimize_all","name":"Réduire tout","params":[]},
    {"cat":"PC","icon":"▶","type":"run_command","name":"Commande","params":[{"key":"command","lbl":"Commande","ph":"ipconfig"}]},
    # Scripts
    {"cat":"Avancé","icon":"⚡","type":"script_powershell","name":"Script PowerShell","params":[{"key":"code","lbl":"Code PS","ph":"Get-Date","multi":True}]},
    {"cat":"Avancé","icon":"🐍","type":"script_python","name":"Script Python","params":[{"key":"code","lbl":"Code Python","ph":"print('hello')","multi":True}]},
    {"cat":"Avancé","icon":"🖥","type":"script_batch","name":"Script Batch","params":[{"key":"code","lbl":"Code .bat","ph":"echo hello","multi":True}]},
    {"cat":"Avancé","icon":"⏳","type":"delay","name":"Délai","params":[{"key":"ms","lbl":"Millisecondes","ph":"500"}]},
    {"cat":"Avancé","icon":"🔗","type":"multi_action","name":"Multi-actions","params":[]},
    # Clavier / souris
    {"cat":"Clavier","icon":"⌨","type":"hotkey","name":"Raccourci clavier","params":[{"key":"keys","lbl":"Touches","ph":"ctrl+c"}]},
    {"cat":"Clavier","icon":"✏","type":"type_text","name":"Saisir texte","params":[{"key":"text","lbl":"Texte","ph":"Bonjour !"}]},
    {"cat":"Clavier","icon":"🔁","type":"key_sequence","name":"Séquence de touches","params":[{"key":"sequence","lbl":"Touches (virgule)","ph":"ctrl+c,ctrl+v"}]},
    {"cat":"Clavier","icon":"🖱","type":"mouse_click","name":"Clic souris","params":[{"key":"button","lbl":"Bouton","ph":"left"},{"key":"x","lbl":"X (opt)","ph":""},{"key":"y","lbl":"Y (opt)","ph":""}]},
    {"cat":"Clavier","icon":"🖱","type":"mouse_scroll","name":"Défilement souris","params":[{"key":"delta","lbl":"Delta","ph":"3"}]},
    # Audio
    {"cat":"Audio","icon":"🔊","type":"volume_up","name":"Volume +","params":[{"key":"step","lbl":"Pas (%)","ph":"5"}]},
    {"cat":"Audio","icon":"🔉","type":"volume_down","name":"Volume -","params":[{"key":"step","lbl":"Pas (%)","ph":"5"}]},
    {"cat":"Audio","icon":"🔈","type":"volume_set","name":"Volume fixe","params":[{"key":"value","lbl":"Valeur (0-100)","ph":"50"}]},
    {"cat":"Audio","icon":"🔇","type":"mute_toggle","name":"Muet","params":[]},
    # Médias
    {"cat":"Médias","icon":"⏯","type":"media_play_pause","name":"Lecture/Pause","params":[]},
    {"cat":"Médias","icon":"⏭","type":"media_next","name":"Suivant","params":[]},
    {"cat":"Médias","icon":"⏮","type":"media_prev","name":"Précédent","params":[]},
    {"cat":"Médias","icon":"⏹","type":"media_stop","name":"Stop","params":[]},
    {"cat":"Médias","icon":"🌟","type":"brightness","name":"Luminosité","params":[{"key":"value","lbl":"Valeur (0-100)","ph":"75"}]},
    # OBS
    {"cat":"OBS","icon":"🎬","type":"obs_scene","name":"Changer scène","params":[{"key":"scene","lbl":"Nom scène","ph":"Gaming"}]},
    {"cat":"OBS","icon":"📡","type":"obs_stream_start","name":"Démarrer stream","params":[]},
    {"cat":"OBS","icon":"⏹","type":"obs_stream_stop","name":"Arrêter stream","params":[]},
    {"cat":"OBS","icon":"⏺","type":"obs_record_start","name":"Démarrer enregistrement","params":[]},
    {"cat":"OBS","icon":"⏹","type":"obs_record_stop","name":"Arrêter enregistrement","params":[]},
    {"cat":"OBS","icon":"🎙","type":"obs_mute_toggle","name":"Muet source OBS","params":[{"key":"source","lbl":"Source","ph":"Mic/Aux"}]},
    # Visio
    {"cat":"Visio","icon":"🎙","type":"zoom_mute","name":"Zoom : Muet","params":[]},
    {"cat":"Visio","icon":"📷","type":"zoom_camera","name":"Zoom : Caméra","params":[]},
    {"cat":"Visio","icon":"✋","type":"zoom_hand","name":"Zoom : Main levée","params":[]},
    {"cat":"Visio","icon":"🖥","type":"zoom_share","name":"Zoom : Partager","params":[]},
    {"cat":"Visio","icon":"🚪","type":"zoom_leave","name":"Zoom : Quitter","params":[]},
    {"cat":"Visio","icon":"🎙","type":"teams_mute","name":"Teams : Muet","params":[]},
    {"cat":"Visio","icon":"📷","type":"teams_camera","name":"Teams : Caméra","params":[]},
    {"cat":"Visio","icon":"🎙","type":"discord_mute","name":"Discord : Muet","params":[]},
    {"cat":"Visio","icon":"🔇","type":"discord_deafen","name":"Discord : Sourd","params":[]},
    # Dev
    {"cat":"Dev","icon":"💻","type":"vscode_open","name":"Ouvrir VS Code","params":[{"key":"path","lbl":"Dossier","ph":"."}]},
    {"cat":"Dev","icon":"⬇","type":"git_pull","name":"Git Pull","params":[{"key":"folder","lbl":"Dossier","ph":"."}]},
    {"cat":"Dev","icon":"⬆","type":"git_push","name":"Git Push","params":[{"key":"folder","lbl":"Dossier","ph":"."}, {"key":"message","lbl":"Message","ph":"commit"}]},
    {"cat":"Dev","icon":"🐳","type":"docker_start","name":"Docker Start","params":[{"key":"name","lbl":"Conteneur","ph":"myapp"}]},
    {"cat":"Dev","icon":"🐳","type":"docker_stop","name":"Docker Stop","params":[{"key":"name","lbl":"Conteneur","ph":"myapp"}]},
    # Web
    {"cat":"Web","icon":"🌐","type":"open_url","name":"Ouvrir URL","params":[{"key":"url","lbl":"URL","ph":"https://"}]},
    {"cat":"Web","icon":"🤖","type":"open_chatgpt","name":"ChatGPT","params":[]},
    {"cat":"Web","icon":"📧","type":"google_gmail","name":"Gmail","params":[]},
    {"cat":"Web","icon":"📅","type":"google_calendar","name":"Google Agenda","params":[]},
    # Temps
    {"cat":"Temps","icon":"⏱","type":"timer","name":"Minuteur","params":[{"key":"seconds","lbl":"Secondes","ph":"60"},{"key":"label","lbl":"Message","ph":"Terminé !"}]},
    {"cat":"Temps","icon":"🍅","type":"pomodoro","name":"Pomodoro (25 min)","params":[]},
    # Réseau
    {"cat":"Réseau","icon":"📡","type":"ping","name":"Ping","params":[{"key":"host","lbl":"Hôte","ph":"8.8.8.8"}]},
    {"cat":"Réseau","icon":"🔌","type":"api_call","name":"Appel API","params":[{"key":"url","lbl":"URL","ph":"https://api.example.com"},{"key":"method","lbl":"Méthode","ph":"GET"}]},
    {"cat":"Réseau","icon":"🪝","type":"webhook","name":"Webhook","params":[{"key":"url","lbl":"URL","ph":"https://"}]},
    {"cat":"Réseau","icon":"🏠","type":"home_assistant","name":"Home Assistant","params":[{"key":"ha_url","lbl":"URL HA","ph":"http://homeassistant.local:8123"},{"key":"service","lbl":"Service","ph":"light.toggle"},{"key":"entity_id","lbl":"Entité","ph":"light.salon"}]},
]

POT_ACTIONS = [
    ("volume_system","🔊 Volume système"),("volume_app","🎵 Volume appli"),
    ("brightness","🌟 Luminosité"),("scroll","🖱 Défilement"),
    ("zoom_level","🔍 Zoom"),("media_seek","⏩ Seek média"),
    ("discord_volume","💬 Discord"),("spotify_volume","🎵 Spotify"),
    ("game_volume","🎮 Jeu"),("mic_volume","🎙 Micro"),
    ("obs_volume","🎬 OBS"),("custom","⚙ Custom"),
]

# ══════════════════════════════════════════════════════════════════════════════
# OVERLAY TKINTER (fenêtre flottante profil)
# ══════════════════════════════════════════════════════════════════════════════
class ProfileOverlay:
    def __init__(self):
        self._q=None; self._root=None; self._popup=None; self._timer=None
        self._ready=threading.Event()
        threading.Thread(target=self._run,daemon=True).start()
        self._ready.wait(timeout=5)

    def _run(self):
        try:
            import queue as _q
            self._q=_q.Queue()
            root=tk.Tk(); root.withdraw(); self._root=root; self._ready.set()
            def poll():
                try:
                    while True:
                        item=self._q.get_nowait()
                        try: self._show(*item)
                        except Exception as e: log.warning(f"Overlay: {e}")
                except: pass
                root.after(30,poll)
            root.after(30,poll); root.mainloop()
        except Exception as e:
            log.warning(f"Overlay init: {e}"); self._ready.set()

    def _show(self,profile,ov_cfg):
        root=self._root
        if not root: return
        if self._timer:
            try: root.after_cancel(self._timer)
            except: pass
        if self._popup:
            try: self._popup.destroy()
            except: pass
            self._popup=None

        ov=ov_cfg or {}; CELL=max(32,min(100,int(ov.get("cell_size",56))))
        DELAY=max(1,min(30,int(ov.get("delay",3))))*1000
        POS=ov.get("position","br"); ALPHA=max(0.2,min(1.0,int(ov.get("alpha",97))/100))
        ACC="#6366f1"; BG="#0d0e12"; CARD="#1c1f29"; FG="#f1f5f9"; FG3="#94a3b8"
        BG3="#181b22"; BG4="#1e212b"; BDR="#2a2d3a"; GAP=4; PAD=10; COLS=4
        W=COLS*CELL+(COLS-1)*GAP+PAD*2
        H=38+1+8+CELL*2+GAP+8+1+8+CELL+12
        sw=root.winfo_screenwidth(); sh=root.winfo_screenheight(); mg=20
        X,Y={"br":(sw-W-mg,sh-H-60),"bl":(mg,sh-H-60),"tr":(sw-W-mg,mg+40)}.get(POS,(mg,mg+40))

        win=tk.Toplevel(root); self._popup=win
        win.overrideredirect(True); win.attributes("-topmost",True)
        try: win.attributes("-alpha",ALPHA)
        except: pass
        win.configure(bg=ACC); win.geometry(f"{W}x{H}+{X}+{Y}"); win._imgs=[]
        main=tk.Frame(win,bg=BG); main.pack(padx=1,pady=1,fill="both",expand=True)

        # Header
        hdr=tk.Frame(main,bg=BG); hdr.pack(fill="x",padx=PAD,pady=(7,4))
        dot=tk.Canvas(hdr,width=8,height=8,bg=BG,highlightthickness=0); dot.pack(side="left")
        dot.create_oval(0,0,8,8,fill=ACC,outline="")
        tk.Label(hdr,text=profile.get("name","Profil"),fg=FG,bg=BG,font=("Segoe UI",10,"bold")).pack(side="left",padx=(6,0))
        tk.Label(hdr,text="PROFIL",fg=ACC,bg=BG,font=("Segoe UI",7,"bold")).pack(side="right")
        tk.Frame(main,bg=BDR,height=1).pack(fill="x")

        def _img(data_url,sz):
            try:
                import io,base64 as b64; raw=b64.b64decode(data_url[data_url.index(",")+1:])
                try:
                    from PIL import Image as PI,ImageTk
                    return ImageTk.PhotoImage(PI.open(io.BytesIO(raw)).resize((sz,sz),PI.LANCZOS))
                except ImportError:
                    img=tk.PhotoImage(data=b64.b64encode(raw).decode())
                    tw,th=img.width(),img.height()
                    if tw>sz or th>sz:
                        f=max(tw//sz,th//sz,1)
                        if f>1: img=img.subsample(f,f)
                    return img
            except: return None

        bf=tk.Frame(main,bg=BG); bf.pack(padx=PAD,pady=(8,0))
        for i in range(8):
            b=profile.get("buttons",{}).get(str(i),{}); r,c=divmod(i,COLS)
            outer=tk.Frame(bf,bg=BDR); outer.grid(row=r,column=c,padx=GAP//2,pady=GAP//2)
            cell=tk.Frame(outer,bg=CARD,width=CELL-2,height=CELL-2); cell.pack(padx=1,pady=1); cell.pack_propagate(False)
            lbl=(b.get("label") or f"Btn {i+1}")[:9]; placed=False
            if b.get("iconImage","").startswith("data:image"):
                img=_img(b["iconImage"],max(CELL-16,18))
                if img:
                    win._imgs.append(img)
                    tk.Label(cell,image=img,bg=CARD).place(relx=.5,rely=.36,anchor="center")
                    tk.Label(cell,text=lbl,fg=FG3,bg=CARD,font=("Segoe UI",6)).place(relx=.5,rely=.82,anchor="center")
                    placed=True
            if not placed:
                tk.Label(cell,text=b.get("icon","●"),fg=FG,bg=CARD,font=("Segoe UI Emoji",15)).place(relx=.5,rely=.36,anchor="center")
                tk.Label(cell,text=lbl,fg=FG3,bg=CARD,font=("Segoe UI",6)).place(relx=.5,rely=.78,anchor="center")

        tk.Frame(main,bg=BDR,height=1).pack(fill="x",padx=PAD,pady=(8,0))

        POT_LBL={"volume_system":"Vol.sys","volume_app":"Vol.app","brightness":"Luminosité","scroll":"Scroll",
            "zoom_level":"Zoom","media_seek":"Seek","discord_volume":"Discord","spotify_volume":"Spotify",
            "game_volume":"Jeu","mic_volume":"Micro","obs_volume":"OBS","custom":"Custom"}
        pf=tk.Frame(main,bg=BG); pf.pack(padx=PAD,pady=(8,12))
        for i in range(COLS):
            p=profile.get("pots",{}).get(str(i),{})
            name=(p.get("name") or f"Pot {i+1}")[:8]
            action=POT_LBL.get(p.get("action",""),"—")
            outer=tk.Frame(pf,bg=BDR); outer.grid(row=0,column=i,padx=GAP//2)
            cell=tk.Frame(outer,bg=BG3,width=CELL-2,height=CELL-2); cell.pack(padx=1,pady=1); cell.pack_propagate(False)
            img_data=p.get("image","")
            if img_data and img_data.startswith("data:image"):
                img=_img(img_data,max(CELL-22,14))
                if img:
                    win._imgs.append(img)
                    tk.Label(cell,image=img,bg=BG3).place(relx=.5,rely=.28,anchor="center")
                    tk.Label(cell,text=name,fg=FG,bg=BG3,font=("Segoe UI",5,"bold")).place(relx=.5,rely=.80,anchor="center")
                    continue
            cv=tk.Canvas(cell,width=26,height=26,bg=BG3,highlightthickness=0); cv.place(relx=.5,rely=.26,anchor="center")
            cv.create_oval(1,1,25,25,outline=FG3,width=1,fill=BG4)
            cv.create_oval(5,5,21,21,outline=ACC,width=1.5,fill=BG3)
            cv.create_oval(10,10,16,16,fill=ACC,outline="")
            tk.Label(cell,text=name,fg=FG,bg=BG3,font=("Segoe UI",6,"bold")).place(relx=.5,rely=.65,anchor="center")
            tk.Label(cell,text=action,fg=FG3,bg=BG3,font=("Segoe UI",5)).place(relx=.5,rely=.83,anchor="center")

        win.update_idletasks()
        self._timer=root.after(DELAY,self._close)

    def _close(self):
        self._timer=None
        if self._popup:
            try: self._popup.destroy()
            except: pass
            self._popup=None

    def show(self,profile,ov_cfg):
        if self._q:
            try: self._q.put_nowait((profile,ov_cfg))
            except: pass

# ══════════════════════════════════════════════════════════════════════════════
# MOTEUR D'ACTIONS
# ══════════════════════════════════════════════════════════════════════════════
class ActionEngine:
    def __init__(self,cfg,on_profile_change):
        self.cfg=cfg; self._profile_cb=on_profile_change

    def run(self,actions):
        for a in actions:
            try: self._one(a)
            except Exception as e: log.error(f"Action {a.get('type')}: {e}")

    def run_pot(self,pot_cfg,val):
        ac=pot_cfg.get("action","volume_system")
        try:
            if   ac=="volume_system":  set_volume(val)
            elif ac=="volume_app":     set_app_volume(pot_cfg.get("app",""),val)
            elif ac=="discord_volume": set_app_volume("Discord",val)
            elif ac=="spotify_volume": set_app_volume("Spotify",val)
            elif ac=="game_volume":    set_app_volume(pot_cfg.get("app",""),val)
            elif ac=="mic_volume":     set_app_volume(pot_cfg.get("app","") or "Discord",val)
            elif ac=="brightness":
                run_hidden(["powershell","-Command",
                    f"(Get-WmiObject -NS root/WMI -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1,{val})"],
                    creationflags=CREATE_NO_WINDOW)
            elif ac in ("scroll","zoom_level","media_seek","playback_speed"):
                last=pot_cfg.get("_last",50); d=val-last; pot_cfg["_last"]=val
                if not d: return
                if   ac=="scroll": mouse.wheel(d/8)
                elif ac=="zoom_level": keyboard.press("ctrl"); mouse.wheel(d/10); keyboard.release("ctrl")
                elif ac=="media_seek":
                    if d>2: keyboard.send("right")
                    elif d<-2: keyboard.send("left")
            elif ac=="custom":
                code=pot_cfg.get("script","")
                if code: exec(code,{"value":val})
        except Exception as e: log.error(f"Pot '{ac}': {e}")

    def _one(self,a):
        if isinstance(a.get("params"),dict):
            m=dict(a); m.update(a["params"]); a=m
        t=a.get("type","")

        if t in ("switch_profile","next_profile","prev_profile"):
            keys=list(self.cfg.data["profiles"].keys())
            cur=self.cfg.data.get("active_profile","default")
            if   t=="switch_profile": n=a.get("profile","")
            elif t=="next_profile": n=keys[(keys.index(cur)+1)%len(keys)] if cur in keys else keys[0]
            else: n=keys[(keys.index(cur)-1)%len(keys)] if cur in keys else keys[0]
            if n in self.cfg.data["profiles"]:
                self.cfg.data["active_profile"]=n; self.cfg.save(); self._profile_cb(n)
        elif t=="open_app":     run_hidden(a.get("path",""),shell=True,creationflags=CREATE_NO_WINDOW)
        elif t=="close_app":
            n=a.get("name","").lower()
            [p.terminate() for p in psutil.process_iter(["name"]) if n in (p.info.get("name") or "").lower()]
        elif t=="open_folder":  os.startfile(a.get("path","."))
        elif t=="open_file":    os.startfile(a.get("path",""))
        elif t=="open_url":     open_url(a.get("url",""))
        elif t=="lock_session": keyboard.send("win+l")
        elif t=="shutdown":     run_silent("shutdown /s /t 0")
        elif t=="restart":      run_silent("shutdown /r /t 0")
        elif t=="sleep":        run_silent("rundll32.exe powrprof.dll,SetSuspendState 0,1,0")
        elif t=="logoff":       run_silent("shutdown /l")
        elif t=="run_command":  run_hidden(a.get("command",""),shell=True,creationflags=CREATE_NO_WINDOW)
        elif t=="script_powershell": run_hidden(["powershell","-Command",a.get("code","")],creationflags=CREATE_NO_WINDOW)
        elif t=="script_python": exec(a.get("code",""),{})
        elif t=="script_batch":
            tmp=os.path.join(os.environ.get("TEMP","."), "imp_tmp.bat")
            open(tmp,"w").write(a.get("code","")); run_hidden(tmp,shell=True,creationflags=CREATE_NO_WINDOW)
        elif t=="clean_temp":
            for f in glob.glob(os.path.join(os.environ.get("TEMP",""),"*")):
                try: os.remove(f) if os.path.isfile(f) else shutil.rmtree(f,ignore_errors=True)
                except: pass
        elif t=="screenshot":       keyboard.send("win+shift+s")
        elif t=="win_minimize_all": keyboard.send("win+d")
        elif t=="hotkey":       keyboard.send(a.get("keys",""))
        elif t=="type_text":    keyboard.write(a.get("text",""),delay=a.get("delay",0.03))
        elif t=="key_sequence":
            for k in a.get("sequence","").split(","):
                keyboard.send(k.strip()); time.sleep(a.get("interval",0.05))
        elif t=="mouse_click":
            x,y=a.get("x"),a.get("y")
            if x is not None: mouse.move(x,y,absolute=True)
            mouse.click(a.get("button","left"))
        elif t=="mouse_scroll": mouse.wheel(a.get("delta",1))
        elif t=="volume_up":   set_volume(get_volume()+a.get("step",5))
        elif t=="volume_down": set_volume(get_volume()-a.get("step",5))
        elif t=="volume_set":  set_volume(int(a.get("value",50)))
        elif t=="mute_toggle": set_mute(not get_mute())
        elif t=="media_play_pause": keyboard.send("play/pause media")
        elif t=="media_next":  keyboard.send("next track")
        elif t=="media_prev":  keyboard.send("previous track")
        elif t=="media_stop":  keyboard.send("stop media")
        elif t=="brightness":
            run_hidden(["powershell","-Command",
                f"(Get-WmiObject -NS root/WMI -Class WmiMonitorBrightnessMethods).WmiSetBrightness(1,{a.get('value',75)})"],
                creationflags=CREATE_NO_WINDOW)
        elif t=="obs_scene":        self._obs("SetCurrentScene",{"scene-name":a.get("scene","")})
        elif t=="obs_stream_start": self._obs("StartStreaming",{})
        elif t=="obs_stream_stop":  self._obs("StopStreaming",{})
        elif t=="obs_record_start": self._obs("StartRecording",{})
        elif t=="obs_record_stop":  self._obs("StopRecording",{})
        elif t=="obs_mute_toggle":  self._obs("ToggleMute",{"source":a.get("source","Mic/Aux")})
        elif t=="zoom_mute":     keyboard.send("alt+a")
        elif t=="zoom_camera":   keyboard.send("alt+v")
        elif t=="zoom_hand":     keyboard.send("alt+y")
        elif t=="zoom_share":    keyboard.send("alt+s")
        elif t=="zoom_leave":    keyboard.send("alt+q")
        elif t=="teams_mute":    keyboard.send("ctrl+shift+m")
        elif t=="teams_camera":  keyboard.send("ctrl+shift+o")
        elif t=="discord_mute":  keyboard.send("ctrl+shift+m")
        elif t=="discord_deafen":keyboard.send("ctrl+shift+d")
        elif t=="vscode_open":  run_hidden(f'code "{a.get("path",".")}"',shell=True,creationflags=CREATE_NO_WINDOW)
        elif t=="git_pull":     run_hidden(f'git -C "{a.get("folder",".")}" pull',shell=True,creationflags=CREATE_NO_WINDOW)
        elif t=="git_push":
            f=a.get("folder","."); m=a.get("message","commit")
            run_hidden(f'git -C "{f}" add -A && git -C "{f}" commit -m "{m}" && git -C "{f}" push',shell=True,creationflags=CREATE_NO_WINDOW)
        elif t=="docker_start": run_hidden(f'docker start {a.get("name","")}',shell=True,creationflags=CREATE_NO_WINDOW)
        elif t=="docker_stop":  run_hidden(f'docker stop {a.get("name","")}',shell=True,creationflags=CREATE_NO_WINDOW)
        elif t in ("open_url","open_chatgpt","google_gmail","google_calendar","google_meet"):
            urls={"open_chatgpt":"https://chatgpt.com","google_gmail":"https://mail.google.com",
                  "google_calendar":"https://calendar.google.com","google_meet":"https://meet.google.com/new"}
            open_url(a.get("url","") or urls.get(t,""))
        elif t=="timer":
            s=int(a.get("seconds",60)); lbl=a.get("label","Terminé !")
            threading.Thread(target=lambda:(time.sleep(s),ctypes.windll.user32.MessageBoxW(0,lbl,"Imperium ⏱",0x40|0x1000)),daemon=True).start()
        elif t=="pomodoro":
            threading.Thread(target=lambda:(time.sleep(25*60),ctypes.windll.user32.MessageBoxW(0,"🍅 Pomodoro terminé !","Imperium",0x40|0x1000)),daemon=True).start()
        elif t=="delay": time.sleep(a.get("ms",500)/1000)
        elif t=="api_call": threading.Thread(target=self._api,args=(a,),daemon=True).start()
        elif t=="webhook":  threading.Thread(target=self._webhook,args=(a,),daemon=True).start()
        elif t=="home_assistant": threading.Thread(target=self._ha,args=(a,),daemon=True).start()
        elif t=="multi_action":
            delay=a.get("delay",0)
            def _r():
                for act in a.get("actions",[]): self._one(act); time.sleep(delay/1000) if delay else None
            threading.Thread(target=_r,daemon=True).start()

    def _obs(self,req,data):
        try:
            import websocket; ws=websocket.create_connection("ws://localhost:4444",timeout=3)
            ws.send(json.dumps({"request-type":req,"message-id":"md",**data})); ws.close()
        except: pass

    def _api(self,a):
        import urllib.request
        req=urllib.request.Request(a.get("url",""),method=a.get("method","GET"))
        for k,v in a.get("headers",{}).items(): req.add_header(k,v)
        if a.get("body"): req.data=json.dumps(a["body"]).encode(); req.add_header("Content-Type","application/json")
        try:
            with urllib.request.urlopen(req,timeout=10) as r: log.info(f"API {r.status}")
        except Exception as e: log.error(f"API: {e}")

    def _webhook(self,a):
        import urllib.request
        req=urllib.request.Request(a.get("url",""),data=json.dumps(a.get("payload",{})).encode(),method="POST")
        req.add_header("Content-Type","application/json")
        try:
            with urllib.request.urlopen(req,timeout=10) as r: log.info(f"Webhook {r.status}")
        except Exception as e: log.error(f"Webhook: {e}")

    def _ha(self,a):
        import urllib.request
        url=f"{a.get('ha_url','http://homeassistant.local:8123')}/api/services/{a.get('service','').replace('.','/')}"
        req=urllib.request.Request(url,data=json.dumps({"entity_id":a.get("entity_id","")}).encode(),method="POST")
        req.add_header("Authorization",f"Bearer {a.get('token','')}"); req.add_header("Content-Type","application/json")
        try:
            with urllib.request.urlopen(req,timeout=5) as r: log.info(f"HA {r.status}")
        except Exception as e: log.error(f"HA: {e}")

# ══════════════════════════════════════════════════════════════════════════════
# GUI PRINCIPALE — TKINTER
# ══════════════════════════════════════════════════════════════════════════════
class ImperiumApp:
    # ── init ─────────────────────────────────────────────────────────────────
    def __init__(self, root: tk.Tk):
        self.root = root
        self.root.title("Imperium")
        self.root.configure(bg=th("bg"))
        self.root.geometry("900x640")
        self.root.minsize(700, 480)

        # State
        self.cfg     = ConfigManager()
        self.metrics = Metrics()
        self.overlay = ProfileOverlay()
        self.engine  = ActionEngine(self.cfg, self._on_profile_changed)
        self.transport = Transport(self._on_serial)
        self._metrics_data = {}
        self._log_lines = []
        self._active_view = "device"
        self._btn_frames = {}   # btn index → Frame widget
        self._pot_frames = {}
        self._led_frames = {}
        self._selected_btn = None
        self._selected_pot = None

        self._build_ui()
        self._start_metrics_loop()
        self.transport.start(self.cfg.data.get("serial_port","AUTO"))
        self._refresh_device()

    # ── UI GLOBALE ────────────────────────────────────────────────────────────
    def _build_ui(self):
        # Sidebar
        sb = tk.Frame(self.root, bg=th("bg1"), width=46)
        sb.pack(side="left", fill="y"); sb.pack_propagate(False)
        self._sb = sb

        # Contenu principal
        self._content = tk.Frame(self.root, bg=th("bg"))
        self._content.pack(side="left", fill="both", expand=True)

        # Topbar
        top = tk.Frame(self._content, bg=th("bg1"), height=38)
        top.pack(fill="x"); top.pack_propagate(False)
        self._lbl_title = tk.Label(top, text="Imperium", fg=th("text"), bg=th("bg1"),
            font=("Segoe UI", 11, "bold"))
        self._lbl_title.pack(side="left", padx=14)
        self._lbl_profile = tk.Label(top, text="", fg=th("accent"), bg=th("bg1"),
            font=("Segoe UI", 9))
        self._lbl_profile.pack(side="left", padx=4)
        self._lbl_time = tk.Label(top, text="", fg=th("text3"), bg=th("bg1"),
            font=("Segoe UI", 9))
        self._lbl_time.pack(side="right", padx=12)

        # Views
        self._views = {}
        for name in ("device","metrics","profiles","settings","log"):
            f = tk.Frame(self._content, bg=th("bg"))
            self._views[name] = f

        self._build_sidebar()
        self._build_device()
        self._build_metrics()
        self._build_profiles()
        self._build_settings()
        self._build_log()
        self._switch_view("device")
        self._update_profile_label()

    def _build_sidebar(self):
        TABS = [("🎛","device","Device"),("📊","metrics","Métriques"),
                ("◈","profiles","Profils"),("⚙","settings","Paramètres"),("📋","log","Journal")]
        self._sb_btns = {}
        tk.Frame(self._sb, bg=th("bg1"), height=8).pack()
        for icon, name, tip in TABS:
            btn = tk.Label(self._sb, text=icon, bg=th("bg1"), fg=th("text3"),
                font=("Segoe UI Emoji", 15), cursor="hand2", width=2, pady=6)
            btn.pack()
            btn.bind("<Button-1>", lambda e, n=name: self._switch_view(n))
            btn.bind("<Enter>", lambda e, b=btn: b.configure(fg=th("text")))
            btn.bind("<Leave>", lambda e, b=btn, n=name: b.configure(fg=th("accent") if self._active_view==n else th("text3")))
            self._sb_btns[name] = btn
        tk.Frame(self._sb, bg=th("border"), height=1).pack(fill="x", padx=6, pady=6)

    def _switch_view(self, name):
        for n, f in self._views.items(): f.pack_forget()
        self._views[name].pack(fill="both", expand=True, padx=0, pady=0)
        self._active_view = name
        for n, b in self._sb_btns.items():
            b.configure(fg=th("accent") if n==name else th("text3"))
        if name == "metrics": self._refresh_metrics_ui()
        if name == "profiles": self._refresh_profiles()
        if name == "device": self._refresh_device()

    # ── DEVICE VIEW ──────────────────────────────────────────────────────────
    def _build_device(self):
        f = self._views["device"]
        top = tk.Frame(f, bg=th("bg")); top.pack(fill="x", padx=14, pady=(10,0))
        tk.Label(top, text="Device", fg=th("text"), bg=th("bg"), font=("Segoe UI",12,"bold")).pack(side="left")
        self._serial_dot = tk.Canvas(top, width=10, height=10, bg=th("bg"), highlightthickness=0)
        self._serial_dot.pack(side="right", padx=(0,4))
        self._serial_lbl = tk.Label(top, text="Déconnecté", fg=th("text3"), bg=th("bg"), font=("Segoe UI",9))
        self._serial_lbl.pack(side="right")

        # Scroll
        canvas = tk.Canvas(f, bg=th("bg"), highlightthickness=0)
        canvas.pack(fill="both", expand=True, padx=0, pady=0)
        inner = tk.Frame(canvas, bg=th("bg"))
        canvas.create_window((0,0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        self._device_inner = inner

    def _refresh_device(self):
        f = self._device_inner
        for w in f.winfo_children(): w.destroy()
        self._btn_frames.clear(); self._pot_frames.clear(); self._led_frames.clear()

        # ── Boutons ──
        tk.Label(f, text="Boutons", fg=th("text2"), bg=th("bg"),
            font=("Segoe UI",10,"bold")).pack(anchor="w", padx=14, pady=(12,6))
        btn_grid = tk.Frame(f, bg=th("bg")); btn_grid.pack(padx=14)
        profile = self.cfg.active()
        for i in range(8):
            r, c = divmod(i, 4)
            b = profile["buttons"].get(str(i), {})
            cell = self._make_btn_card(btn_grid, i, b)
            cell.grid(row=r, column=c, padx=5, pady=5)
            self._btn_frames[i] = cell

        # ── Potards ──
        tk.Label(f, text="Potentiomètres", fg=th("text2"), bg=th("bg"),
            font=("Segoe UI",10,"bold")).pack(anchor="w", padx=14, pady=(14,6))
        pot_row = tk.Frame(f, bg=th("bg")); pot_row.pack(padx=14)
        for i in range(4):
            p = profile["pots"].get(str(i), {})
            cell = self._make_pot_card(pot_row, i, p)
            cell.pack(side="left", padx=5)
            self._pot_frames[i] = cell

        # ── LED strips ──
        tk.Label(f, text="LED Strips", fg=th("text2"), bg=th("bg"),
            font=("Segoe UI",10,"bold")).pack(anchor="w", padx=14, pady=(14,6))
        led_frame = tk.Frame(f, bg=th("bg")); led_frame.pack(padx=14, fill="x")
        metrics_keys = ["cpu","ram","gpu_usage","ssd_usage"]
        metrics_lbl  = ["CPU","RAM","GPU","SSD"]
        strips_cfg = self.cfg.data.get("led_strips",{})
        for i in range(4):
            key = strips_cfg.get(str(i),{}).get("metric", metrics_keys[i])
            val = int(self._metrics_data.get(key,0) or 0)
            cell = self._make_led_strip(led_frame, i, val, key, metrics_lbl)
            cell.pack(fill="x", pady=3)
            self._led_frames[i] = cell

    def _make_btn_card(self, parent, idx, btn_data):
        frame = tk.Frame(parent, bg=th("card"), width=96, height=86,
            relief="flat", bd=0, cursor="hand2")
        frame.pack_propagate(False)
        # Numéro
        tk.Label(frame, text=str(idx+1), fg=th("text4"), bg=th("card"),
            font=("Segoe UI",7)).place(x=5,y=4)
        # Icône
        icon = btn_data.get("icon","⭐") or "⭐"
        lbl_icon = tk.Label(frame, text=icon, fg=th("text"), bg=th("card"),
            font=("Segoe UI Emoji",20))
        lbl_icon.place(relx=.5, rely=.38, anchor="center")
        # Label
        label = (btn_data.get("label") or f"Bouton {idx+1}")[:12]
        tk.Label(frame, text=label, fg=th("text3"), bg=th("card"),
            font=("Segoe UI",7), wraplength=80).place(relx=.5, rely=.78, anchor="center")
        # Nombre d'actions
        n_actions = len(btn_data.get("press",[]))
        if n_actions:
            tk.Label(frame, text=str(n_actions), fg=th("accent"), bg=th("card"),
                font=("Segoe UI",7,"bold")).place(x=74,y=4)
        # Clic → éditeur
        for w in (frame, lbl_icon):
            w.bind("<Button-1>", lambda e, i=idx: self._open_btn_editor(i))
        return frame

    def _make_pot_card(self, parent, idx, pot_data):
        frame = tk.Frame(parent, bg=th("card"), width=96, height=96, cursor="hand2")
        frame.pack_propagate(False)
        r=28; circ=2*3.14159*r
        cv=tk.Canvas(frame,width=64,height=64,bg=th("card"),highlightthickness=0)
        cv.place(relx=.5,rely=.4,anchor="center")
        cv.create_oval(3,3,61,61,fill=th("bg3"),outline=th("border"),width=2)
        cv.create_oval(10,10,54,54,fill=th("bg"),outline=th("border"),width=1)
        cv.create_oval(29,29,35,35,fill=th("accent"),outline="")
        name=(pot_data.get("name") or f"Pot {idx+1}")[:9]
        tk.Label(frame,text=name,fg=th("text3"),bg=th("card"),font=("Segoe UI",7)).place(relx=.5,rely=.86,anchor="center")
        frame.bind("<Button-1>", lambda e,i=idx: self._open_pot_editor(i))
        cv.bind("<Button-1>",    lambda e,i=idx: self._open_pot_editor(i))
        return frame

    def _make_led_strip(self, parent, idx, val, metric_key, labels):
        frame = tk.Frame(parent, bg=th("bg4"), height=32)
        # Couleur selon valeur
        if val < 33: color = "#22c55e"
        elif val < 66: color = "#f59e0b"
        else: color = "#ef4444"
        bar = tk.Frame(frame, bg=color, height=32)
        bar.place(x=0,y=0,relwidth=val/100)
        key_lbl = metric_key.upper().replace("_USAGE","").replace("_","/")
        tk.Label(frame,text=f"  {key_lbl}",fg=th("text"),bg=th("bg4"),font=("Segoe UI",9,"bold")).place(x=8,rely=.5,anchor="w")
        tk.Label(frame,text=f"{val}%",fg=th("text2"),bg=th("bg4"),font=("Segoe UI",9)).place(relx=1,x=-10,rely=.5,anchor="e")
        return frame

    def _flash_btn(self, idx):
        if idx in self._btn_frames:
            f = self._btn_frames[idx]
            orig = th("card")
            f.configure(bg=th("accent"))
            self.root.after(120, lambda: f.configure(bg=orig))

    # ── ÉDITEUR BOUTON ────────────────────────────────────────────────────────
    def _open_btn_editor(self, idx):
        profile = self.cfg.active()
        btn = profile["buttons"].get(str(idx), {})

        win = tk.Toplevel(self.root); win.title(f"Bouton {idx+1}"); win.geometry("520x560")
        win.configure(bg=th("bg")); win.grab_set()

        tk.Label(win, text=f"Bouton {idx+1} — {profile.get('name','')}",
            fg=th("text"), bg=th("bg"), font=("Segoe UI",11,"bold")).pack(pady=(12,0))

        nb = ttk.Notebook(win); nb.pack(fill="both", expand=True, padx=12, pady=8)
        style = ttk.Style(); style.theme_use("default")
        style.configure("TNotebook", background=th("bg"), borderwidth=0)
        style.configure("TNotebook.Tab", background=th("bg3"), foreground=th("text3"),
            padding=[10,4], font=("Segoe UI",9))
        style.map("TNotebook.Tab", background=[("selected",th("card"))], foreground=[("selected",th("text"))])

        for ev_key, ev_label in [("press","Appui"),("long_press","Appui long"),("double_click","Double clic")]:
            tab = tk.Frame(nb, bg=th("bg")); nb.add(tab, text=ev_label)
            self._build_action_editor(tab, idx, ev_key, btn.get(ev_key,[]), profile, win)

        # Icône et label
        info_frame = tk.Frame(nb, bg=th("bg")); nb.add(info_frame, text="Apparence")
        tk.Label(info_frame, text="Icône (emoji):", fg=th("text2"), bg=th("bg"),
            font=("Segoe UI",9)).pack(anchor="w", padx=12, pady=(12,2))
        icon_var = tk.StringVar(value=btn.get("icon","⭐"))
        icon_entry = tk.Entry(info_frame, textvariable=icon_var, bg=th("bg3"), fg=th("text"),
            insertbackground=th("text"), font=("Segoe UI Emoji",14), width=6,
            relief="flat", bd=4)
        icon_entry.pack(anchor="w", padx=12)
        tk.Label(info_frame, text="Label:", fg=th("text2"), bg=th("bg"),
            font=("Segoe UI",9)).pack(anchor="w", padx=12, pady=(10,2))
        lbl_var = tk.StringVar(value=btn.get("label",f"Bouton {idx+1}"))
        tk.Entry(info_frame, textvariable=lbl_var, bg=th("bg3"), fg=th("text"),
            insertbackground=th("text"), font=("Segoe UI",10), relief="flat", bd=4).pack(anchor="w", padx=12, fill="x")

        def _save():
            profile["buttons"][str(idx)]["icon"] = icon_var.get()
            profile["buttons"][str(idx)]["label"] = lbl_var.get()
            self.cfg.save(); self._refresh_device(); win.destroy()

        tk.Button(win, text="💾 Enregistrer", command=_save, bg=th("accent"), fg="white",
            font=("Segoe UI",10,"bold"), relief="flat", bd=0, pady=6, cursor="hand2").pack(fill="x", padx=12, pady=8)

    def _build_action_editor(self, tab, btn_idx, ev_key, actions, profile, parent_win):
        """Liste des actions pour un event (press/long/double), avec ajout/suppression."""
        lf = tk.Frame(tab, bg=th("bg")); lf.pack(fill="both", expand=True, padx=8, pady=8)

        act_list = tk.Frame(lf, bg=th("bg")); act_list.pack(fill="both", expand=True)

        def refresh_list():
            for w in act_list.winfo_children(): w.destroy()
            acts = profile["buttons"][str(btn_idx)].get(ev_key,[])
            if not acts:
                tk.Label(act_list, text="Aucune action", fg=th("text4"), bg=th("bg"),
                    font=("Segoe UI",9,"italic")).pack(pady=20)
            for j, act in enumerate(acts):
                row = tk.Frame(act_list, bg=th("card")); row.pack(fill="x", pady=2)
                info = next((a for a in ALL_ACTIONS if a["type"]==act.get("type")), None)
                icon = info["icon"] if info else "?"
                name = info["name"] if info else act.get("type","?")
                tk.Label(row, text=f"{icon} {name}", fg=th("text"), bg=th("card"),
                    font=("Segoe UI",9), anchor="w").pack(side="left", padx=8, pady=6, fill="x", expand=True)
                tk.Button(row, text="✕", fg=th("red"), bg=th("card"), relief="flat", bd=0,
                    cursor="hand2", font=("Segoe UI",10),
                    command=lambda j_=j: _remove(j_)).pack(side="right", padx=6)

        def _remove(j):
            profile["buttons"][str(btn_idx)][ev_key].pop(j)
            self.cfg.save(); refresh_list()

        def _add_action():
            self._action_picker(lambda a: _on_picked(a))

        def _on_picked(act_def):
            # Collecte les params
            params = {}
            for p in act_def.get("params",[]):
                params[p["key"]] = p.get("ph","")
            action = {"type": act_def["type"]}
            action.update(params)
            if ev_key not in profile["buttons"][str(btn_idx)]:
                profile["buttons"][str(btn_idx)][ev_key] = []
            profile["buttons"][str(btn_idx)][ev_key].append(action)
            self.cfg.save(); refresh_list()

        refresh_list()
        tk.Button(lf, text="+ Ajouter une action", command=_add_action,
            bg=th("bg3"), fg=th("accent"), font=("Segoe UI",9,"bold"),
            relief="flat", bd=0, pady=5, cursor="hand2").pack(fill="x", pady=(6,0))

        def _test():
            acts = profile["buttons"][str(btn_idx)].get(ev_key,[])
            threading.Thread(target=self.engine.run, args=(acts,), daemon=True).start()
            self._toast(f"Test : {ev_key}")

        tk.Button(lf, text="▶ Tester", command=_test,
            bg=th("bg4"), fg=th("text2"), font=("Segoe UI",9),
            relief="flat", bd=0, pady=4, cursor="hand2").pack(fill="x", pady=(3,0))

    def _action_picker(self, callback):
        """Fenêtre de sélection d'action par catégorie."""
        win = tk.Toplevel(self.root); win.title("Choisir une action")
        win.geometry("480x500"); win.configure(bg=th("bg")); win.grab_set()

        tk.Label(win, text="Choisir une action", fg=th("text"), bg=th("bg"),
            font=("Segoe UI",11,"bold")).pack(pady=(12,6))

        search_var = tk.StringVar()
        tk.Entry(win, textvariable=search_var, bg=th("bg3"), fg=th("text"),
            insertbackground=th("text"), font=("Segoe UI",10),
            relief="flat", bd=6, placeholder_text="Rechercher…").pack(fill="x", padx=12)

        canvas = tk.Canvas(win, bg=th("bg"), highlightthickness=0)
        sb = tk.Scrollbar(win, orient="vertical", command=canvas.yview)
        canvas.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y"); canvas.pack(fill="both", expand=True, padx=12, pady=6)
        inner = tk.Frame(canvas, bg=th("bg")); canvas.create_window((0,0), window=inner, anchor="nw")
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))

        def render(q=""):
            for w in inner.winfo_children(): w.destroy()
            cats = {}
            for a in ALL_ACTIONS:
                if q and q.lower() not in a["name"].lower() and q.lower() not in a["cat"].lower(): continue
                cats.setdefault(a["cat"],[]).append(a)
            for cat, acts in sorted(cats.items()):
                tk.Label(inner, text=cat, fg=th("accent"), bg=th("bg"),
                    font=("Segoe UI",9,"bold")).pack(anchor="w", pady=(8,2))
                for a in acts:
                    row = tk.Frame(inner, bg=th("card"), cursor="hand2")
                    row.pack(fill="x", pady=1)
                    tk.Label(row, text=f"{a['icon']} {a['name']}", fg=th("text"), bg=th("card"),
                        font=("Segoe UI",9), anchor="w").pack(side="left", padx=8, pady=5)
                    tk.Label(row, text=a.get("desc",""), fg=th("text3"), bg=th("card"),
                        font=("Segoe UI",8)).pack(side="left", padx=4)
                    row.bind("<Button-1>", lambda e, a_=a: (win.destroy(), _open_params(a_)))
                    for child in row.winfo_children():
                        child.bind("<Button-1>", lambda e, a_=a: (win.destroy(), _open_params(a_)))

        def _open_params(act_def):
            if not act_def.get("params"):
                callback(act_def); return
            pw = tk.Toplevel(self.root); pw.title(act_def["name"])
            pw.geometry("360x300"); pw.configure(bg=th("bg")); pw.grab_set()
            tk.Label(pw, text=f"{act_def['icon']} {act_def['name']}", fg=th("text"), bg=th("bg"),
                font=("Segoe UI",11,"bold")).pack(pady=(12,8))
            entries = {}
            for p in act_def["params"]:
                tk.Label(pw, text=p["lbl"]+":", fg=th("text2"), bg=th("bg"),
                    font=("Segoe UI",9)).pack(anchor="w", padx=16)
                var = tk.StringVar(value=p.get("ph",""))
                if p.get("multi"):
                    t = tk.Text(pw, bg=th("bg3"), fg=th("text"), insertbackground=th("text"),
                        font=("Segoe UI",9), height=5, relief="flat", bd=4)
                    t.insert("1.0", p.get("ph",""))
                    t.pack(fill="x", padx=16, pady=(0,6))
                    entries[p["key"]] = ("text", t)
                else:
                    e = tk.Entry(pw, textvariable=var, bg=th("bg3"), fg=th("text"),
                        insertbackground=th("text"), font=("Segoe UI",10), relief="flat", bd=4)
                    e.pack(fill="x", padx=16, pady=(0,6))
                    entries[p["key"]] = ("var", var)
            def _confirm():
                built = dict(act_def)
                built["params"] = []
                for key,(kind,widget) in entries.items():
                    val = widget.get("1.0","end-1c") if kind=="text" else widget.get()
                    built[key] = val
                    built.setdefault("params",[])
                pw.destroy(); callback(built)
            tk.Button(pw, text="✅ Confirmer", command=_confirm, bg=th("accent"), fg="white",
                font=("Segoe UI",10,"bold"), relief="flat", bd=0, pady=6, cursor="hand2").pack(fill="x", padx=16, pady=8)

        search_var.trace_add("write", lambda *_: render(search_var.get()))
        render()

    # ── ÉDITEUR POTARD ────────────────────────────────────────────────────────
    def _open_pot_editor(self, idx):
        profile = self.cfg.active()
        pot = profile["pots"].get(str(idx), {})
        win = tk.Toplevel(self.root); win.title(f"Potard {idx+1}")
        win.geometry("360x280"); win.configure(bg=th("bg")); win.grab_set()

        tk.Label(win, text=f"Potard {idx+1}", fg=th("text"), bg=th("bg"),
            font=("Segoe UI",11,"bold")).pack(pady=(12,8))

        tk.Label(win, text="Nom:", fg=th("text2"), bg=th("bg"), font=("Segoe UI",9)).pack(anchor="w",padx=16)
        name_var = tk.StringVar(value=pot.get("name",f"Pot {idx+1}"))
        tk.Entry(win, textvariable=name_var, bg=th("bg3"), fg=th("text"),
            insertbackground=th("text"), font=("Segoe UI",10), relief="flat", bd=4).pack(fill="x",padx=16,pady=(0,8))

        tk.Label(win, text="Action:", fg=th("text2"), bg=th("bg"), font=("Segoe UI",9)).pack(anchor="w",padx=16)
        action_var = tk.StringVar(value=pot.get("action","volume_system"))
        sel = ttk.Combobox(win, textvariable=action_var, state="readonly",
            values=[k for k,_ in POT_ACTIONS], font=("Segoe UI",10))
        sel["values"] = [f"{lbl}" for _,lbl in POT_ACTIONS]
        # Map display → key
        pot_map = {lbl:k for k,lbl in POT_ACTIONS}
        cur_lbl = next((l for k,l in POT_ACTIONS if k==pot.get("action","volume_system")), POT_ACTIONS[0][1])
        action_var.set(cur_lbl)
        sel.pack(fill="x",padx=16,pady=(0,8))

        # App (si volume_app)
        tk.Label(win, text="Appli cible (si vol.app):", fg=th("text2"), bg=th("bg"),
            font=("Segoe UI",9)).pack(anchor="w",padx=16)
        app_var = tk.StringVar(value=pot.get("app",""))
        tk.Entry(win, textvariable=app_var, bg=th("bg3"), fg=th("text"),
            insertbackground=th("text"), font=("Segoe UI",10), relief="flat", bd=4).pack(fill="x",padx=16,pady=(0,8))

        def _save():
            profile["pots"][str(idx)]["name"] = name_var.get()
            profile["pots"][str(idx)]["action"] = pot_map.get(action_var.get(), "volume_system")
            profile["pots"][str(idx)]["app"] = app_var.get()
            self.cfg.save(); self._refresh_device(); win.destroy()

        tk.Button(win, text="💾 Enregistrer", command=_save, bg=th("accent"), fg="white",
            font=("Segoe UI",10,"bold"), relief="flat", bd=0, pady=6, cursor="hand2").pack(fill="x",padx=16,pady=8)

    # ── MÉTRIQUES ─────────────────────────────────────────────────────────────
    def _build_metrics(self):
        f = self._views["metrics"]
        tk.Label(f, text="Métriques système", fg=th("text"), bg=th("bg"),
            font=("Segoe UI",12,"bold")).pack(anchor="w", padx=14, pady=(12,8))
        self._metrics_frame = tk.Frame(f, bg=th("bg")); self._metrics_frame.pack(fill="both", expand=True, padx=14)

    def _refresh_metrics_ui(self):
        m = self._metrics_data
        if not m: return
        f = self._metrics_frame
        for w in f.winfo_children(): w.destroy()

        def card(label, value, unit="", color=th("text"), sub=""):
            c = tk.Frame(f, bg=th("card"), width=160, height=80); c.pack_propagate(False)
            tk.Label(c, text=label, fg=th("text3"), bg=th("card"), font=("Segoe UI",8)).pack(anchor="w",padx=10,pady=(8,0))
            tk.Label(c, text=f"{value}{unit}", fg=color, bg=th("card"), font=("Segoe UI",18,"bold")).pack(anchor="w",padx=10)
            if sub: tk.Label(c, text=sub, fg=th("text4"), bg=th("card"), font=("Segoe UI",7)).pack(anchor="w",padx=10)
            return c

        def color_pct(v):
            try: v=float(v)
            except: return th("text")
            if v<50: return th("green")
            if v<80: return th("yellow")
            return th("red")

        grid = tk.Frame(f, bg=th("bg")); grid.pack(fill="x")
        items = [
            ("CPU", f"{m.get('cpu',0):.0f}", "%", color_pct(m.get('cpu',0)), f"{m.get('cpu_freq',0):.0f} MHz — {m.get('cpu_cores',0)} cœurs"),
            ("RAM", f"{m.get('ram',0):.0f}", "%", color_pct(m.get('ram',0)), f"{m.get('ram_used_gb',0)} / {m.get('ram_total_gb',0)} GB"),
            ("GPU", f"{m.get('gpu_usage',0):.0f}", "%", color_pct(m.get('gpu_usage',0)), m.get('gpu_name','')[:22]),
            ("VRAM", f"{m.get('gpu_vram',0):.0f}", "%", color_pct(m.get('gpu_vram',0)), ""),
            ("SSD", f"{m.get('ssd_usage',0):.0f}", "%", color_pct(m.get('ssd_usage',0)), ""),
            ("↑ Réseau", f"{m.get('net_up',0)}", " KB/s", th("text2"), ""),
            ("↓ Réseau", f"{m.get('net_down',0)}", " KB/s", th("text2"), ""),
            ("Volume", f"{m.get('volume',0)}", "%", th("text2"), "🔇" if m.get("muted") else ""),
        ]
        for i, (lbl, val, unit, col, sub) in enumerate(items):
            c = card(lbl, val, unit, col, sub)
            c.grid(row=i//4, column=i%4, padx=5, pady=5, in_=grid)

        # Top processus
        tk.Label(f, text="Top processus", fg=th("text2"), bg=th("bg"),
            font=("Segoe UI",10,"bold")).pack(anchor="w", pady=(12,4))
        for p in m.get("top_processes",[]):
            row = tk.Frame(f, bg=th("card")); row.pack(fill="x", pady=1)
            tk.Label(row, text=p["name"], fg=th("text"), bg=th("card"), font=("Segoe UI",9), width=24, anchor="w").pack(side="left",padx=8,pady=4)
            tk.Label(row, text=f"CPU {p['cpu']}%", fg=color_pct(p['cpu']), bg=th("card"), font=("Segoe UI",9)).pack(side="left",padx=4)
            tk.Label(row, text=f"MEM {p['mem']:.1f}%", fg=th("text3"), bg=th("card"), font=("Segoe UI",9)).pack(side="left",padx=4)

    # ── PROFILS ───────────────────────────────────────────────────────────────
    def _build_profiles(self):
        f = self._views["profiles"]
        top = tk.Frame(f, bg=th("bg")); top.pack(fill="x", padx=14, pady=(12,6))
        tk.Label(top, text="Profils", fg=th("text"), bg=th("bg"), font=("Segoe UI",12,"bold")).pack(side="left")
        tk.Button(top, text="+ Nouveau", command=self._new_profile,
            bg=th("accent"), fg="white", font=("Segoe UI",9,"bold"),
            relief="flat", bd=0, padx=10, pady=4, cursor="hand2").pack(side="right")
        self._profiles_frame = tk.Frame(f, bg=th("bg"))
        self._profiles_frame.pack(fill="both", expand=True, padx=14)

    def _refresh_profiles(self):
        f = self._profiles_frame
        for w in f.winfo_children(): w.destroy()
        active = self.cfg.data.get("active_profile","default")
        for key, profile in self.cfg.data["profiles"].items():
            is_active = (key == active)
            row = tk.Frame(f, bg=th("card") if is_active else th("bg3"))
            row.pack(fill="x", pady=4)
            # Indicateur actif
            dot = tk.Canvas(row, width=8, height=8, bg=row.cget("bg"), highlightthickness=0)
            dot.pack(side="left", padx=8, pady=14)
            dot.create_oval(0,0,8,8, fill=th("accent") if is_active else th("border"), outline="")
            tk.Label(row, text=profile.get("name",key), fg=th("text") if is_active else th("text2"),
                bg=row.cget("bg"), font=("Segoe UI",10,"bold" if is_active else "normal")).pack(side="left",pady=8)
            if is_active:
                tk.Label(row, text="ACTIF", fg=th("accent"), bg=row.cget("bg"),
                    font=("Segoe UI",7,"bold")).pack(side="left",padx=8)
            # Boutons
            if not is_active:
                tk.Button(row, text="Activer", command=lambda k=key: self._set_profile(k),
                    bg=th("accent"), fg="white", font=("Segoe UI",8),
                    relief="flat", bd=0, padx=8, pady=3, cursor="hand2").pack(side="right",padx=4,pady=6)
            if key != "default":
                tk.Button(row, text="🗑", fg=th("red"), bg=row.cget("bg"), relief="flat", bd=0,
                    cursor="hand2", font=("Segoe UI",12),
                    command=lambda k=key: self._delete_profile(k)).pack(side="right",padx=4)
            tk.Button(row, text="✏", fg=th("text3"), bg=row.cget("bg"), relief="flat", bd=0,
                cursor="hand2", font=("Segoe UI",12),
                command=lambda k=key, p=profile: self._rename_profile(k,p)).pack(side="right",padx=2)

    def _set_profile(self, key):
        self.cfg.data["active_profile"] = key
        self.cfg.save()
        self._on_profile_changed(key)
        self._refresh_profiles()

    def _new_profile(self):
        win = tk.Toplevel(self.root); win.title("Nouveau profil")
        win.geometry("300x160"); win.configure(bg=th("bg")); win.grab_set()
        tk.Label(win, text="Nom du profil:", fg=th("text2"), bg=th("bg"),
            font=("Segoe UI",9)).pack(padx=16, pady=(16,4), anchor="w")
        var = tk.StringVar()
        tk.Entry(win, textvariable=var, bg=th("bg3"), fg=th("text"),
            insertbackground=th("text"), font=("Segoe UI",10), relief="flat", bd=4).pack(fill="x", padx=16)
        def _ok():
            name = var.get().strip()
            if not name: return
            key = name.lower().replace(" ","_")
            if key not in self.cfg.data["profiles"]:
                self.cfg.data["profiles"][key] = empty_profile(name)
                self.cfg.save(); self._refresh_profiles()
            win.destroy()
        tk.Button(win, text="Créer", command=_ok, bg=th("accent"), fg="white",
            font=("Segoe UI",10,"bold"), relief="flat", bd=0, pady=6, cursor="hand2").pack(fill="x", padx=16, pady=12)

    def _rename_profile(self, key, profile):
        win = tk.Toplevel(self.root); win.title("Renommer")
        win.geometry("300x140"); win.configure(bg=th("bg")); win.grab_set()
        var = tk.StringVar(value=profile.get("name",key))
        tk.Entry(win, textvariable=var, bg=th("bg3"), fg=th("text"),
            insertbackground=th("text"), font=("Segoe UI",10), relief="flat", bd=4).pack(fill="x", padx=16, pady=16)
        def _ok():
            self.cfg.data["profiles"][key]["name"] = var.get().strip()
            self.cfg.save(); self._refresh_profiles(); win.destroy()
        tk.Button(win, text="OK", command=_ok, bg=th("accent"), fg="white",
            font=("Segoe UI",10,"bold"), relief="flat", bd=0, pady=6, cursor="hand2").pack(fill="x", padx=16)

    def _delete_profile(self, key):
        if messagebox.askyesno("Supprimer", f"Supprimer le profil « {key} » ?", parent=self.root):
            del self.cfg.data["profiles"][key]
            if self.cfg.data.get("active_profile") == key:
                self.cfg.data["active_profile"] = "default"
            self.cfg.save(); self._refresh_profiles()

    # ── PARAMÈTRES ────────────────────────────────────────────────────────────
    def _build_settings(self):
        f = self._views["settings"]
        tk.Label(f, text="Paramètres", fg=th("text"), bg=th("bg"),
            font=("Segoe UI",12,"bold")).pack(anchor="w", padx=14, pady=(12,8))

        nb = ttk.Notebook(f); nb.pack(fill="both", expand=True, padx=12)
        style = ttk.Style(); style.theme_use("default")
        style.configure("TNotebook", background=th("bg"), borderwidth=0)
        style.configure("TNotebook.Tab", background=th("bg3"), foreground=th("text3"),
            padding=[10,4], font=("Segoe UI",9))
        style.map("TNotebook.Tab", background=[("selected",th("card"))], foreground=[("selected",th("text"))])

        # ── Connexion série ──
        ser_tab = tk.Frame(nb, bg=th("bg")); nb.add(ser_tab, text="🔌 Connexion")

        tk.Label(ser_tab, text="Port série (AUTO = détection auto):", fg=th("text2"), bg=th("bg"),
            font=("Segoe UI",9)).pack(anchor="w", padx=12, pady=(12,2))
        port_var = tk.StringVar(value=self.cfg.data.get("serial_port","AUTO"))
        port_entry = tk.Entry(ser_tab, textvariable=port_var, bg=th("bg3"), fg=th("text"),
            insertbackground=th("text"), font=("Segoe UI",10), relief="flat", bd=4)
        port_entry.pack(fill="x", padx=12, pady=(0,6))

        tk.Label(ser_tab, text="Baud rate:", fg=th("text2"), bg=th("bg"), font=("Segoe UI",9)).pack(anchor="w", padx=12)
        baud_var = tk.StringVar(value=str(self.cfg.data.get("baud_rate",115200)))
        tk.Entry(ser_tab, textvariable=baud_var, bg=th("bg3"), fg=th("text"),
            insertbackground=th("text"), font=("Segoe UI",10), relief="flat", bd=4).pack(fill="x", padx=12, pady=(0,8))

        self._serial_status_lbl = tk.Label(ser_tab, text="", fg=th("text3"), bg=th("bg"), font=("Segoe UI",9))
        self._serial_status_lbl.pack(anchor="w", padx=12)

        def _connect():
            port = port_var.get().strip()
            baud = int(baud_var.get() or 115200)
            self.cfg.data["serial_port"] = port
            self.cfg.data["baud_rate"] = baud
            self.cfg.save()
            self.transport.start(port, baud=baud, slot=0)
            self.root.after(800, self._update_serial_status)

        def _refresh_ports():
            if SERIAL_OK:
                ports = [p.device for p in serial.tools.list_ports.comports()]
                port_var.set(ports[0] if ports else "AUTO")

        btns = tk.Frame(ser_tab, bg=th("bg")); btns.pack(fill="x", padx=12, pady=8)
        tk.Button(btns, text="🔌 Connecter", command=_connect, bg=th("accent"), fg="white",
            font=("Segoe UI",9,"bold"), relief="flat", bd=0, padx=12, pady=5, cursor="hand2").pack(side="left",padx=(0,8))
        tk.Button(btns, text="🔍 Scanner", command=_refresh_ports, bg=th("bg3"), fg=th("text2"),
            font=("Segoe UI",9), relief="flat", bd=0, padx=10, pady=5, cursor="hand2").pack(side="left")

        # ── Overlay ──
        ov_tab = tk.Frame(nb, bg=th("bg")); nb.add(ov_tab, text="🪟 Overlay")
        ov_cfg = self.cfg.data.get("overlay",{})

        def ov_row(label, key, default, kind="int"):
            row = tk.Frame(ov_tab, bg=th("bg")); row.pack(fill="x", padx=12, pady=3)
            tk.Label(row, text=label, fg=th("text2"), bg=th("bg"),
                font=("Segoe UI",9), width=20, anchor="w").pack(side="left")
            var = tk.StringVar(value=str(ov_cfg.get(key,default)))
            tk.Entry(row, textvariable=var, bg=th("bg3"), fg=th("text"),
                insertbackground=th("text"), font=("Segoe UI",10),
                relief="flat", bd=4, width=8).pack(side="left")
            return var

        tk.Label(ov_tab, text="Configuration de l'overlay profil", fg=th("text3"), bg=th("bg"),
            font=("Segoe UI",9,"italic")).pack(anchor="w", padx=12, pady=(12,8))
        v_cell  = ov_row("Taille cellule (px)", "cell_size", 56)
        v_delay = ov_row("Durée affichage (s)", "delay", 3)
        v_alpha = ov_row("Opacité (20-100)", "alpha", 97)

        tk.Label(ov_tab, text="Position:", fg=th("text2"), bg=th("bg"),
            font=("Segoe UI",9)).pack(anchor="w", padx=12, pady=(6,2))
        pos_var = tk.StringVar(value=ov_cfg.get("position","br"))
        pos_sel = ttk.Combobox(ov_tab, textvariable=pos_var, state="readonly",
            values=["br","bl","tr","tl"], font=("Segoe UI",10))
        pos_sel.pack(anchor="w", padx=12, pady=(0,8))

        def _save_overlay():
            self.cfg.data["overlay"] = {
                "cell_size": int(v_cell.get() or 56),
                "delay": int(v_delay.get() or 3),
                "alpha": int(v_alpha.get() or 97),
                "position": pos_var.get(),
            }
            self.cfg.save()
            self._toast("Overlay sauvegardé")

        def _preview():
            key = self.cfg.data.get("active_profile","default")
            profile = self.cfg.data["profiles"].get(key)
            if profile: self.overlay.show(profile, self.cfg.data.get("overlay",{}))

        btns2 = tk.Frame(ov_tab, bg=th("bg")); btns2.pack(fill="x", padx=12, pady=6)
        tk.Button(btns2, text="💾 Sauvegarder", command=_save_overlay, bg=th("accent"), fg="white",
            font=("Segoe UI",9,"bold"), relief="flat", bd=0, padx=10, pady=5, cursor="hand2").pack(side="left", padx=(0,8))
        tk.Button(btns2, text="👁 Prévisualiser", command=_preview, bg=th("bg3"), fg=th("text2"),
            font=("Segoe UI",9), relief="flat", bd=0, padx=10, pady=5, cursor="hand2").pack(side="left")

        # ── Protocole ──
        proto_tab = tk.Frame(nb, bg=th("bg")); nb.add(proto_tab, text="📡 Protocole")
        proto = self.cfg.data.get("protocol",{})
        tk.Label(proto_tab, text="Patrons de trames série ({i}=index, {v}=valeur)",
            fg=th("text3"), bg=th("bg"), font=("Segoe UI",8,"italic")).pack(anchor="w", padx=12, pady=(12,8))

        proto_vars = {}
        for key, label, default in [
            ("in_press","Bouton ON","btn{i}:on"),
            ("in_release","Bouton OFF","btn{i}:off"),
            ("in_pot","Potard","pot{i}:{v}"),
            ("in_long_press","Long press (opt.)",""),
            ("in_double_click","Double clic (opt.)",""),
            ("out_led","LED (sortie)","led{i}:{v}"),
        ]:
            row = tk.Frame(proto_tab, bg=th("bg")); row.pack(fill="x", padx=12, pady=2)
            tk.Label(row, text=label+":", fg=th("text2"), bg=th("bg"),
                font=("Segoe UI",9), width=22, anchor="w").pack(side="left")
            var = tk.StringVar(value=proto.get(key,default))
            tk.Entry(row, textvariable=var, bg=th("bg3"), fg=th("text"),
                insertbackground=th("text"), font=("Consolas",10),
                relief="flat", bd=4).pack(side="left", fill="x", expand=True)
            proto_vars[key] = var

        def _save_proto():
            self.cfg.data["protocol"] = {k:v.get() for k,v in proto_vars.items()}
            self.cfg.save(); self._toast("Protocole sauvegardé")

        tk.Button(proto_tab, text="💾 Sauvegarder", command=_save_proto, bg=th("accent"), fg="white",
            font=("Segoe UI",9,"bold"), relief="flat", bd=0, padx=12, pady=5, cursor="hand2").pack(anchor="w", padx=12, pady=10)

        # ── MAJ ──
        upd_tab = tk.Frame(nb, bg=th("bg")); nb.add(upd_tab, text="🚀 Mises à jour")
        tk.Label(upd_tab, text=f"Version actuelle : {APP_VERSION}", fg=th("text3"), bg=th("bg"),
            font=("Segoe UI",9)).pack(anchor="w", padx=12, pady=(12,6))
        self._upd_status = tk.Label(upd_tab, text="", fg=th("text2"), bg=th("bg"), font=("Segoe UI",9))
        self._upd_status.pack(anchor="w", padx=12)
        self._upd_bar_frame = tk.Frame(upd_tab, bg=th("bg")); self._upd_bar_frame.pack(fill="x",padx=12,pady=4)

        def _check_update():
            self._upd_status.configure(text="⏳ Vérification…"); self.root.update_idletasks()
            def _do():
                import urllib.request, urllib.error
                REPO="tuturpotter-web/Imperium"
                try:
                    req=urllib.request.Request(f"https://api.github.com/repos/{REPO}/releases/latest",
                        headers={"User-Agent":"Imperium-updater"})
                    with urllib.request.urlopen(req,timeout=8) as r: data=json.loads(r.read())
                    latest=data.get("tag_name","").lstrip("v")
                    if latest and latest!=APP_VERSION:
                        asset=next((a for a in data.get("assets",[]) if a["name"].endswith(".exe")),None)
                        dl=asset["browser_download_url"] if asset else ""
                        self.root.after(0,lambda:self._upd_status.configure(text=f"🚀 MAJ disponible : {APP_VERSION} → {latest}",fg=th("yellow")))
                        if dl: self.root.after(0,lambda: self._show_download_btn(dl))
                    else:
                        self.root.after(0,lambda:self._upd_status.configure(text=f"✅ À jour ({APP_VERSION})",fg=th("green")))
                except Exception as e:
                    self.root.after(0,lambda:self._upd_status.configure(text=f"⚠ {e}",fg=th("red")))
            threading.Thread(target=_do,daemon=True).start()

        tk.Button(upd_tab, text="🔍 Vérifier les MAJ", command=_check_update,
            bg=th("accent"), fg="white", font=("Segoe UI",9,"bold"),
            relief="flat", bd=0, padx=12, pady=5, cursor="hand2").pack(anchor="w", padx=12, pady=6)

    def _show_download_btn(self, url):
        for w in self._upd_bar_frame.winfo_children(): w.destroy()
        def _dl():
            for w in self._upd_bar_frame.winfo_children(): w.destroy()
            pb = ttk.Progressbar(self._upd_bar_frame, length=300, mode="determinate")
            pb.pack(pady=4); lbl=tk.Label(self._upd_bar_frame,text="0%",fg=th("text2"),bg=th("bg"),font=("Segoe UI",8)); lbl.pack()
            def _do():
                import urllib.request, tempfile
                try:
                    fname=url.split("/")[-1]; tmp=os.path.join(tempfile.gettempdir(),fname)
                    def rep(bn,bs,fs):
                        pct=min(100,int(bn*bs/fs*100)) if fs>0 else 0
                        self.root.after(0,lambda p=pct:(pb.configure(value=p),lbl.configure(text=f"{p}%")))
                    urllib.request.urlretrieve(url,tmp,rep)
                    self.root.after(0,lambda:lbl.configure(text="✅ Installation…"))
                    self.root.after(500,lambda:(subprocess.Popen([tmp],creationflags=CREATE_NO_WINDOW),self.root.after(1000,lambda:os._exit(0))))
                except Exception as e:
                    self.root.after(0,lambda:lbl.configure(text=f"⚠ {e}",fg=th("red")))
            threading.Thread(target=_do,daemon=True).start()
        tk.Button(self._upd_bar_frame, text="⬇ Télécharger et installer", command=_dl,
            bg=th("yellow"), fg=th("bg"), font=("Segoe UI",9,"bold"),
            relief="flat", bd=0, padx=12, pady=5, cursor="hand2").pack(anchor="w")

    # ── JOURNAL ───────────────────────────────────────────────────────────────
    def _build_log(self):
        f = self._views["log"]
        top = tk.Frame(f, bg=th("bg")); top.pack(fill="x", padx=14, pady=(12,6))
        tk.Label(top, text="Journal d'événements", fg=th("text"), bg=th("bg"),
            font=("Segoe UI",12,"bold")).pack(side="left")
        tk.Button(top, text="🗑 Effacer", command=self._clear_log,
            bg=th("bg3"), fg=th("text3"), font=("Segoe UI",9),
            relief="flat", bd=0, padx=8, pady=3, cursor="hand2").pack(side="right")
        self._log_text = tk.Text(f, bg=th("bg3"), fg=th("text2"),
            font=("Consolas",9), relief="flat", bd=0, state="disabled", wrap="word")
        self._log_text.pack(fill="both", expand=True, padx=14, pady=(0,10))
        self._log_text.tag_configure("ts", foreground=th("text4"))
        self._log_text.tag_configure("rx", foreground=th("green"))
        self._log_text.tag_configure("tx", foreground=th("accent"))
        self._log_text.tag_configure("ev", foreground=th("yellow"))

    def _add_log(self, kind, text):
        t = self._log_text
        ts = datetime.datetime.now().strftime("%H:%M:%S")
        t.configure(state="normal")
        t.insert("end", f"[{ts}] ", "ts")
        t.insert("end", text+"\n", kind)
        t.see("end"); t.configure(state="disabled")

    def _clear_log(self):
        self._log_text.configure(state="normal")
        self._log_text.delete("1.0","end")
        self._log_text.configure(state="disabled")

    # ── TOAST ─────────────────────────────────────────────────────────────────
    def _toast(self, msg, ms=2500):
        try:
            if hasattr(self,"_toast_win") and self._toast_win.winfo_exists():
                self._toast_win.destroy()
        except: pass
        w = tk.Toplevel(self.root); w.overrideredirect(True)
        w.configure(bg=th("bg3"))
        w.attributes("-topmost", True)
        try: w.attributes("-alpha", 0.92)
        except: pass
        tk.Label(w, text=msg, fg=th("text"), bg=th("bg3"),
            font=("Segoe UI",9), padx=14, pady=6).pack()
        w.update_idletasks()
        rx = self.root.winfo_x() + self.root.winfo_width()//2 - w.winfo_width()//2
        ry = self.root.winfo_y() + self.root.winfo_height() - 60
        w.geometry(f"+{rx}+{ry}")
        self._toast_win = w
        self.root.after(ms, lambda: w.destroy() if w.winfo_exists() else None)

    # ── CALLBACKS ─────────────────────────────────────────────────────────────

    def _update_led_bars(self):
        """Met à jour les barres LED existantes sans les reconstruire."""
        m = self._metrics_data
        keys = ["cpu","ram","gpu_usage","ssd_usage"]
        strips_cfg = self.cfg.data.get("led_strips",{})
        for i, frame in self._led_frames.items():
            if not frame.winfo_exists(): continue
            key = strips_cfg.get(str(i),{}).get("metric", keys[i] if i<4 else "cpu")
            val = int(m.get(key,0) or 0)
            color = "#22c55e" if val<33 else ("#f59e0b" if val<66 else "#ef4444")
            key_lbl = key.upper().replace("_USAGE","").replace("_","/")
            # Détruire et recréer juste la bar (frame enfant)
            for child in frame.winfo_children():
                try: child.destroy()
                except: pass
            bar = tk.Frame(frame, bg=color, height=32)
            bar.place(x=0,y=0,relwidth=val/100)
            tk.Label(frame,text=f"  {key_lbl}",fg=th("text"),bg=th("bg4"),font=("Segoe UI",9,"bold")).place(x=8,rely=.5,anchor="w")
            tk.Label(frame,text=f"{val}%",fg=th("text2"),bg=th("bg4"),font=("Segoe UI",9)).place(relx=1,x=-10,rely=.5,anchor="e")

    def _on_profile_changed(self, key):
        self._update_profile_label()
        profile = self.cfg.data["profiles"].get(key)
        if profile: self.overlay.show(profile, self.cfg.data.get("overlay",{}))
        self._toast(f"Profil : {profile.get('name',key) if profile else key}")
        if self._active_view == "device": self._refresh_device()

    def _on_serial(self, raw, slot):
        proto = self.cfg.data.get("protocol",{})
        self._add_log("rx", f"[ESP32] {raw}")

        pat_pot = proto.get("in_pot","")
        if pat_pot:
            try:
                m = pattern_to_regex(pat_pot).match(raw)
                if m:
                    idx=int(m.group("i")); val=int(m.group("v"))
                    self.engine.run_pot(self.cfg.active()["pots"].get(str(idx),{}), val)
                    return
            except: pass

        pat_on  = proto.get("in_press","btn{i}:on")
        pat_off = proto.get("in_release","btn{i}:off")

        def _dispatch(idx, ev):
            actions = self.cfg.active()["buttons"].get(str(idx),{}).get(ev,[])
            if actions: threading.Thread(target=self.engine.run,args=(actions,),daemon=True).start()
            self._add_log("ev", f"BTN{idx} → {ev}")
            self.root.after(0, lambda: self._flash_btn(idx))

        if pat_on:
            try:
                m=pattern_to_regex(pat_on).match(raw)
                if m: self.transport._handle_timing(int(m.group("i")),"on",_dispatch); return
            except: pass
        if pat_off:
            try:
                m=pattern_to_regex(pat_off).match(raw)
                if m: self.transport._handle_timing(int(m.group("i")),"off",_dispatch); return
            except: pass

        for ev_key,ev_name in [("in_long_press","long_press"),("in_double_click","double_click")]:
            pat=proto.get(ev_key,"")
            if not pat: continue
            try:
                m=pattern_to_regex(pat).match(raw)
                if m: _dispatch(int(m.group("i")),ev_name); return
            except: pass

        # Fallback JSON
        try:
            msg=json.loads(raw); t=msg.get("t")
            if t in ("press","long_press","double_click"):
                idx=msg.get("i",0)
                actions=self.cfg.active()["buttons"].get(str(idx),{}).get(t,[])
                threading.Thread(target=self.engine.run,args=(actions,),daemon=True).start()
                _dispatch(idx,t)
            elif t=="pot":
                idx=msg.get("i",0); val=msg.get("v",0)
                self.engine.run_pot(self.cfg.active()["pots"].get(str(idx),{}),val)
        except: pass

    def _update_serial_status(self):
        ok = self.transport.is_connected(0)
        port = self.transport._port_names[0]
        self._serial_dot.delete("all")
        self._serial_dot.create_oval(0,0,10,10, fill=th("green") if ok else th("red"), outline="")
        self._serial_lbl.configure(text=port if ok else "Déconnecté",
            fg=th("text2") if ok else th("text3"))
        if hasattr(self,"_serial_status_lbl"):
            self._serial_status_lbl.configure(
                text=f"✅ Connecté : {port}" if ok else "❌ Non connecté",
                fg=th("green") if ok else th("red"))

    def _update_profile_label(self):
        p = self.cfg.active()
        self._lbl_profile.configure(text=f"◈ {p.get('name','?')}")

    # ── BOUCLE MÉTRIQUES ─────────────────────────────────────────────────────
    def _start_metrics_loop(self):
        self.metrics.collect()  # init réseau
        def _loop():
            while True:
                time.sleep(1)
                m = self.metrics.collect()
                self._metrics_data = m
                keys=["cpu","ram","gpu_usage","ssd_usage"]
                out_pat=self.cfg.data.get("protocol",{}).get("out_led","led{i}:{v}")
                for i in range(4):
                    k=self.cfg.data.get("led_strips",{}).get(str(i),{}).get("metric",keys[i])
                    self.transport.send_raw(pattern_format(out_pat,i=i,v=min(100,int(float(m.get(k,0) or 0)))))
                # MAJ UI en thread-safe
                self.root.after(0, self._tick_ui)
        threading.Thread(target=_loop,daemon=True).start()

    def _tick_ui(self):
        m = self._metrics_data
        # Heure topbar
        self._lbl_time.configure(text=m.get("time",""))
        # Serial status (polling)
        self._update_serial_status()
        # Vue métriques si active
        if self._active_view == "metrics":
            self._refresh_metrics_ui()
        # LED strips — mise à jour légère (couleur + valeur uniquement)
        if self._active_view == "device":
            self._update_led_bars()

# ══════════════════════════════════════════════════════════════════════════════
# INSTANCE UNIQUE + MAIN
# ══════════════════════════════════════════════════════════════════════════════
def _port_is_free(p):
    import socket as _s; s=_s.socket(_s.AF_INET,_s.SOCK_STREAM)
    try: s.bind(("127.0.0.1",p)); s.close(); return True
    except: s.close(); return False

if __name__ == "__main__":
    # Instance unique via lockfile
    LOCK = Path(os.path.expanduser("~")) / ".macrodeck" / "imperium.lock"
    try:
        if LOCK.exists():
            try:
                pid = int(LOCK.read_text())
                if psutil.pid_exists(pid):
                    if sys.platform == "win32":
                        ctypes.windll.user32.MessageBoxW(0,
                            "Imperium est déjà lancé.", "Imperium", 0x40|0x1000)
                    sys.exit(0)
            except: pass
        LOCK.write_text(str(os.getpid()))
    except: pass

    root = tk.Tk()
    app = ImperiumApp(root)

    def _on_close():
        try: app.cfg.save()
        except: pass
        try: LOCK.unlink()
        except: pass
        root.destroy()

    root.protocol("WM_DELETE_WINDOW", _on_close)
    try:
        root.mainloop()
    finally:
        try: app.cfg.save()
        except: pass
        try: LOCK.unlink()
        except: pass
