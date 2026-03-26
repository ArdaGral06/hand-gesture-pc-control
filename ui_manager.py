"""
UI Manager - Tum tkinter pencerelerini TEK ana thread'de yonetir.
Tcl_AsyncDelete hatasinin kokeni: farkli thread'lerde tk.Tk() olusturulmasi.
Cozum: tek gizli root, tum pencereler Toplevel olarak acilir.
"""

import tkinter as tk
import threading
import queue
import time
import lang as _lang_mod
from status_overlay import StatusOverlay

_BG     = "#0d0d1a"
_CARD   = "#1a1a2e"
_BORDER = "#2a2a4a"
_DIM    = "#5a5a7a"
_GREEN  = "#4ade80"
_AMBER  = "#fbbf24"
_BLUE   = "#60a5fa"
_PURPLE = "#c084fc"
_RED    = "#f87171"
_WHITE  = "#e8e8f0"
_CYAN   = "#67e8f9"


class UIManager:
    """
    Ana tkinter dongusu. main() tarafindan ana thread'de calistirilir.
    Diger modüller event queue'ya mesaj gonderir, bu sinif islemi yapar.
    """

    def __init__(self):
        self._q       = queue.Queue()
        self._root    = None
        self._panel   = None   # kontrol paneli Toplevel
        self._help    = None   # yardim Toplevel
        self._notify  = None   # bildirim Toplevel
        self._overlay         = None   # kalici durum seridi
        self._overlay_visible  = True   # overlay acik mi

        # Durum (ana loop'tan guncellenir, panel okur)
        self._state: dict = {}

        # Callback'ler (main tarafindan set edilir)
        self.on_calibrate   = None
        self.on_toggle_hand = None
        self.on_quit        = None

        self._running = False

    # ── Ana loop (MAIN THREAD'de calisir) ────────────────────────────────────

    def run(self) -> None:
        """Ana tkinter dongusunu baslatir. BLOKLAR — main thread'de cagir."""
        self._root = tk.Tk()
        self._root.withdraw()   # Gizli root pencere
        self._running = True

        # Kontrol panelini ac
        self._root.after(100, self._open_panel)
        # Surekli durum overlay'ini baslat
        self._root.after(150, self._open_overlay)
        # Queue'yu isle
        self._root.after(50, self._process_queue)

        self._root.mainloop()

    def stop(self) -> None:
        """Tkinter dongusunu durdur."""
        self._running = False
        try:
            self._root.after(0, self._root.quit)
        except Exception:
            pass

    # ── Thread-safe API (herhangi bir thread'den cagrilabilir) ───────────────

    def update_state(self, state: dict) -> None:
        self._q.put(("state", state))

    def update_gesture(self, gesture: str, progress: float,
                       scroll_active: bool = False,
                       hold_active: bool = False,
                       action_label: str = "",
                       dwell_sec: float | None = None) -> None:
        """Her frame cagrilan gesture durum guncellemesi."""
        if dwell_sec is None:
            dwell_sec = float(self._state.get("dwell_sec", 1.5))
        self._q.put(("gesture", {
            "gesture":      gesture,
            "progress":     progress,
            "scroll_active":scroll_active,
            "hold_active":  hold_active,
            "action_label": action_label,
            "dwell_sec":    dwell_sec,
        }))

    def show_notify(self, gesture: str) -> None:
        self._q.put(("notify", gesture))

    def request_quit(self) -> None:
        self._q.put(("quit", None))

    # ── Queue isleme (ana thread) ─────────────────────────────────────────────

    def _process_queue(self) -> None:
        try:
            while True:
                msg, data = self._q.get_nowait()
                if msg == "state":
                    self._state = data
                    self._refresh_panel()
                elif msg == "notify":
                    self._show_notify_window(data)
                elif msg == "gesture":
                    if self._overlay:
                        self._overlay.update(
                            data.get("gesture","none"),
                            data.get("progress",0.0),
                            data.get("scroll_active",False),
                            data.get("hold_active",False),
                            data.get("action_label",""),
                            data.get("dwell_sec", self._state.get("dwell_sec", 1.5)),
                        )
                elif msg == "quit":
                    if self.on_quit:
                        self.on_quit()
                    self._root.quit()
        except queue.Empty:
            pass
        if self._running:
            self._root.after(50, self._process_queue)

    # ── Kontrol Paneli ────────────────────────────────────────────────────────

    def _open_panel(self) -> None:
        L     = _lang_mod.get()
        is_tr = L.code == "tr"

        if self._panel and self._panel.winfo_exists():
            return

        win = tk.Toplevel(self._root)
        self._panel = win
        win.title("GestureMouse")
        win.configure(bg=_BG)
        win.resizable(False, False)
        win.attributes("-topmost", True)
        try:
            win.attributes("-alpha", 0.96)
        except Exception:
            pass

        scr_h = win.winfo_screenheight()
        win_w, win_h = 230, 480
        win.geometry(f"{win_w}x{win_h}+10+{(scr_h - win_h)//2}")
        win.protocol("WM_DELETE_WINDOW", self._on_quit_click)

        pad = 12

        # Baslik
        tk.Label(win, text="GestureMouse",
                 font=("Consolas", 12, "bold"),
                 fg=_GREEN, bg=_BG, pady=10).pack(fill="x")
        tk.Frame(win, height=1, bg=_BORDER).pack(fill="x", padx=pad)

        # Durum kartı
        sf = tk.Frame(win, bg=_CARD, padx=10, pady=8)
        sf.pack(fill="x", padx=pad, pady=(8, 0))

        def _row(lbl, val, fg):
            r = tk.Frame(sf, bg=_CARD)
            r.pack(fill="x", pady=1)
            tk.Label(r, text=lbl, font=("Consolas", 8),
                     fg=_DIM, bg=_CARD, width=11, anchor="w").pack(side="left")
            v = tk.Label(r, text=val, font=("Consolas", 8, "bold"),
                         fg=fg, bg=_CARD, anchor="w")
            v.pack(side="left")
            return v

        self._v_hand  = _row(L.t("panel_hand_lbl"),  "--", _BLUE)
        self._v_cal   = _row(L.t("panel_cal_lbl"),   "--", _GREEN)
        self._v_fps   = _row(L.t("panel_fps_lbl"),   "0",  _DIM)
        self._v_kb    = _row(L.t("panel_kb_lbl"),    "--", _DIM)
        self._v_cam   = _row(L.t("panel_cam_lbl"),   "--", _DIM)
        self._v_dwell = _row(L.t("panel_dwell_lbl"), "--", _AMBER)

        tk.Frame(win, height=1, bg=_BORDER).pack(fill="x", padx=pad, pady=8)

        def _btn(text, color, cmd):
            b = tk.Button(win, text=text,
                          font=("Consolas", 10, "bold"),
                          fg=_BG, bg=color, activebackground=color,
                          activeforeground=_BG,
                          relief="flat", bd=0,
                          padx=0, pady=5, cursor="hand2",
                          command=cmd)
            b.pack(fill="x", padx=pad, pady=3)
            lighter = self._lighten(color)
            b.bind("<Enter>", lambda e: b.configure(bg=lighter))
            b.bind("<Leave>", lambda e: b.configure(bg=color))

        _btn(f"  {L.t('panel_calibrate')}",_AMBER,  self._on_cal_click)
        _btn(f"  {L.t('panel_hand')}",   _BLUE,   self._on_hand_click)
        _btn(f"  {L.t('panel_how_to')}",  _PURPLE, self._open_help)
        _btn(f"  {L.t('panel_quit')}",    _RED,    self._on_quit_click)
        # Overlay toggle butonu (ayri renk ile)
        self._overlay_btn = _btn(f"  {L.t('panel_overlay_on')}",
                                 "#374151", self._toggle_overlay)

    def _open_overlay(self) -> None:
        """Surekli durum overlay'ini olusturur."""
        self._overlay = StatusOverlay(self._root)
        self._overlay.build()

    def _refresh_panel(self) -> None:
        if not self._panel or not self._panel.winfo_exists():
            return
        L  = _lang_mod.get()
        st = self._state
        try:
            lh = st.get("left_hand", False)
            self._v_hand.configure(
                text=L.t("hand_left") if lh else L.t("hand_right"), fg=_BLUE)
            cal = st.get("calibrated", False)
            self._v_cal.configure(
                text=L.t("startup_cal_ok") if cal else L.t("startup_cal_no"),
                fg=_GREEN if cal else _RED)
            self._v_fps.configure(text=f"{st.get('fps',0):.0f} fps")
            kb = st.get("kb_visible", False)
            self._v_kb.configure(
                text=L.t("hud_kb_on") if kb else L.t("hud_kb_off"),
                fg=_GREEN if kb else _DIM)
            ct = st.get("cam_top", True)
            self._v_cam.configure(
                text=L.t("hud_cam_top") if ct else L.t("hud_cam_back"),
                fg=_GREEN if ct else _DIM)
            self._v_dwell.configure(text=f"{st.get('dwell_sec',1.5)}s")
        except Exception:
            pass

    # ── Yardim Ekrani ─────────────────────────────────────────────────────────

    def _open_help(self) -> None:
        if self._help and self._help.winfo_exists():
            self._help.lift()
            return

        L     = _lang_mod.get()
        is_tr = L.code == "tr"

        win = tk.Toplevel(self._root)
        self._help = win
        win.title("GestureMouse - " + ("Nasil Kullanilir?" if is_tr else "How To Use?"))
        win.configure(bg=_BG)
        win.resizable(False, False)
        win.attributes("-topmost", True)
        try:
            win.attributes("-alpha", 0.97)
        except Exception:
            pass

        scr_w = win.winfo_screenwidth()
        scr_h = win.winfo_screenheight()
        ww, wh = 480, 780
        win.geometry(f"{ww}x{wh}+{scr_w-ww-20}+{(scr_h-wh)//2}")

        f_head = ("Consolas", 14, "bold")
        f_lbl  = ("Consolas", 10, "bold")
        f_sm   = ("Consolas", 9)
        f_desc = ("Consolas", 8)

        canvas = tk.Canvas(win, bg=_BG, highlightthickness=0, width=ww, height=wh-50)
        canvas.pack(fill="both", expand=True)
        inner = tk.Frame(canvas, bg=_BG)
        canvas.create_window((0,0), window=inner, anchor="nw", width=ww)
        inner.bind("<Configure>", lambda e: canvas.configure(
            scrollregion=canvas.bbox("all")))
        canvas.bind_all("<MouseWheel>",
            lambda e: canvas.yview_scroll(int(-1*(e.delta/120)), "units"))

        pad = 14
        tk.Label(inner,
                 text="NASIL KULLANILIR?" if is_tr else "HOW TO USE?",
                 font=f_head, fg=_GREEN, bg=_BG, pady=12).pack(fill="x", padx=pad)

        # Dwell aciklamasi
        df = tk.Frame(inner, bg=_CARD, padx=10, pady=8)
        df.pack(fill="x", padx=pad, pady=(0,6))
        tk.Label(df,
                 text="DWELL SISTEMI" if is_tr else "DWELL SYSTEM",
                 font=f_lbl, fg=_AMBER, bg=_CARD).pack(anchor="w")
        dwell_txt = (
            "Isaret parmagi haric tum jestler bekleme sistemi kullanir.\n"
            "Jesti yap ve halka dolana kadar bekle — islem o zaman tetiklenir."
            if is_tr else
            "All gestures except pointing use the dwell system.\n"
            "Hold the gesture until the ring fills — action fires then."
        )
        tk.Label(df, text=dwell_txt, font=f_desc,
                 fg=_DIM, bg=_CARD, justify="left").pack(anchor="w")

        # Jest listesi
        if is_tr:
            items = [
                ("[1]", "IMLEC",     "Isaret Parmagi",
                 "Sadece isaret parmagi yukari, diger parmaklar kapali.\nFareyi dogrudan hareket ettirir — bekleme yok.",
                 _GREEN),
                ("[2]", "SOL TIK",   "Pinch",
                 "Basparmak ucu ile isaret parmagi ucunu birlestir.\nHalka dolunca sol tik yapar.",
                 _AMBER),
                ("[3]", "SAG TIK",   "V Isareti",
                 "Isaret ve orta parmak acik, yuzuk ve serce kapali.\nHalka dolunca sag tik yapar.",
                 _BLUE),
                ("[4]", "KAYDIRMA",  "4 Parmak",
                 "Isaret, orta, yuzuk, serce acik — basparmak kapali.\nHalka dolunca aktif: el yukari/asagi hareketiyle kaydir.",
                 _PURPLE),
                ("[5]", "KLAVYE",    "3 Parmak",
                 "Isaret, orta, yuzuk acik — serce ve basparmak kapali.\nHalka dolunca ekran klavyesini acar/kapatir.",
                 _CYAN),
                ("[6]", "KAMERA",    "Yumruk",
                 "Tum parmaklar kapali, siki yumruk.\nHalka dolunca kamera penceresini one/arkaya alir.",
                 _RED),
                ("[7]", "ALT+TAB",   "Kurt",
                 "Orta ve yuzuk parmak basparmaga deger,\nisaret ve serce duz yukari.\nHalka dolunca pencere degistirir.",
                 "#fb923c"),
                ("[8]", "BASILI TUT",  "Yumruk + Basparmak",
                 "Elini yumruk yapip yumrugu uste dogru tut.\nSadece basparmak yukarida kalsin.\nHalka dolunca sol tus basili kalir.\nElini hareket ettirerek surukle.\nBaska jest yapinca birakir.",
                 "#ffd700"),
            ]
        else:
            items = [
                ("[1]", "CURSOR",    "Index Finger",
                 "Only index finger raised, others closed.\nMoves mouse directly — no dwell needed.",
                 _GREEN),
                ("[2]", "L-CLICK",   "Pinch",
                 "Bring thumb tip and index fingertip together.\nWhen ring fills: left click.",
                 _AMBER),
                ("[3]", "R-CLICK",   "V Sign",
                 "Index and middle up, ring and pinky closed.\nWhen ring fills: right click.",
                 _BLUE),
                ("[4]", "SCROLL",    "4 Fingers",
                 "Index, middle, ring, pinky up — thumb closed.\nWhen ready: move hand up/down to scroll.",
                 _PURPLE),
                ("[5]", "KEYBOARD",  "3 Fingers",
                 "Index, middle, ring up — pinky and thumb closed.\nWhen ring fills: toggles on-screen keyboard.",
                 _CYAN),
                ("[6]", "CAMERA",    "Fist",
                 "All fingers closed, tight fist.\nWhen ring fills: moves camera window front/back.",
                 _RED),
                ("[7]", "ALT+TAB",   "Wolf",
                 "Middle and ring touch thumb,\nindex and pinky raised straight up.\nWhen ring fills: switches windows.",
                 "#fb923c"),
                ("[8]", "HOLD CLICK", "Fist + Thumb Up",
                 "Close all fingers into a fist, then raise only your thumb.\nWhen ring fills: left button is held down.\nMove your hand to drag anything.\nChange to another gesture to release.",
                 "#ffd700"),
            ]

        for num, action, pose, desc, color in items:
            card = tk.Frame(inner, bg=_CARD, padx=12, pady=8)
            card.pack(fill="x", padx=pad, pady=2)
            top = tk.Frame(card, bg=_CARD)
            top.pack(fill="x")
            tk.Label(top, text=num, font=f_sm, fg=_DIM, bg=_CARD,
                     width=4, anchor="w").pack(side="left")
            tk.Label(top, text=action, font=f_lbl, fg=color, bg=_CARD,
                     width=10, anchor="w").pack(side="left")
            tk.Label(top, text=pose, font=f_sm, fg=_WHITE, bg=_CARD,
                     anchor="w").pack(side="left")
            tk.Label(card, text=desc, font=f_desc, fg="#8888aa",
                     bg=_CARD, justify="left", anchor="w",
                     wraplength=420).pack(fill="x", pady=(4,0))
            tk.Frame(card, height=1, bg=_BORDER).pack(fill="x", pady=(6,0))

        tk.Frame(inner, height=20, bg=_BG).pack()

        close_lbl = "Kapat" if is_tr else "Close"
        tk.Button(win, text=close_lbl, font=("Consolas",10,"bold"),
                  fg=_BG, bg=_GREEN, activebackground="#22c55e",
                  relief="flat", bd=0, padx=20, pady=6,
                  cursor="hand2", command=win.destroy).pack(pady=8)

    # ── Bildirim Popup ────────────────────────────────────────────────────────

    def _show_notify_window(self, gesture: str) -> None:
        L = _lang_mod.get()
        key = {
            "pinch":  "notify_lclick",
            "v_sign": "notify_rclick",
            "four":   "notify_scroll",
            "three":  "notify_keyboard",
            "fist":   "notify_cam",
            "wolf":   "notify_wolf",
        "thumbs_up_hold":    "notify_hold",
        "thumbs_up_release": "notify_release",
        }.get(gesture)
        if not key:
            return
        text = f"  {L.t(key)}  "

        # Eski bildirimi kapat
        if self._notify and self._notify.winfo_exists():
            try:
                self._notify.destroy()
            except Exception:
                pass

        win = tk.Toplevel(self._root)
        self._notify = win
        win.overrideredirect(True)
        win.attributes("-topmost", True)
        try:
            win.attributes("-alpha", 0.88)
        except Exception:
            pass

        tk.Label(win, text=text,
                 font=("Consolas", 13, "bold"),
                 fg="#00e676", bg="#0f0f1a",
                 padx=16, pady=10).pack()

        win.update_idletasks()
        sw = win.winfo_screenwidth()
        ww = win.winfo_width()
        win.geometry(f"+{(sw-ww)//2}+24")
        win.after(900, lambda: win.destroy() if win.winfo_exists() else None)
        # Overlay'i aksiyon rengiyle guncelle
        if self._overlay:
            L2 = _lang_mod.get()
            action_map = {
                "pinch":             "notify_lclick",
                "v_sign":            "notify_rclick",
                "four":              "notify_scroll",
                "three":             "notify_keyboard",
                "fist":              "notify_cam",
                "wolf":              "notify_wolf",
                "thumbs_up_hold":    "notify_hold",
                "thumbs_up_release": "notify_release",
            }
            action_key = action_map.get(gesture, "")
            if action_key:
                self._overlay.update(
                    gesture=gesture.replace("_hold","").replace("_release",""),
                    progress=1.0,
                    scroll_active=False,
                    hold_active=False,
                    action_label=L2.t(action_key),
                    dwell_sec=self._state.get("dwell_sec", 1.5),
                )

    # ── Buton callback'leri ───────────────────────────────────────────────────

    def _toggle_overlay(self) -> None:
        """Durum cubuğunu goster/gizle."""
        L = _lang_mod.get()
        self._overlay_visible = not self._overlay_visible
        if self._overlay and self._overlay._win:
            try:
                if self._overlay_visible:
                    self._overlay._win.deiconify()
                    if hasattr(self, "_overlay_btn") and self._overlay_btn:
                        self._overlay_btn.configure(
                            text=f"  {L.t('panel_overlay_on')}")
                else:
                    self._overlay._win.withdraw()
                    if hasattr(self, "_overlay_btn") and self._overlay_btn:
                        self._overlay_btn.configure(
                            text=f"  {L.t('panel_overlay_off')}")
            except Exception:
                pass

    def _on_cal_click(self) -> None:
        if self.on_calibrate:
            self.on_calibrate()

    def _on_hand_click(self) -> None:
        if self.on_toggle_hand:
            self.on_toggle_hand()

    def _on_quit_click(self) -> None:
        self._running = False
        if self.on_quit:
            self.on_quit()
        try:
            self._root.quit()
        except Exception:
            pass

    @staticmethod
    def _lighten(hex_color: str) -> str:
        try:
            h = hex_color.lstrip("#")
            r,g,b = int(h[0:2],16), int(h[2:4],16), int(h[4:6],16)
            return f"#{min(255,r+30):02x}{min(255,g+30):02x}{min(255,b+30):02x}"
        except Exception:
            return hex_color
