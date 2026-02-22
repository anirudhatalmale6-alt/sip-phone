"""
SIP Phone - Simple Windows SIP Dialer (PJSUA2)
"""
import tkinter as tk
from tkinter import messagebox
import threading
import queue
import json
import os
import sys
import time
import logging
import traceback

# Settings & log file paths
APP_DIR = os.getcwd()
SETTINGS_FILE = os.path.join(APP_DIR, "sip_settings.json")
import tempfile
LOG_DIR = tempfile.gettempdir()
LOG_FILE = os.path.join(LOG_DIR, "sip_debug.log")

logging.basicConfig(filename=LOG_FILE, level=logging.DEBUG,
                    format='%(asctime)s %(levelname)s: %(message)s')

# Lazy import - don't import pjsua2 at module level
pj = None

DEFAULT_SETTINGS = {
    "server": "172.104.203.87",
    "port": 5060,
    "username": "MESER921201",
    "password": "ccc3409fa9de49"
}

def load_settings():
    if os.path.exists(SETTINGS_FILE):
        try:
            with open(SETTINGS_FILE, 'r') as f:
                return json.load(f)
        except:
            pass
    return DEFAULT_SETTINGS.copy()

def save_settings(settings):
    with open(SETTINGS_FILE, 'w') as f:
        json.dump(settings, f, indent=2)


class SIPPhoneApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("SIP Phone")
        self.root.geometry("320x580")
        self.root.resizable(False, False)
        self.root.configure(bg="#1a1a2e")

        self.settings = load_settings()
        self.ep = None
        self.acc = None
        self.current_call = None
        self.is_registered = False
        self.is_calling = False
        self.pj_loaded = False
        self.ui_queue = queue.Queue()
        self.sip_queue = queue.Queue()  # Commands for the SIP thread
        self.auto_dial_number = None
        self.auto_dial_done = False

        # Check for phone number in command line args
        self._parse_args()

        self.build_ui()
        self._poll_ui_queue()

        if self.auto_dial_number:
            self.number_var.set(self.auto_dial_number)
            self.log(f"Auto-dial: {self.auto_dial_number}")
            # Auto-connect and dial
            self.on_connect_click()
        else:
            self.log("UI ready. Click Connect to start.")

    def _parse_args(self):
        """Parse command line for phone number. Supports:
        - SIP-Phone.exe 0501234567
        - SIP-Phone.exe sipphone://0501234567
        - SIP-Phone.exe sipphone:0501234567
        """
        if len(sys.argv) > 1:
            arg = sys.argv[1].strip()
            # Strip protocol prefix if present
            for prefix in ["sipphone://", "sipphone:", "tel://", "tel:"]:
                if arg.lower().startswith(prefix):
                    arg = arg[len(prefix):]
                    break
            # Strip trailing slash
            arg = arg.rstrip("/")
            # Clean the number - keep digits, *, #, +
            cleaned = ''.join(c for c in arg if c in '0123456789*#+')
            if cleaned:
                self.auto_dial_number = cleaned

    def safe_ui(self, func):
        """Thread-safe way to run a function on the UI thread."""
        self.ui_queue.put(func)

    def _poll_ui_queue(self):
        """Process pending UI updates from background threads."""
        try:
            for _ in range(20):  # Process max 20 items per tick
                func = self.ui_queue.get_nowait()
                try:
                    func()
                except Exception as e:
                    logging.error(f"UI update error: {e}")
        except queue.Empty:
            pass
        self.root.after(100, self._poll_ui_queue)

    def log(self, msg):
        logging.info(msg)
        print(msg)
        try:
            self.safe_ui(lambda m=msg: self._update_log(m))
        except:
            pass

    def _update_log(self, msg):
        try:
            self.log_text.config(state="normal")
            self.log_text.insert("end", msg + "\n")
            self.log_text.see("end")
            self.log_text.config(state="disabled")
        except:
            pass

    def build_ui(self):
        # Title
        tk.Label(self.root, text="SIP Phone", font=("Segoe UI", 18, "bold"),
                 fg="#e94560", bg="#1a1a2e").pack(pady=(10, 3))

        # Status
        self.status_var = tk.StringVar(value="Not connected")
        self.status_label = tk.Label(self.root, textvariable=self.status_var,
                                      font=("Segoe UI", 10), fg="#999999", bg="#1a1a2e")
        self.status_label.pack(pady=(0, 3))

        # Status indicator
        self.indicator = tk.Canvas(self.root, width=12, height=12, bg="#1a1a2e",
                                    highlightthickness=0)
        self.indicator.pack()
        self.indicator_dot = self.indicator.create_oval(2, 2, 10, 10, fill="#ff4444", outline="")

        # Connect button
        self.btn_connect = tk.Button(self.root, text="Connect", font=("Segoe UI", 10, "bold"),
                                      bg="#0f3460", fg="white", activebackground="#16213e",
                                      relief="flat", command=self.on_connect_click)
        self.btn_connect.pack(pady=(5, 5))

        # Phone number display
        frame_num = tk.Frame(self.root, bg="#16213e", padx=10, pady=8)
        frame_num.pack(padx=20, pady=(5, 5), fill="x")

        self.number_var = tk.StringVar()
        self.number_entry = tk.Entry(frame_num, textvariable=self.number_var,
                                      font=("Segoe UI", 20), bg="#16213e", fg="#ffffff",
                                      insertbackground="#ffffff", relief="flat",
                                      justify="center")
        self.number_entry.pack(fill="x")
        self.number_entry.bind("<Return>", lambda e: self.dial())

        # Keypad
        keypad_frame = tk.Frame(self.root, bg="#1a1a2e")
        keypad_frame.pack(padx=20, pady=3)

        keys = [
            ['1', '2', '3'],
            ['4', '5', '6'],
            ['7', '8', '9'],
            ['*', '0', '#']
        ]

        for row in keys:
            row_frame = tk.Frame(keypad_frame, bg="#1a1a2e")
            row_frame.pack()
            for key in row:
                btn = tk.Button(row_frame, text=key, font=("Segoe UI", 14, "bold"),
                                width=4, height=1, bg="#16213e", fg="#ffffff",
                                activebackground="#0f3460", activeforeground="#ffffff",
                                relief="flat", bd=0,
                                command=lambda k=key: self.press_key(k))
                btn.pack(side="left", padx=3, pady=2)

        # Call / Hangup buttons
        btn_frame = tk.Frame(self.root, bg="#1a1a2e")
        btn_frame.pack(padx=20, pady=5, fill="x")

        self.btn_call = tk.Button(btn_frame, text="Dial", font=("Segoe UI", 14, "bold"),
                                   bg="#4CAF50", fg="white", activebackground="#388E3C",
                                   relief="flat", height=2, command=self.dial)
        self.btn_call.pack(side="left", fill="x", expand=True, padx=(0, 5))

        self.btn_hangup = tk.Button(btn_frame, text="Hangup", font=("Segoe UI", 14, "bold"),
                                     bg="#e94560", fg="white", activebackground="#c62828",
                                     relief="flat", height=2, command=self.hangup,
                                     state="disabled")
        self.btn_hangup.pack(side="right", fill="x", expand=True, padx=(5, 0))

        # Call status
        self.call_status_var = tk.StringVar(value="")
        tk.Label(self.root, textvariable=self.call_status_var, font=("Segoe UI", 10),
                 fg="#4CAF50", bg="#1a1a2e").pack()

        # Settings button
        self.btn_settings = tk.Button(self.root, text="Settings", font=("Segoe UI", 9),
                                       bg="#1a1a2e", fg="#666666", activebackground="#1a1a2e",
                                       activeforeground="#999999", relief="flat", bd=0,
                                       command=self.show_settings)
        self.btn_settings.pack(pady=(0, 3))

        # Log area
        log_frame = tk.Frame(self.root, bg="#0d0d1a")
        log_frame.pack(padx=10, pady=(0, 5), fill="both", expand=True)
        self.log_text = tk.Text(log_frame, height=5, bg="#0d0d1a", fg="#666666",
                                 font=("Consolas", 7), relief="flat", state="disabled",
                                 wrap="word")
        self.log_text.pack(fill="both", expand=True)

    def press_key(self, key):
        self.number_var.set(self.number_var.get() + key)
        if self.current_call and self.is_calling and self.pj_loaded:
            try:
                dtmf_prm = pj.CallSendDtmfParam()
                dtmf_prm.digits = key
                dtmf_prm.method = pj.PJSUA_DTMF_METHOD_RFC2833
                self.current_call.sendDtmf(dtmf_prm)
            except:
                pass

    def on_connect_click(self):
        self.btn_connect.config(state="disabled", text="Connecting...")
        self.status_var.set("Loading SIP engine...")
        self.indicator.itemconfig(self.indicator_dot, fill="#ffaa00")
        threading.Thread(target=self._connect_sip_thread, daemon=True).start()

    def _connect_sip_thread(self):
        global pj
        try:
            # Step 1: Import pjsua2
            self.log("Loading pjsua2...")
            import pjsua2
            pj = pjsua2
            self.pj_loaded = True
            self.log("pjsua2 loaded OK")

            server = self.settings["server"]
            port = int(self.settings["port"])
            username = self.settings["username"]
            password = self.settings["password"]

            self.safe_ui(lambda: self.status_var.set("Initializing..."))

            # Step 2: Create endpoint
            self.log("Creating endpoint...")
            self.ep = pj.Endpoint()
            self.ep.libCreate()

            # Endpoint config - no console logging
            ep_cfg = pj.EpConfig()
            ep_cfg.logConfig.level = 3
            ep_cfg.logConfig.consoleLevel = 0
            log_path = os.path.join(LOG_DIR, "sip_pjsip.log")
            ep_cfg.logConfig.filename = log_path
            ep_cfg.uaConfig.maxCalls = 4
            # Use fewer threads to reduce crash risk
            ep_cfg.uaConfig.threadCnt = 0

            self.log("Initializing PJSIP...")
            self.ep.libInit(ep_cfg)

            # Step 3: Create UDP transport
            self.log("Creating UDP transport...")
            tp_cfg = pj.TransportConfig()
            tp_cfg.port = 0
            self.ep.transportCreate(pj.PJSIP_TRANSPORT_UDP, tp_cfg)

            self.log("Starting PJSIP...")
            self.ep.libStart()

            # Handle events manually since threadCnt=0
            self.log("PJSIP started OK")
            self.safe_ui(lambda: self.status_var.set("Registering..."))

            # Step 4: Create account
            self.log(f"Registering {username}@{server}:{port}...")

            # Define callback classes with pj reference
            class CallHandler(pj.Call):
                def __init__(ch_self, acc, app, call_id=pj.PJSUA_INVALID_ID):
                    pj.Call.__init__(ch_self, acc, call_id)
                    ch_self.app = app

                def onCallState(ch_self, prm):
                    try:
                        ci = ch_self.getInfo()
                        ch_self.app.log(f"Call: {ci.stateText} ({ci.lastStatusCode})")
                        if ci.state == pj.PJSIP_INV_STATE_CONFIRMED:
                            ch_self.app.safe_ui(lambda: ch_self.app.call_status_var.set("Connected"))
                        elif ci.state == pj.PJSIP_INV_STATE_DISCONNECTED:
                            ch_self.app.safe_ui(ch_self.app._call_ended)
                        elif ci.state == pj.PJSIP_INV_STATE_CALLING:
                            ch_self.app.safe_ui(lambda: ch_self.app.call_status_var.set("Calling..."))
                        elif ci.state == pj.PJSIP_INV_STATE_EARLY:
                            ch_self.app.safe_ui(lambda: ch_self.app.call_status_var.set("Ringing..."))
                    except Exception as e:
                        ch_self.app.log(f"onCallState err: {e}")

                def onCallMediaState(ch_self, prm):
                    try:
                        ci = ch_self.getInfo()
                        for i in range(len(ci.media)):
                            if ci.media[i].type == pj.PJMEDIA_TYPE_AUDIO and \
                               ci.media[i].status == pj.PJSUA_CALL_MEDIA_ACTIVE:
                                m = ch_self.getMedia(i)
                                am = pj.AudioMedia.typecastFromMedia(m)
                                mgr = pj.Endpoint.instance().audDevManager()
                                mgr.getCaptureDevMedia().startTransmit(am)
                                am.startTransmit(mgr.getPlaybackDevMedia())
                                ch_self.app.log("Audio connected")
                    except Exception as e:
                        ch_self.app.log(f"Audio err: {e}")

            class AccHandler(pj.Account):
                def __init__(ah_self, app):
                    pj.Account.__init__(ah_self)
                    ah_self.app = app

                def onRegState(ah_self, prm):
                    try:
                        ah_self.app.log(f"Reg: {prm.code} {prm.reason}")
                        if prm.code == 200:
                            ah_self.app.is_registered = True
                            ah_self.app.safe_ui(lambda: ah_self.app.status_var.set(
                                f"Registered: {ah_self.app.settings['username']}"))
                            ah_self.app.safe_ui(lambda: ah_self.app.indicator.itemconfig(
                                ah_self.app.indicator_dot, fill="#4CAF50"))
                            ah_self.app.safe_ui(lambda: ah_self.app.btn_connect.config(
                                text="Connected", state="disabled"))
                            # Auto-dial if launched with a phone number
                            if ah_self.app.auto_dial_number and not ah_self.app.auto_dial_done:
                                ah_self.app.auto_dial_done = True
                                ah_self.app.safe_ui(ah_self.app.dial)
                        elif prm.code >= 300:
                            ah_self.app.safe_ui(lambda: ah_self.app.status_var.set(
                                f"Reg failed: {prm.code}"))
                            ah_self.app.safe_ui(lambda: ah_self.app.indicator.itemconfig(
                                ah_self.app.indicator_dot, fill="#ff4444"))
                    except Exception as e:
                        ah_self.app.log(f"onRegState err: {e}")

                def onIncomingCall(ah_self, prm):
                    try:
                        call = CallHandler(ah_self, ah_self.app, prm.callId)
                        cp = pj.CallOpParam()
                        cp.statusCode = 200
                        call.answer(cp)
                        ah_self.app.current_call = call
                        ah_self.app.is_calling = True
                        ah_self.app.safe_ui(lambda: ah_self.app.call_status_var.set("Incoming call"))
                        ah_self.app.safe_ui(lambda: ah_self.app.btn_hangup.config(state="normal"))
                        ah_self.app.safe_ui(lambda: ah_self.app.btn_call.config(state="disabled"))
                    except Exception as e:
                        ah_self.app.log(f"Incoming err: {e}")

            # Store the classes for later use
            self.CallHandler = CallHandler

            acfg = pj.AccountConfig()
            acfg.idUri = f"sip:{username}@{server}"
            acfg.regConfig.registrarUri = f"sip:{server}:{port}"
            acfg.regConfig.timeoutSec = 300

            cred = pj.AuthCredInfo("digest", "*", username, 0, password)
            acfg.sipConfig.authCreds.append(cred)

            # NAT - disable ICE to avoid potential crashes
            acfg.natConfig.iceEnabled = False
            acfg.natConfig.sdpNatRewriteUse = 1

            self.acc = AccHandler(self)
            self.acc.create(acfg)

            self.log("Account created, waiting for registration...")

            # Since threadCnt=0, we need to poll for events AND process commands
            while True:
                try:
                    self.ep.libHandleEvents(50)
                except:
                    pass
                # Process any queued SIP commands (dial, hangup, etc)
                try:
                    while True:
                        cmd = self.sip_queue.get_nowait()
                        try:
                            cmd()
                        except Exception as e:
                            self.log(f"SIP cmd error: {e}")
                except queue.Empty:
                    pass
                time.sleep(0.02)

        except Exception as e:
            err = str(e)
            self.log(f"SIP error: {err}\n{traceback.format_exc()}")
            self.safe_ui(lambda: self.status_var.set(f"Error: {err[:50]}"))
            self.safe_ui(lambda: self.indicator.itemconfig(self.indicator_dot, fill="#ff4444"))
            self.safe_ui(lambda: self.btn_connect.config(state="normal", text="Retry"))

    def dial(self):
        number = self.number_var.get().strip()
        if not number:
            return

        if not self.is_registered or not self.acc:
            messagebox.showerror("Error", "Not registered. Click Connect first.")
            return

        if self.current_call:
            messagebox.showwarning("Warning", "Already in a call. Hang up first.")
            return

        self.btn_call.config(state="disabled")
        self.btn_hangup.config(state="normal")
        self.call_status_var.set(f"Calling {number}...")
        self.log(f"Dialing: {number}")

        # Queue the call to the SIP thread
        def do_call():
            try:
                server = self.settings["server"]
                call = self.CallHandler(self.acc, self)
                call_prm = pj.CallOpParam(True)
                dest_uri = f"sip:{number}@{server}"
                self.log(f"URI: {dest_uri}")
                call.makeCall(dest_uri, call_prm)
                self.current_call = call
                self.is_calling = True
                self.log("Call initiated")
            except Exception as e:
                err = str(e)
                self.log(f"Call error: {err}")
                self.safe_ui(lambda: self.call_status_var.set(f"Error: {err[:40]}"))
                self.safe_ui(self._call_ended)

        self.sip_queue.put(do_call)

    def hangup(self):
        self.log("Hangup pressed")
        def do_hangup():
            if self.current_call:
                try:
                    prm = pj.CallOpParam()
                    self.current_call.hangup(prm)
                except Exception as e:
                    self.log(f"Hangup error: {e}")
            self.safe_ui(self._call_ended)
        self.sip_queue.put(do_hangup)

    def _call_ended(self):
        self.current_call = None
        self.is_calling = False
        self.call_status_var.set("")
        self.btn_call.config(state="normal")
        self.btn_hangup.config(state="disabled")

    def show_settings(self):
        win = tk.Toplevel(self.root)
        win.title("SIP Settings")
        win.geometry("300x280")
        win.configure(bg="#1a1a2e")
        win.resizable(False, False)

        fields = {}
        for i, (label, key) in enumerate([
            ("Server:", "server"),
            ("Port:", "port"),
            ("Username:", "username"),
            ("Password:", "password")
        ]):
            tk.Label(win, text=label, font=("Segoe UI", 10), fg="#cccccc",
                     bg="#1a1a2e").place(x=20, y=20 + i * 55)
            var = tk.StringVar(value=str(self.settings.get(key, "")))
            show = "*" if key == "password" else None
            e = tk.Entry(win, textvariable=var, font=("Segoe UI", 11), bg="#16213e",
                         fg="#ffffff", insertbackground="#ffffff", relief="flat",
                         show=show)
            e.place(x=20, y=42 + i * 55, width=260, height=28)
            fields[key] = var

        def do_save():
            self.settings["server"] = fields["server"].get()
            self.settings["port"] = int(fields["port"].get())
            self.settings["username"] = fields["username"].get()
            self.settings["password"] = fields["password"].get()
            save_settings(self.settings)
            win.destroy()
            messagebox.showinfo("Saved", "Settings saved. Click Connect to reconnect.")

        tk.Button(win, text="Save", font=("Segoe UI", 11, "bold"),
                  bg="#4CAF50", fg="white", relief="flat",
                  command=do_save).place(x=20, y=240, width=260, height=32)

    def run(self):
        self.root.protocol("WM_DELETE_WINDOW", self.on_close)
        self.root.mainloop()

    def on_close(self):
        if self.current_call:
            try:
                prm = pj.CallOpParam()
                self.current_call.hangup(prm)
            except:
                pass
        if self.acc:
            try:
                self.acc.shutdown()
            except:
                pass
        if self.ep:
            try:
                self.ep.libDestroy()
            except:
                pass
        self.root.destroy()
        os._exit(0)


if __name__ == "__main__":
    err_log = os.path.join(LOG_DIR, "sip_stderr.log")
    try:
        sys.stderr = open(err_log, 'w')
    except:
        pass

    print(f"SIP Phone starting...")
    print(f"Log dir: {LOG_DIR}")
    print(f"App dir: {APP_DIR}")

    try:
        app = SIPPhoneApp()
        app.run()
    except Exception as e:
        err_msg = f"Fatal error:\n{e}\n\n{traceback.format_exc()}"
        print(err_msg)
        logging.error(err_msg)
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("SIP Phone Error", err_msg)
            root.destroy()
        except:
            pass
        input("Press Enter to close...")
        sys.exit(1)
