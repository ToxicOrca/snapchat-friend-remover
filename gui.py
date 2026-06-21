#!/usr/bin/env python3
"""
Snapchat friend remover -- GUI (Tkinter, no extra dependencies, dark theme).

Run:  python gui.py
Needs snap_remover.py in the same folder, adb on PATH, USB debugging on.
"""

import os
import math
import queue
import tempfile
import threading
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox

import snap_remover as eng

# dark palette
BG = "#1e1f22"
BG2 = "#2b2d31"
BG3 = "#383a40"
FG = "#e3e5e8"
MUTED = "#9aa0a6"
ACCENT = "#5865f2"


class App:
    def __init__(self, root):
        self.root = root
        root.title("Snapchat Friend Remover")
        root.geometry("560x720")
        root.configure(bg=BG)

        self.q = queue.Queue()
        self.stop_event = threading.Event()
        self.worker = None
        self.progress_var = tk.StringVar(value="")

        # Friends tab state
        self.vars = {}
        self.canvas = None
        self.list_frame = None
        self.summary = None
        self.start_btn = None
        self.stop_btn = None
        self.dmin = tk.StringVar(value="1")
        self.dmax = tk.StringVar(value="3")
        self.count = tk.StringVar(value="60")

        # Following tab state
        self.vars_f = {}
        self.canvas_f = None
        self.list_frame_f = None
        self.summary_f = None
        self.start_btn_f = None
        self.stop_btn_f = None
        self.dmin_f = tk.StringVar(value="0.5")
        self.dmax_f = tk.StringVar(value="1")
        self.count_f = tk.StringVar(value="60")

        self._theme()
        self._build()
        self.refresh_device()
        self.load_list()
        self.load_following_list()
        self.root.after(120, self._drain_log)

    def _theme(self):
        s = ttk.Style()
        s.theme_use("clam")
        s.configure(".", background=BG, foreground=FG, fieldbackground=BG2,
                    bordercolor=BG3, focuscolor=ACCENT, troughcolor=BG2)
        s.configure("TFrame", background=BG)
        s.configure("TLabel", background=BG, foreground=FG)
        s.configure("Muted.TLabel", background=BG, foreground=MUTED)
        s.configure("TButton", background=BG3, foreground=FG, borderwidth=0, padding=6)
        s.map("TButton", background=[("active", ACCENT), ("disabled", BG2)],
              foreground=[("disabled", MUTED)])
        s.configure("TCheckbutton", background=BG, foreground=FG)
        s.map("TCheckbutton", background=[("active", BG)],
              indicatorcolor=[("selected", ACCENT), ("!selected", BG2)])
        s.configure("TEntry", fieldbackground=BG2, foreground=FG, insertcolor=FG,
                    bordercolor=BG3)
        s.configure("Vertical.TScrollbar", background=BG3, troughcolor=BG,
                    bordercolor=BG, arrowcolor=FG)
        s.configure("TNotebook", background=BG, borderwidth=0)
        s.configure("TNotebook.Tab", background=BG3, foreground=FG, padding=[12, 4])
        s.map("TNotebook.Tab", background=[("selected", BG)], foreground=[("selected", FG)])

    def _build(self):
        # Top bar (shared)
        top = ttk.Frame(self.root, padding=8)
        top.pack(fill="x")
        self.dev_lbl = ttk.Label(top, text="Device: checking...")
        self.dev_lbl.pack(side="left")
        ttk.Button(top, text="Refresh", command=self.refresh_device).pack(side="right")

        # Notebook with tabs
        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=8)

        friends_tab = ttk.Frame(self.notebook)
        self.notebook.add(friends_tab, text="  Friends  ")
        self._build_friends_tab(friends_tab)

        following_tab = ttk.Frame(self.notebook)
        self.notebook.add(following_tab, text="  Following  ")
        self._build_following_tab(following_tab)

        # Log pane (shared)
        self.log = scrolledtext.ScrolledText(self.root, height=10, state="disabled",
                                             bg=BG2, fg=FG, insertbackground=FG,
                                             borderwidth=0, highlightthickness=0)
        self.log.pack(fill="both", expand=False, padx=8, pady=8)

        # Tab-aware mousewheel
        self.root.bind_all("<MouseWheel>", self._on_mousewheel)

    def _build_friends_tab(self, parent):
        bar = ttk.Frame(parent, padding=(8, 4))
        bar.pack(fill="x")
        ttk.Button(bar, text="Scan friends", command=self.scan).pack(side="left")
        ttk.Button(bar, text="Calibrate three-dots", command=self.calibrate).pack(side="left", padx=4)
        ttk.Button(bar, text="Mark all", command=lambda: self.set_all(True)).pack(side="right")
        ttk.Button(bar, text="Clear all", command=lambda: self.set_all(False)).pack(side="right", padx=4)

        mid = ttk.Frame(parent, padding=8)
        mid.pack(fill="both", expand=True)
        self.canvas = tk.Canvas(mid, highlightthickness=0, bg=BG)
        sb = ttk.Scrollbar(mid, orient="vertical", command=self.canvas.yview)
        self.list_frame = ttk.Frame(self.canvas)
        self.list_frame.bind("<Configure>",
                             lambda e: self.canvas.configure(scrollregion=self.canvas.bbox("all")))
        self.canvas.create_window((0, 0), window=self.list_frame, anchor="nw")
        self.canvas.configure(yscrollcommand=sb.set)
        self.canvas.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        ctl = ttk.Frame(parent, padding=8)
        ctl.pack(fill="x")
        ttk.Button(ctl, text="Save list", command=self.save_list).pack(side="left")
        ttk.Label(ctl, text="delay min").pack(side="left", padx=(12, 2))
        ttk.Entry(ctl, width=4, textvariable=self.dmin).pack(side="left")
        ttk.Label(ctl, text="max").pack(side="left", padx=2)
        ttk.Entry(ctl, width=4, textvariable=self.dmax).pack(side="left")
        ttk.Label(ctl, text="count").pack(side="left", padx=(12, 2))
        ttk.Entry(ctl, width=5, textvariable=self.count).pack(side="left")

        run = ttk.Frame(parent, padding=(8, 0))
        run.pack(fill="x")
        self.start_btn = ttk.Button(run, text="Start removal", command=self.start)
        self.start_btn.pack(side="left")
        self.stop_btn = ttk.Button(run, text="Stop", command=self.stop, state="disabled")
        self.stop_btn.pack(side="left", padx=4)
        self.progress_lbl = ttk.Label(run, textvariable=self.progress_var, style="Muted.TLabel")
        self.progress_lbl.pack(side="left", padx=8)
        self.summary = ttk.Label(run, text="", style="Muted.TLabel")
        self.summary.pack(side="right")

    def _build_following_tab(self, parent):
        bar = ttk.Frame(parent, padding=(8, 4))
        bar.pack(fill="x")
        ttk.Button(bar, text="Scan following", command=self.scan_following).pack(side="left")
        ttk.Button(bar, text="Calibrate X button", command=self.calibrate_x).pack(side="left", padx=4)
        ttk.Button(bar, text="Mark all", command=lambda: self.set_all_f(True)).pack(side="right")
        ttk.Button(bar, text="Clear all", command=lambda: self.set_all_f(False)).pack(side="right", padx=4)

        mid = ttk.Frame(parent, padding=8)
        mid.pack(fill="both", expand=True)
        self.canvas_f = tk.Canvas(mid, highlightthickness=0, bg=BG)
        sb = ttk.Scrollbar(mid, orient="vertical", command=self.canvas_f.yview)
        self.list_frame_f = ttk.Frame(self.canvas_f)
        self.list_frame_f.bind("<Configure>",
                               lambda e: self.canvas_f.configure(scrollregion=self.canvas_f.bbox("all")))
        self.canvas_f.create_window((0, 0), window=self.list_frame_f, anchor="nw")
        self.canvas_f.configure(yscrollcommand=sb.set)
        self.canvas_f.pack(side="left", fill="both", expand=True)
        sb.pack(side="right", fill="y")

        ctl = ttk.Frame(parent, padding=8)
        ctl.pack(fill="x")
        ttk.Button(ctl, text="Save list", command=self.save_following_list).pack(side="left")
        ttk.Label(ctl, text="delay min").pack(side="left", padx=(12, 2))
        ttk.Entry(ctl, width=4, textvariable=self.dmin_f).pack(side="left")
        ttk.Label(ctl, text="max").pack(side="left", padx=2)
        ttk.Entry(ctl, width=4, textvariable=self.dmax_f).pack(side="left")
        ttk.Label(ctl, text="count").pack(side="left", padx=(12, 2))
        ttk.Entry(ctl, width=5, textvariable=self.count_f).pack(side="left")

        run = ttk.Frame(parent, padding=(8, 0))
        run.pack(fill="x")
        self.start_btn_f = ttk.Button(run, text="Start unfollow", command=self.start_unfollow)
        self.start_btn_f.pack(side="left")
        self.stop_btn_f = ttk.Button(run, text="Stop", command=self.stop, state="disabled")
        self.stop_btn_f.pack(side="left", padx=4)
        self.progress_lbl_f = ttk.Label(run, textvariable=self.progress_var, style="Muted.TLabel")
        self.progress_lbl_f.pack(side="left", padx=8)
        self.summary_f = ttk.Label(run, text="", style="Muted.TLabel")
        self.summary_f.pack(side="right")

    def _on_mousewheel(self, e):
        active = self.notebook.index(self.notebook.select())
        canvas = self.canvas if active == 0 else self.canvas_f
        canvas.yview_scroll(int(-e.delta / 120), "units")

    def logmsg(self, msg):
        self.q.put(msg)

    def _drain_log(self):
        try:
            while True:
                msg = self.q.get_nowait()
                self.log.configure(state="normal")
                self.log.insert("end", msg + "\n")
                self.log.see("end")
                self.log.configure(state="disabled")
        except queue.Empty:
            pass
        self.root.after(120, self._drain_log)

    def refresh_device(self):
        ok = eng.device_connected()
        self.dev_lbl.config(text="Device: connected" if ok else "Device: NOT connected")

    # --- Friends tab ---

    def load_list(self):
        for w in self.list_frame.winfo_children():
            w.destroy()
        self.vars.clear()
        roster = eng.load_roster()
        for key in sorted(roster, key=lambda k: roster[k][1].lower()):
            action, name = roster[key]
            v = tk.BooleanVar(value=(action == "drop"))
            self.vars[name] = v
            ttk.Checkbutton(self.list_frame, text=name, variable=v,
                            command=self.update_summary).pack(anchor="w")
        self.update_summary()

    def _fmt_eta(self, marked, count_var, dmin_var, dmax_var, overhead):
        try:
            cap = int(count_var.get())
            dmin = float(dmin_var.get())
            dmax = float(dmax_var.get())
        except ValueError:
            return ""
        n = min(marked, cap)
        if n == 0:
            return ""
        secs = n * (overhead + (dmin + dmax) / 2)
        if secs < 60:
            return f"~{int(secs)}s"
        mins = secs / 60
        if mins < 60:
            return f"~{int(mins)}m"
        return f"~{int(mins // 60)}h {int(mins % 60)}m"

    def update_summary(self):
        total = len(self.vars)
        n = sum(1 for v in self.vars.values() if v.get())
        eta = self._fmt_eta(n, self.count, self.dmin, self.dmax, 10)
        eta_str = f"  |  ETA {eta}" if eta else ""
        self.summary.config(text=f"{total} friends  |  {n} marked to remove{eta_str}")

    def set_all(self, val):
        for v in self.vars.values():
            v.set(val)
        self.update_summary()

    def save_list(self):
        roster = eng.load_roster()
        for name, v in self.vars.items():
            roster[name.lower()] = ("drop" if v.get() else "keep", name)
        eng.write_roster(roster)
        self.update_summary()
        self.logmsg(f"Saved. {sum(1 for v in self.vars.values() if v.get())} marked to remove.")

    def scan(self):
        if not eng.device_connected():
            messagebox.showwarning("No device", "Phone not connected over adb.")
            return
        self.logmsg("Scanning friends list (put the phone on it, top)...")

        def work():
            r = eng.scan_roster()
            self.logmsg(f"Found {len(r)} friends.")
            self.root.after(0, self.load_list)

        threading.Thread(target=work, daemon=True).start()

    def calibrate(self):
        if not eng.device_connected():
            messagebox.showwarning("No device", "Phone not connected over adb.")
            return
        data = eng.screencap()
        if not data:
            messagebox.showerror("Screenshot failed", "Couldn't capture the screen.")
            return
        path = os.path.join(tempfile.gettempdir(), "snap_profile.png")
        with open(path, "wb") as f:
            f.write(data)
        try:
            img = tk.PhotoImage(file=path)
        except Exception as e:
            messagebox.showerror("Image error", str(e))
            return

        factor = max(1, math.ceil(img.height() / 640))
        shown = img.subsample(factor, factor)

        win = tk.Toplevel(self.root)
        win.title("Click the three-dots menu")
        win.configure(bg=BG)
        ttk.Label(win, text="Open a friend's PROFILE first, then click the three-dots.",
                  style="Muted.TLabel").pack(pady=4)
        cv = tk.Canvas(win, width=shown.width(), height=shown.height(),
                       highlightthickness=0, bg=BG)
        cv.pack()
        cv.create_image(0, 0, anchor="nw", image=shown)
        cv.image = shown

        def on_click(e):
            dx, dy = e.x * factor, e.y * factor
            eng.set_three_dots((dx, dy))
            self.logmsg(f"Calibrated three-dots = ({dx}, {dy}). Saved to config.json.")
            win.destroy()

        cv.bind("<Button-1>", on_click)

    def start(self):
        if self.worker and self.worker.is_alive():
            return
        self.save_list()
        if not eng.device_connected():
            messagebox.showwarning("No device", "Phone not connected over adb.")
            return
        if not sum(1 for v in self.vars.values() if v.get()):
            messagebox.showinfo("Nothing selected", "Check the people to remove first.")
            return
        if not eng.load_config().get("three_dots"):
            if not messagebox.askyesno("Not calibrated",
                                       "Three-dots isn't calibrated yet. It may miss. Continue?"):
                return
        try:
            dmin, dmax, cap = float(self.dmin.get()), float(self.dmax.get()), int(self.count.get())
        except ValueError:
            messagebox.showerror("Bad input", "Delay/count must be numbers.")
            return
        if not messagebox.askyesno(
                "Get ready",
                "On your phone, open Snapchat to your Friends list and scroll to the "
                "TOP.\n\nWhen you're there, click Yes to start removing up to "
                f"{cap} friends. These are real removals."):
            return
        if not eng.at_friends_list(eng.dump()):
            if not messagebox.askyesno(
                    "Not on the friends list?",
                    "I can't see the friends list on screen right now. The run may "
                    "misbehave if you're not on it.\n\nStart anyway?"):
                return

        self.stop_event.clear()
        self._set_running(True)
        self.progress_var.set("0/{} done".format(cap))
        self.logmsg(f"Starting: up to {cap}, {dmin}-{dmax}s gaps. Phone on the friends list.")

        def work():
            removed, remaining = eng.run_batch(cap, dmin, dmax, log=self.logmsg,
                                               should_stop=self.stop_event.is_set,
                                               on_progress=self._on_progress)
            self.logmsg(f"Finished. Removed {removed}. {len(remaining)} still pending.")
            self.root.after(0, self._run_done)

        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()

    def _run_done(self):
        self._set_running(False)
        self.progress_var.set("")
        self.load_list()
        self.load_following_list()

    def stop(self):
        self.stop_event.set()
        self.logmsg("Stopping after the current person...")

    def _on_progress(self, removed, cap):
        self.root.after(0, lambda: self.progress_var.set(f"{removed}/{cap} done"))

    def _set_running(self, running):
        state_start = "disabled" if running else "normal"
        state_stop = "normal" if running else "disabled"
        self.start_btn.config(state=state_start)
        self.stop_btn.config(state=state_stop)
        self.start_btn_f.config(state=state_start)
        self.stop_btn_f.config(state=state_stop)

    # --- Following tab ---

    def load_following_list(self):
        for w in self.list_frame_f.winfo_children():
            w.destroy()
        self.vars_f.clear()
        roster = eng.load_following()
        for key in sorted(roster, key=lambda k: roster[k][1].lower()):
            action, name = roster[key]
            v = tk.BooleanVar(value=(action == "drop"))
            self.vars_f[name] = v
            ttk.Checkbutton(self.list_frame_f, text=name, variable=v,
                            command=self.update_summary_f).pack(anchor="w")
        self.update_summary_f()

    def update_summary_f(self):
        total = len(self.vars_f)
        n = sum(1 for v in self.vars_f.values() if v.get())
        eta = self._fmt_eta(n, self.count_f, self.dmin_f, self.dmax_f, 4)
        eta_str = f"  |  ETA {eta}" if eta else ""
        self.summary_f.config(text=f"{total} following  |  {n} marked to unfollow{eta_str}")

    def set_all_f(self, val):
        for v in self.vars_f.values():
            v.set(val)
        self.update_summary_f()

    def save_following_list(self):
        roster = eng.load_following()
        for name, v in self.vars_f.items():
            roster[name.lower()] = ("drop" if v.get() else "keep", name)
        eng.write_following(roster)
        self.update_summary_f()
        self.logmsg(f"Saved. {sum(1 for v in self.vars_f.values() if v.get())} marked to unfollow.")

    def scan_following(self):
        if not eng.device_connected():
            messagebox.showwarning("No device", "Phone not connected over adb.")
            return
        self.logmsg("Scanning following list (put the phone on it)...")

        def work():
            r = eng.scan_following(log=self.logmsg)
            self.logmsg(f"Found {len(r)} following.")
            self.root.after(0, self.load_following_list)

        threading.Thread(target=work, daemon=True).start()

    def calibrate_x(self):
        if not eng.device_connected():
            messagebox.showwarning("No device", "Phone not connected over adb.")
            return
        data = eng.screencap()
        if not data:
            messagebox.showerror("Screenshot failed", "Couldn't capture the screen.")
            return
        path = os.path.join(tempfile.gettempdir(), "snap_following.png")
        with open(path, "wb") as f:
            f.write(data)
        try:
            img = tk.PhotoImage(file=path)
        except Exception as e:
            messagebox.showerror("Image error", str(e))
            return

        factor = max(1, math.ceil(img.height() / 640))
        shown = img.subsample(factor, factor)

        win = tk.Toplevel(self.root)
        win.title("Click any X button")
        win.configure(bg=BG)
        ttk.Label(win, text="On the Following list in Edit mode, click any X button.",
                  style="Muted.TLabel").pack(pady=4)
        cv = tk.Canvas(win, width=shown.width(), height=shown.height(),
                       highlightthickness=0, bg=BG)
        cv.pack()
        cv.create_image(0, 0, anchor="nw", image=shown)
        cv.image = shown

        def on_click(e):
            dx = e.x * factor
            eng.set_unfollow_x(dx)
            self.logmsg(f"Calibrated X button = x:{dx}. Saved to config.json.")
            win.destroy()

        cv.bind("<Button-1>", on_click)

    def start_unfollow(self):
        if self.worker and self.worker.is_alive():
            return
        self.save_following_list()
        if not eng.device_connected():
            messagebox.showwarning("No device", "Phone not connected over adb.")
            return
        if not sum(1 for v in self.vars_f.values() if v.get()):
            messagebox.showinfo("Nothing selected", "Check the accounts to unfollow first.")
            return
        if not eng.load_config().get("unfollow_x"):
            if not messagebox.askyesno("Not calibrated",
                                       "X button isn't calibrated yet. It will miss.\n\n"
                                       "Go to the Following tab, tap Edit, then click "
                                       "'Calibrate X button' first.\n\nContinue anyway?"):
                return
        try:
            dmin, dmax, cap = float(self.dmin_f.get()), float(self.dmax_f.get()), int(self.count_f.get())
        except ValueError:
            messagebox.showerror("Bad input", "Delay/count must be numbers.")
            return
        if not messagebox.askyesno(
                "Get ready",
                "On your phone, open Snapchat to your Following list.\n\n"
                f"Click Yes to start unfollowing up to {cap} accounts. "
                "These are real unfollows."):
            return

        self.stop_event.clear()
        self._set_running(True)
        self.progress_var.set("0/{} done".format(cap))
        self.logmsg(f"Starting unfollow: up to {cap}, {dmin}-{dmax}s gaps.")

        def work():
            removed, remaining = eng.run_unfollow_batch(cap, dmin, dmax, log=self.logmsg,
                                                         should_stop=self.stop_event.is_set,
                                                         on_progress=self._on_progress)
            self.logmsg(f"Finished. Unfollowed {removed}. {len(remaining)} still pending.")
            self.root.after(0, self._run_done)

        self.worker = threading.Thread(target=work, daemon=True)
        self.worker.start()


if __name__ == "__main__":
    root = tk.Tk()
    App(root)
    root.mainloop()
