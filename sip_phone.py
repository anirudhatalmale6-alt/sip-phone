"""
SIP Phone - Simple Windows SIP Dialer (PJSUA2)
"""
import tkinter as tk
from tkinter import messagebox
import threading
import json
import os
import sys
import time
import logging
import traceback

# Settings & log file paths - use CWD for settings, temp for logs
APP_DIR = os.getcwd()
SETTINGS_FILE = os.path.join(APP_DIR, "sip_settings.json")
import tempfile
LOG_DIR = tempfile.gettempdir()
LOG_FILE = os.path.join(LOG_DIR, "sip_debug.log")

logging.basicConfig(filename=LOG_FILE, level=logging.DEBUG,
                    format='%(asctime)s %(levelname)s: %(message)s')

try:
    import pjsua2 as pj
except Exception as e:
    err_msg = f"Failed to load pjsua2:\n{e}\n\n{traceback.format_exc()}"
    logging.error(err_msg)
    try:
        root = tk.Tk()
        root.withdraw()
        messagebox.showerror("SIP Phone Error", err_msg)
        root.destroy()
    except:
        print(err_msg)
    sys.exit(1)

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


class MyCall(pj.Call):
    """Custom call class with state callbacks."""
    def __init__(self, acc, app, call_id=pj.PJSUA_INVALID_ID):
        pj.Call.__init__(self, acc, call_id)
        self.app = app

    def onCallState(self, prm):
        ci = self.getInfo()
        state_text = ci.stateText
        self.app.log(f"Call state: {state_text} (code {ci.lastStatusCode})")

        if ci.state == pj.PJSIP_INV_STATE_CONFIRMED:
            self.app.root.after(0, lambda: self.app.call_status_var.set("Connected"))
            self.app.root.after(0, lambda: self.app.status_label.config(fg="#4CAF50"))
        elif ci.state == pj.PJSIP_INV_STATE_DISCONNECTED:
            self.app.log(f"Call disconnected: {ci.lastReason}")
            self.app.root.after(0, self.app._call_ended)
        elif ci.state == pj.PJSIP_INV_STATE_CALLING:
            self.app.root.after(0, lambda: self.app.call_status_var.set("Calling..."))
        elif ci.state == pj.PJSIP_INV_STATE_EARLY:
            self.app.root.after(0, lambda: self.app.call_status_var.set("Ringing..."))
        elif ci.state == pj.PJSIP_INV_STATE_CONNECTING:
            self.app.root.after(0, lambda: self.app.call_status_var.set("Connecting..."))

    def onCallMediaState(self, prm):
        ci = self.getInfo()
        for mi_idx in range(len(ci.media)):
            mi = ci.media[mi_idx]
            if mi.type == pj.PJMEDIA_TYPE_AUDIO and \
               (mi.status == pj.PJSUA_CALL_MEDIA_ACTIVE or
                mi.status == pj.PJSUA_CALL_MEDIA_REMOTE_HOLD):
                try:
                    m = self.getMedia(mi_idx)
                    am = pj.AudioMedia.typecastFromMedia(m)
                    # Connect call audio to sound device
                    mgr = pj.Endpoint.instance().audDevManager()
                    mgr.getCaptureDevMedia().startTransmit(am)
                    am.startTransmit(mgr.getPlaybackDevMedia())
                    self.app.log("Audio connected")
                except Exception as e:
                    self.app.log(f"Audio error: {e}")


