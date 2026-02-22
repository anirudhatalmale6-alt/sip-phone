"""
SIP Phone - Simple Windows SIP Dialer
"""
import tkinter as tk
from tkinter import messagebox
import threading
import json
import os
import sys
import socket
import time
import logging

# Enable pyVoIP debug
try:
    import pyVoIP
    pyVoIP.DEBUG = True
except:
    pass

# Settings file path
SETTINGS_FILE = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "sip_settings.json")
LOG_FILE = os.path.join(os.path.dirname(os.path.abspath(sys.argv[0])), "sip_debug.log")

logging.basicConfig(filename=LOG_FILE, level=logging.DEBUG,
                    format='%(asctime)s %(levelname)s: %(message)s')

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

def get_local_ip(server="172.104.203.87", port=5060):
    """Get the local IP address that has a route to the SIP server."""
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect((server, port))
        ip = s.getsockname()[0]
        s.close()
        logging.info(f"Detected local IP: {ip}")
        return ip
    except Exception as e:
        logging.error(f"Failed to detect local IP: {e}")
        # Fallback
        try:
            return socket.gethostbyname(socket.gethostname())
        except:
            return "0.0.0.0"


class SIPPhoneApp:
    def __init__(self):
        self.root = tk.Tk()
        self.root.title("SIP Phone")
        self.root.geometry("320x560")
        self.root.resizable(False, False)
        self.root.configure(bg="#1a1a2e")

        self.settings = load_settings()
        self.phone = None
        self.current_call = None
        self.is_registered = False
        self.is_calling = False
        self.my_ip = None

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
                self.current_call.dtmf(key)
            except:
                pass

    def connect_sip(self):
        threading.Thread(target=self._connect_sip_thread, daemon=True).start()

    def _connect_sip_thread(self):
        try:
            from pyVoIP.VoIP import VoIPPhone, CallState

            server = self.settings["server"]
            port = int(self.settings["port"])

            self.root.after(0, lambda: self.status_var.set("Detecting IP..."))
            self.my_ip = get_local_ip(server, port)
            self.log(f"Local IP: {self.my_ip}")
            self.log(f"Server: {server}:{port}")

            self.root.after(0, lambda: self.status_var.set("Registering..."))

            self.phone = VoIPPhone(
                server=server,
                port=port,
                username=self.settings["username"],
                password=self.settings["password"],
                myIP=self.my_ip,
                callCallback=self.incoming_call_callback,
                sipPort=5080,
                rtpPortLow=10000,
                rtpPortHigh=20000
            )
            self.phone.start()
            self.is_registered = True

            self.log(f"Registered as {self.settings['username']}")
            self.root.after(0, lambda: self.status_var.set(f"Registered: {self.settings['username']}"))
            self.root.after(0, lambda: self.indicator.itemconfig(self.indicator_dot, fill="#4CAF50"))

        except Exception as e:
            err = str(e)
            self.log(f"Registration error: {err}")
            self.root.after(0, lambda: self.status_var.set(f"Error: {err[:50]}"))
            self.root.after(0, lambda: self.indicator.itemconfig(self.indicator_dot, fill="#ff4444"))

    def incoming_call_callback(self, call):
        """Handle incoming calls"""
        from pyVoIP.VoIP import CallState
        try:
            self.log(f"Incoming call, state: {call.state}")
            call.answer()
            self.current_call = call
            self.is_calling = True
            self.root.after(0, lambda: self.call_status_var.set("Incoming call - connected"))
            self.root.after(0, lambda: self.btn_hangup.config(state="normal"))
            self.root.after(0, lambda: self.btn_call.config(state="disabled"))

            while call.state == CallState.ANSWERED:
                time.sleep(0.5)

            self.log("Incoming call ended")
            self.root.after(0, self._call_ended)
        except Exception as e:
            self.log(f"Incoming call error: {e}")
            self.root.after(0, self._call_ended)

    def dial(self):
        number = self.number_var.get().strip()
        if not number:
            return

        if not self.is_registered or not self.phone:
            messagebox.showerror("Error", "SIP not registered. Check settings.")
            return

        self.btn_call.config(state="disabled")
        self.btn_hangup.config(state="normal")
        self.call_status_var.set(f"Calling {number}...")
        self.log(f"Dialing: {number}")

        threading.Thread(target=self._dial_thread, args=(number,), daemon=True).start()

    def _dial_thread(self, number):
        from pyVoIP.VoIP import CallState
        try:
            self.current_call = self.phone.call(number)
            self.is_calling = True
            self.log(f"Call initiated, state: {self.current_call.state}")

            # Wait for call state to change from DIALING
            timeout = 30
            start = time.time()
            while self.current_call and self.current_call.state == CallState.DIALING:
                if time.time() - start > timeout:
                    self.log("Call timeout - no answer after 30s")
                    self.root.after(0, lambda: self.call_status_var.set("No answer (timeout)"))
                    break
                time.sleep(0.5)

            if self.current_call:
                state = self.current_call.state
                self.log(f"Call state changed to: {state}")

                if state == CallState.RINGING:
                    self.root.after(0, lambda: self.call_status_var.set(f"Ringing {number}..."))
                    # Wait for answer or hangup
                    while self.current_call and self.current_call.state == CallState.RINGING:
                        time.sleep(0.5)

                if self.current_call and self.current_call.state == CallState.ANSWERED:
                    self.log("Call answered!")
                    self.root.after(0, lambda: self.call_status_var.set(f"In call: {number}"))
                    # Stay in call until ended
                    while self.current_call and self.current_call.state == CallState.ANSWERED:
                        time.sleep(0.5)

            self.log("Call ended")
            self.root.after(0, self._call_ended)

        except Exception as e:
            err = str(e)
            self.log(f"Call error: {err}")
            self.root.after(0, lambda: self.call_status_var.set(f"Error: {err[:40]}"))
            self.root.after(0, self._call_ended)

    def hangup(self):
        self.log("Hangup pressed")
        if self.current_call:
            try:
                self.current_call.hangup()
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

            if self.phone:
                try:
                    self.phone.stop()
                except:
                    pass
            self.is_registered = False
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
                self.current_call.hangup()
            except:
                pass
        if self.phone:
            try:
                self.phone.stop()
            except:
                pass
        self.root.destroy()


if __name__ == "__main__":
    app = SIPPhoneApp()
    app.run()