class MyAccount(pj.Account):
    """Custom account class with registration callback."""
    def __init__(self, app):
        pj.Account.__init__(self)
        self.app = app

    def onRegState(self, prm):
        ai = self.getInfo()
        self.app.log(f"Registration: {prm.code} {prm.reason}")
        if prm.code == 200:
            self.app.is_registered = True
            self.app.root.after(0, lambda: self.app.status_var.set(
                f"Registered: {self.app.settings['username']}"))
            self.app.root.after(0, lambda: self.app.indicator.itemconfig(
                self.app.indicator_dot, fill="#4CAF50"))
        else:
            self.app.is_registered = False
            self.app.root.after(0, lambda: self.app.status_var.set(
                f"Reg failed: {prm.code} {prm.reason}"))
            self.app.root.after(0, lambda: self.app.indicator.itemconfig(
                self.app.indicator_dot, fill="#ff4444"))

    def onIncomingCall(self, prm):
        call = MyCall(self, self.app, prm.callId)
        ci = call.getInfo()
        self.app.log(f"Incoming call from {ci.remoteUri}")
        # Auto-answer incoming calls
        call_prm = pj.CallOpParam()
        call_prm.statusCode = 200
        call.answer(call_prm)
        self.app.current_call = call
        self.app.is_calling = True
        self.app.root.after(0, lambda: self.app.call_status_var.set("Incoming call"))
        self.app.root.after(0, lambda: self.app.btn_hangup.config(state="normal"))
        self.app.root.after(0, lambda: self.app.btn_call.config(state="disabled"))


class SIPPhoneApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("SIP Phone")
        self.root.geometry("320x560")
        self.root.resizable(False, False)
        self.root.configure(bg="#1a1a2e")

        self.settings = load_settings()
        self.ep = None
        self.acc = None
        self.current_call = None
        self.is_registered = False
        self.is_calling = False

        self.build_ui()
        self.connect_sip()

    def log(self, msg):
        logging.info(msg)
        try:
            self.root.after(0, lambda: self._update_log(msg))
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
        self.status_var = tk.StringVar(value="Connecting...")
        self.status_label = tk.Label(self.root, textvariable=self.status_var,
                                      font=("Segoe UI", 10), fg="#999999", bg="#1a1a2e")
        self.status_label.pack(pady=(0, 5))

        # Status indicator
        self.indicator = tk.Canvas(self.root, width=12, height=12, bg="#1a1a2e",
                                    highlightthickness=0)
        self.indicator.pack()
        self.indicator_dot = self.indicator.create_oval(2, 2, 10, 10, fill="#ff4444", outline="")

        # Phone number display
        frame_num = tk.Frame(self.root, bg="#16213e", padx=10, pady=8)
        frame_num.pack(padx=20, pady=(10, 5), fill="x")

        self.number_var = tk.StringVar()
        self.number_entry = tk.Entry(frame_num, textvariable=self.number_var,
                                      font=("Segoe UI", 20), bg="#16213e", fg="#ffffff",
                                      insertbackground="#ffffff", relief="flat",
                                      justify="center")
        self.number_entry.pack(fill="x")
        self.number_entry.bind("<Return>", lambda e: self.dial())

        # Keypad
        keypad_frame = tk.Frame(self.root, bg="#1a1a2e")
        keypad_frame.pack(padx=20, pady=5)

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
                btn.pack(side="left", padx=3, pady=3)

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
        self.log_text = tk.Text(log_frame, height=4, bg="#0d0d1a", fg="#666666",
                                 font=("Consolas", 7), relief="flat", state="disabled",
                                 wrap="word")
        self.log_text.pack(fill="both", expand=True)

    def press_key(self, key):
        self.number_var.set(self.number_var.get() + key)
        # Send DTMF if in call
        if self.current_call and self.is_calling:
            try:
                dtmf_prm = pj.CallSendDtmfParam()
                dtmf_prm.digits = key
                dtmf_prm.method = pj.PJSUA_DTMF_METHOD_RFC2833
                self.current_call.sendDtmf(dtmf_prm)
            except:
                pass

    def connect_sip(self):
        threading.Thread(target=self._connect_sip_thread, daemon=True).start()

    def _connect_sip_thread(self):
        try:
            server = self.settings["server"]
            port = int(self.settings["port"])
            username = self.settings["username"]
            password = self.settings["password"]

            self.root.after(0, lambda: self.status_var.set("Initializing..."))

            # Create endpoint
            self.ep = pj.Endpoint()
            self.ep.libCreate()

            # Endpoint config
            ep_cfg = pj.EpConfig()
            ep_cfg.logConfig.level = 4
            ep_cfg.logConfig.consoleLevel = 4
            log_path = os.path.join(LOG_DIR, "sip_pjsip.log")
            ep_cfg.logConfig.filename = log_path
            self.log(f"PJSIP log: {log_path}")

            # UA config
            ep_cfg.uaConfig.maxCalls = 4

            self.ep.libInit(ep_cfg)

            # Create UDP transport
            tp_cfg = pj.TransportConfig()
            tp_cfg.port = 0  # auto-select
            self.ep.transportCreate(pj.PJSIP_TRANSPORT_UDP, tp_cfg)

            self.ep.libStart()
            self.log(f"PJSIP started, connecting to {server}:{port}")
            self.root.after(0, lambda: self.status_var.set("Registering..."))

            # Account config
            acfg = pj.AccountConfig()
            acfg.idUri = f"sip:{username}@{server}"
            acfg.regConfig.registrarUri = f"sip:{server}:{port}"
            acfg.regConfig.timeoutSec = 300

            # Auth credentials
            cred = pj.AuthCredInfo("digest", "*", username, 0, password)
            acfg.sipConfig.authCreds.append(cred)

            # NAT config - helps behind routers
            acfg.natConfig.iceEnabled = True
            acfg.natConfig.sdpNatRewriteUse = 1
            acfg.natConfig.sipOutboundUse = 1

            # Create and register account
            self.acc = MyAccount(self)
            self.acc.create(acfg)

            self.log("Account created, waiting for registration...")

        except Exception as e:
            err = str(e)
            self.log(f"SIP init error: {err}")
            self.root.after(0, lambda: self.status_var.set(f"Error: {err[:50]}"))
            self.root.after(0, lambda: self.indicator.itemconfig(self.indicator_dot, fill="#ff4444"))

    def dial(self):
        number = self.number_var.get().strip()
        if not number:
            return

        if not self.is_registered or not self.acc:
            messagebox.showerror("Error", "SIP not registered. Check settings.")
            return

        if self.current_call:
            messagebox.showwarning("Warning", "Already in a call. Hang up first.")
            return

        self.btn_call.config(state="disabled")
        self.btn_hangup.config(state="normal")
        self.call_status_var.set(f"Calling {number}...")
        self.log(f"Dialing: {number}")

        threading.Thread(target=self._dial_thread, args=(number,), daemon=True).start()

    def _dial_thread(self, number):
        try:
            server = self.settings["server"]
            call = MyCall(self.acc, self)
            call_prm = pj.CallOpParam(True)

            dest_uri = f"sip:{number}@{server}"
            self.log(f"Calling URI: {dest_uri}")
            call.makeCall(dest_uri, call_prm)
            self.current_call = call
            self.is_calling = True
            self.log("Call initiated via PJSUA2")

        except Exception as e:
            err = str(e)
            self.log(f"Call error: {err}")
            self.root.after(0, lambda: self.call_status_var.set(f"Error: {err[:40]}"))
            self.root.after(0, self._call_ended)

    def hangup(self):
        self.log("Hangup pressed")
        if self.current_call:
            try:
                prm = pj.CallOpParam()
                self.current_call.hangup(prm)
            except Exception as e:
                self.log(f"Hangup error: {e}")
        self._call_ended()

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

            # Cleanup old connection
            if self.current_call:
                try:
                    prm = pj.CallOpParam()
                    self.current_call.hangup(prm)
                except:
                    pass
                self.current_call = None

            if self.acc:
                try:
                    self.acc.shutdown()
                except:
                    pass
                self.acc = None

            if self.ep:
                try:
                    self.ep.libDestroy()
                except:
                    pass
                self.ep = None

            self.is_registered = False
            self.is_calling = False
            self.status_var.set("Reconnecting...")
            self.indicator.itemconfig(self.indicator_dot, fill="#ffaa00")
            win.destroy()
            self.connect_sip()

        tk.Button(win, text="Save & Reconnect", font=("Segoe UI", 11, "bold"),
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


if __name__ == "__main__":
    try:
        app = SIPPhoneApp()
        app.run()
    except Exception as e:
        err_msg = f"Fatal error:\n{e}\n\n{traceback.format_exc()}"
        logging.error(err_msg)
        try:
            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("SIP Phone Error", err_msg)
            root.destroy()
        except:
            print(err_msg)
        input("Press Enter to close...")
        sys.exit(1)
