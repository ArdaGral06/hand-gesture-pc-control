"""
GestureMouse v2 — El Hareketleriyle Bilgisayar Kontrolu

Thread mimarisi:
  Ana thread  : tkinter UI  (UIManager.run() — burada calisir)
  Arka thread : kamera + jest tespiti + fare kontrolu

Headless mod (Windows/DirectShow fix):
  CAP_DSHOW mesaj kuyruğu icin cv2.waitKey(1) her frame'de cagrilmali.
  Gizli 1x1 pencere + dongunun en basinda waitKey = pump saglanir.
  imshow() gerektirmez.
"""

import sys
import time
import signal
import platform
import threading
import cv2
import pyautogui

from config import Config
cfg = Config()

import lang as _lang_mod
L        = _lang_mod.ask_and_init(cfg)
show_cam = _lang_mod.ask_cam_mode(L)

from hand_tracker import HandTracker
from gesture      import (get_gesture, get_cursor_point,
                           get_scroll_ref, get_palm_center,
                           reset_pinch, set_pinch_threshold)
from mouse_ctrl   import MouseController
from vkeyboard    import VirtualKeyboard
from dwell        import DwellController
from calibration  import CalibrationWizard
from ui_manager   import UIManager
from tray         import SystemTray
import sound

# Config tabanli davranislar
set_pinch_threshold(cfg.get("pinch_threshold", 0.26))
sound.set_enabled(cfg.get("sound_enabled", True))

_OS       = platform.system()
_WIN      = "GestureMouse"
_WIN_PUMP = "_gm_pump_"
_LOW_PERF = bool(cfg.get("low_perf", False))

_COLOR = {
    "pointing":  (100, 255, 100),
    "pinch":     (255, 220, 100),
    "thumbs_up": (255, 215,   0),
    "v_sign":    (100, 200, 255),
    "four":      (180, 120, 255),
    "three":     (255, 100, 200),
    "fist":      ( 80,  80, 255),
    "wolf":      (255, 180,  60),
    "none":      (120, 120, 120),
}
_BG  = (18, 18, 30)
_DIM = (70, 70, 70)


# ── Gesture stabilizasyonu ────────────────────────────────────────────────────

class GestureLock:
    """
    Ham jest akisini stabilize eder.
    CONFIRM_N frame art arda gorulunce onaylanir.
    HOLD_N frame boyunca kisa kesintilere ragmen korunur.
    """
    CONFIRM_N = 4
    HOLD_N    = 10

    def __init__(self):
        self.stable = "none"
        self._cand  = "none"
        self._cc    = 0
        self._hc    = 0

    def update(self, raw: str) -> str:
        if raw == self._cand:
            self._cc += 1
        else:
            self._cand = raw
            self._cc   = 1
        if self._cc >= self.CONFIRM_N:
            if raw != self.stable:
                self.stable = raw
                self._hc    = 0
        elif self.stable != "none" and self.stable != raw:
            self._hc += 1
            if self._hc >= self.HOLD_N:
                self.stable = "none"
                self._hc    = 0
        else:
            self._hc = 0
        return self.stable

    def reset(self) -> None:
        self.stable = "none"
        self._cand  = "none"
        self._cc    = 0
        self._hc    = 0
        reset_pinch()

    @property
    def lock_progress(self) -> float:
        return min(self._cc / self.CONFIRM_N, 1.0)


# ── HUD yardimcilari ──────────────────────────────────────────────────────────

def _gesture_label(g: str, scroll_active: bool, hold_active: bool) -> str:
    if g == "four" and scroll_active:
        return L.t("hud_scroll_active")
    if g == "thumbs_up" and hold_active:
        return L.t("hud_hold_active")
    return L.t({
        "pointing":  "hud_move",
        "pinch":     "hud_lclick",
        "thumbs_up": "hud_hold",
        "v_sign":    "hud_rclick",
        "four":      "hud_scroll",
        "three":     "hud_keyboard",
        "fist":      "hud_cam",
        "wolf":      "hud_wolf",
        "none":      "hud_none",
    }.get(g, "hud_none"))


def _gesture_tip(g: str, progress: float, scroll_active: bool,
                 hold_active: bool) -> str:
    if g == "none":
        return L.t("hud_tip_none")
    if g == "pointing":
        return L.t("hud_tip_pointing")
    if g == "four" and scroll_active:
        return L.t("hud_scroll_active")
    if g == "thumbs_up" and hold_active:
        return L.t("hud_tip_holding")
    if progress >= 1.0:
        return L.t("hud_tip_ready")
    if progress > 0:
        return L.t("hud_tip_dwell")
    return L.t({
        "pinch":     "hud_tip_pinch",
        "thumbs_up": "hud_tip_thumbsup",
        "v_sign":    "hud_tip_vsign",
        "four":      "hud_tip_scroll",
        "three":     "hud_tip_three",
        "fist":      "hud_tip_fist",
        "wolf":      "hud_tip_wolf",
    }.get(g, "hud_tip_none"))


def _draw_hud(frame, stable: str, glock: GestureLock,
              progress: float, landmarks, fps: float,
              scroll_active: bool, hold_active: bool,
              calibrated: bool, kb_on: bool, cam_top: bool) -> None:
    h, w = frame.shape[:2]
    col  = _COLOR.get(stable, (200, 200, 200))

    # Ust bar
    cv2.rectangle(frame, (0, 0), (w, 56), _BG, -1)
    label = _gesture_label(stable, scroll_active, hold_active)
    cv2.putText(frame, label, (12, 36),
                cv2.FONT_HERSHEY_DUPLEX, 0.88, col, 2, cv2.LINE_AA)
    cv2.putText(frame, f"{fps:.0f}fps", (w - 60, 36),
                cv2.FONT_HERSHEY_SIMPLEX, 0.42, _DIM, 1, cv2.LINE_AA)

    # Durum bilgileri (sag)
    for i, (txt, c) in enumerate([
        (L.t("hud_kb_on")    if kb_on       else L.t("hud_kb_off"),
         (80,220,120) if kb_on       else _DIM),
        (L.t("hud_cam_front") if cam_top    else L.t("hud_cam_back"),
         (80,220,120) if cam_top    else _DIM),
        (L.t("hud_cal_ok")   if calibrated  else L.t("hud_cal_no"),
         (80,220,120) if calibrated else (80,80,200)),
    ]):
        cv2.putText(frame, txt, (w - 100, 12 + i * 14),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.35, c, 1, cv2.LINE_AA)

    # Kilit dolum cubugu
    lp = glock.lock_progress
    cv2.rectangle(frame, (0, 53), (w, 56), (25, 25, 45), -1)
    cv2.rectangle(frame, (0, 53), (int(w * lp), 56), col, -1)

    # Dwell halkasi — parmak ucunda
    if stable not in ("none", "pointing") and landmarks and progress > 0:
        cx, cy = get_cursor_point(landmarks)
        ring_r = 30
        cv2.circle(frame, (cx, cy), ring_r, (35, 35, 55), 3)
        angle = int(progress * 360)
        if angle > 0:
            ring_col = (60, 220, 60) if progress >= 1.0 else col
            cv2.ellipse(frame, (cx, cy), (ring_r, ring_r),
                        -90, 0, angle, ring_col, 3, cv2.LINE_AA)
        cv2.circle(frame, (cx, cy), 5, col, -1)
        if progress < 1.0:
            sn = cfg.get("dwell_sec", 1.5)
            cv2.putText(frame, f"{sn*(1-progress):.1f}{L.t('hud_hold_sec')}",
                        (cx - 16, cy + 52),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.50, col, 1, cv2.LINE_AA)
        else:
            cv2.putText(frame, L.t("hud_ready"), (cx - 22, cy + 52),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.56, (60,220,60), 2, cv2.LINE_AA)

    elif stable == "pointing" and landmarks:
        cx, cy = get_cursor_point(landmarks)
        cv2.circle(frame, (cx, cy), 9, col, -1)
        cv2.circle(frame, (cx, cy), 16, col, 1)

    # Thumbs_up basili tutma gostergesi
    if hold_active:
        hold_txt = L.t("hud_holding_indicator")
        tw, _ = cv2.getTextSize(hold_txt, cv2.FONT_HERSHEY_SIMPLEX, 0.50, 2)
        cx_txt = (w - tw[0]) // 2
        cv2.rectangle(frame, (cx_txt - 8, h // 2 - 26),
                       (cx_txt + tw[0] + 8, h // 2 + 8),
                       (40, 40, 0), -1)
        cv2.putText(frame, hold_txt, (cx_txt, h // 2),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.50, (255, 215, 0), 2, cv2.LINE_AA)

    # Alt bar
    cv2.rectangle(frame, (0, h - 26), (w, h), _BG, -1)
    tip = _gesture_tip(stable, progress, scroll_active, hold_active)
    cv2.putText(frame, tip, (8, h - 9),
                cv2.FONT_HERSHEY_SIMPLEX, 0.38, col, 1, cv2.LINE_AA)
    how_to = L.t("hud_how_to")
    tw, _ = cv2.getTextSize(how_to, cv2.FONT_HERSHEY_SIMPLEX, 0.35, 1)
    cv2.putText(frame, how_to, (w - tw[0] - 8, h - 9),
                cv2.FONT_HERSHEY_SIMPLEX, 0.35, _DIM, 1, cv2.LINE_AA)


# ── Kamera Thread ─────────────────────────────────────────────────────────────

def camera_loop(cap, tracker, mouse, keyboard, dwell, glock,
                calib, state, ui, stop_event):
    _scroll_dz  = 8
    _scroll_spd = cfg.get("scroll_speed", 2)
    _max_drops  = cfg.get("max_drops", 30)

    dropped       = 0
    fps_t         = time.perf_counter()
    fps_val       = 0.0
    fc            = 0
    results       = None
    landmarks     = None
    prev_stable   = "none"
    scroll_ref    = None
    scroll_active = False
    hold_active   = False
    cal_win_open  = False

    # ── Pencere kurulumu ──────────────────────────────────────────────────────
    if show_cam:
        cv2.namedWindow(_WIN, cv2.WINDOW_NORMAL)
        cv2.setWindowProperty(_WIN, cv2.WND_PROP_TOPMOST, 1.0)
    else:
        # Headless: Windows DirectShow mesaj pump icin kucuk arka plan penceresi
        # WND_PROP_VISIBLE eski OpenCV surumlerinde desteklenmeyebilir,
        # o yuzden sadece cok kucuk bir boyuta aliyoruz.
        cv2.namedWindow(_WIN_PUMP, cv2.WINDOW_NORMAL)
        cv2.resizeWindow(_WIN_PUMP, 1, 1)
        # Pencereyi ekranin sag alt kosesine gonder (goru alani disina)
        try:
            sw = int(cv2.getWindowProperty(_WIN_PUMP, cv2.WND_PROP_VISIBLE) or 0)
        except Exception:
            sw = 0
        import ctypes
        try:
            # Windows: pencereyi ekran disi konuma tasiyoruz
            user32 = ctypes.WinDLL("user32")
            hwnd   = user32.FindWindowA(None, b"_gm_pump_")
            if hwnd:
                user32.SetWindowPos(hwnd, 0, -10, -10, 1, 1, 0x0040)
        except Exception:
            pass

    while not stop_event.is_set():

        # ── DirectShow message pump — HER ZAMAN, DONGUSUNUN EN BASINDA ──────
        # Windows CAP_DSHOW icin zorunlu. Headless modda bile cagrilmali.
        cv2.waitKey(1)

        ret, frame = cap.read()
        if not ret:
            dropped += 1
            if dropped >= _max_drops:
                print(L.t("cam_lost"))
                stop_event.set()
                ui.request_quit()
                break
            time.sleep(0.02)
            continue
        dropped = 0
        frame = cv2.flip(frame, 1)

        # State oku
        with state["lock"]:
            need_cal   = state["do_calib"]
            left_hand  = state["left_hand"]
            cam_top    = state["cam_top"]
            calibrated = state["calibrated"]
            kb_on      = state["kb_visible"]

        # ── Kalibrasyon ───────────────────────────────────────────────────────
        if need_cal and not calib.active:
            calib.start()
            glock.reset()
            with state["lock"]:
                state["do_calib"] = False
            if not show_cam and not cal_win_open:
                cv2.namedWindow(_WIN, cv2.WINDOW_NORMAL)
                cv2.setWindowProperty(_WIN, cv2.WND_PROP_TOPMOST, 1.0)
                cal_win_open = True

        if calib.active:
            try:
                results   = tracker.process(frame)
                landmarks = tracker.get_landmarks(results, frame.shape)
            except Exception:
                results = landmarks = None
            done = calib.update(frame, landmarks)
            if done:
                mouse.set_calibration(
                    cfg.get("cal_x_min"), cfg.get("cal_x_max"),
                    cfg.get("cal_y_min"), cfg.get("cal_y_max"),
                )
                # Kalibrasyon pinch esigini da guncelle
                set_pinch_threshold(cfg.get("pinch_threshold", 0.26))
                with state["lock"]:
                    state["calibrated"] = True
                sound.play_confirm()
                if not show_cam and cal_win_open:
                    cv2.destroyWindow(_WIN)
                    cal_win_open = False
            cv2.imshow(_WIN, frame)
            fc += 1
            continue

        # ── Normal jest tespiti ───────────────────────────────────────────────
        try:
            results   = tracker.process(frame)
            landmarks = tracker.get_landmarks(results, frame.shape)
        except Exception as e:
            print(f"[!] {L.t('warn_frame')}: {e}")
            results = landmarks = None

        raw    = get_gesture(landmarks, left_hand)
        stable = glock.update(raw)

        now = time.perf_counter()
        progress, fired = dwell.update(stable, now)

        # ── Jest degisince temizle ────────────────────────────────────────────
        if stable != prev_stable:
            # Thumbs_up jestinden cikinca sol tusu birak
            if prev_stable == "thumbs_up" and hold_active:
                mouse.mouse_up()
                hold_active = False
                sound.play_release()
                ui.show_notify("thumbs_up_release")
                print(f"[+] {L.t('action_hold_end')}")
            # Scroll state'ini sifirla
            if stable != "four":
                scroll_ref    = None
                scroll_active = False
            prev_stable = stable

        # ── Aksiyonlar ────────────────────────────────────────────────────────

        # [1] Cursor hareketi — dwell yok, anlik
        if stable == "pointing" and landmarks:
            try:
                mouse.move(*get_cursor_point(landmarks))
            except pyautogui.FailSafeException:
                print(f"\n{L.t('failsafe')}")
                stop_event.set(); ui.request_quit(); break

        # [4] Scroll — dwell dolduktan sonra surekli aktif
        elif stable == "four" and landmarks:
            if progress >= 1.0:
                scroll_active = True
                wy = get_scroll_ref(landmarks)[1]
                if scroll_ref is None:
                    scroll_ref = wy
                    if fired:
                        sound.play_confirm()
                else:
                    delta = scroll_ref - wy
                    if abs(delta) > _scroll_dz:
                        try:
                            mouse.scroll((1 if delta > 0 else -1) * _scroll_spd)
                        except pyautogui.FailSafeException:
                            print(f"\n{L.t('failsafe')}")
                            stop_event.set(); ui.request_quit(); break
                        scroll_ref += delta * 0.3

        elif scroll_active:
            scroll_active = False
            scroll_ref    = None

        # [8] Thumbs Up — sol tus basili tut + imlec ile surukle.
        # Dwell dolunca mouse_down tetiklenir, jest devam ettikce
        # avuc merkezi takip edilir ve fare imleci hareket eder.
        elif stable == "thumbs_up" and landmarks:
            if fired and not hold_active:
                # Dwell doldu → sol tusu basili tut
                mouse.mouse_down()
                hold_active = True
                sound.play_hold()
                ui.show_notify("thumbs_up_hold")
                print(f"[+] {L.t('action_hold_start')}")
            elif hold_active:
                # Basili tutarken avuc merkezini takip et → surukle
                px, py = get_palm_center(landmarks)
                try:
                    mouse.move(px, py)
                except pyautogui.FailSafeException:
                    print(f"\n{L.t('failsafe')}")
                    mouse.mouse_up()
                    hold_active = False
                    stop_event.set(); ui.request_quit(); break

        # Tek seferlik jestler — sadece fired=True aninda
        elif fired:
            if stable == "pinch":
                try:
                    mouse.left_click()
                except pyautogui.FailSafeException:
                    print(f"\n{L.t('failsafe')}")
                    stop_event.set(); ui.request_quit(); break
                sound.play_confirm()
                ui.show_notify("pinch")
                print(f"[+] {L.t('action_lclick')}")

            elif stable == "v_sign":
                try:
                    mouse.right_click()
                except pyautogui.FailSafeException:
                    print(f"\n{L.t('failsafe')}")
                    stop_event.set(); ui.request_quit(); break
                sound.play_confirm()
                ui.show_notify("v_sign")
                print(f"[+] {L.t('action_rclick')}")

            elif stable == "three":
                keyboard.toggle()
                sound.play_confirm()
                ui.show_notify("three")
                with state["lock"]:
                    state["kb_visible"] = keyboard.visible
                print(f"[+] {L.t('action_keyboard')}")

            elif stable == "wolf":
                pyautogui.hotkey("alt", "tab")
                sound.play_confirm()
                ui.show_notify("wolf")
                print(f"[+] {L.t('action_alttab')}")

            elif stable == "fist":
                with state["lock"]:
                    state["cam_top"] = not state["cam_top"]
                    ct = state["cam_top"]
                if show_cam:
                    cv2.setWindowProperty(
                        _WIN, cv2.WND_PROP_TOPMOST,
                        1.0 if ct else 0.0)
                sound.play_confirm()
                ui.show_notify("fist")
                lbl = L.t("action_cam_top") if ct else L.t("action_cam_back")
                print(f"[+] {lbl}")

        # ── Overlay / gesture durumu guncelle ───────────────────────────────
        ui.update_gesture(
            stable, progress,
            scroll_active=scroll_active,
            hold_active=hold_active,
        )

        # ── FPS + UI guncelleme ───────────────────────────────────────────────
        fc += 1
        if fc % 15 == 0:
            e = now - fps_t
            if e > 0:
                fps_val = 15.0 / e
                with state["lock"]:
                    state["fps"] = fps_val
            fps_t = now
            with state["lock"]:
                s = {k: v for k, v in state.items()
                     if k not in ("lock", "do_calib")}
            ui.update_state(s)

        # ── Kamera onizlemesi ─────────────────────────────────────────────────
        if show_cam:
            if results is not None:
                tracker.draw(frame, results)
            _draw_hud(frame, stable, glock, progress,
                      landmarks, fps_val, scroll_active, hold_active,
                      calibrated, kb_on, cam_top)
            cv2.imshow(_WIN, frame)

    # Thread temizligi
    mouse.release_all()
    cv2.destroyAllWindows()
    print("[Camera] Thread stopped.")


# ── Main ──────────────────────────────────────────────────────────────────────

def main():
    print("\n" + "=" * 54)
    print(f"  GestureMouse  v2  —  {L.t('startup_title')}")
    print("=" * 54)
    print(f"  {L.t('startup_os')}: {_OS}   Python: {sys.version.split()[0]}")
    print(f"  {L.t('startup_dwell')}: {cfg.get('dwell_sec')}s   "
          f"{L.t('startup_hand')}: {cfg.get('dominant_hand')}")
    cal_str = (L.t("startup_cal_ok") if cfg.get("calibrated")
               else L.t("startup_cal_no"))
    print(f"  {L.t('startup_cal')}: {cal_str}")
    print("=" * 54)
    print(f"  {L.t('startup_failsafe')}\n")

    print(L.t("cam_opening"))
    cap = cv2.VideoCapture(
        cfg.get("cam_index", 0),
        cv2.CAP_DSHOW if _OS == "Windows" else cv2.CAP_ANY,
    )
    if not cap.isOpened():
        print(L.t("cam_error"))
        sys.exit(1)

    fw = 320 if _LOW_PERF else cfg.get("frame_w", 640)
    fh = 240 if _LOW_PERF else cfg.get("frame_h", 480)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH,  fw)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, fh)
    cap.set(cv2.CAP_PROP_FPS,          30)
    cap.set(cv2.CAP_PROP_BUFFERSIZE,   1)
    print(L.t("cam_ready") + "\n")

    margin = 20 if not show_cam else cfg.get("margin", 60)

    tracker  = HandTracker(low_perf=_LOW_PERF)
    mouse    = MouseController(
        fw, fh,
        margin            = margin,
        process_noise     = cfg.get("kalman_process_noise",     0.004),
        measurement_noise = cfg.get("kalman_measurement_noise", 0.08),
    )
    keyboard = VirtualKeyboard()
    dwell    = DwellController(dwell_sec=cfg.get("dwell_sec", 1.5))
    glock    = GestureLock()
    calib    = CalibrationWizard(cfg)

    if cfg.get("calibrated"):
        mouse.set_calibration(
            cfg.get("cal_x_min"), cfg.get("cal_x_max"),
            cfg.get("cal_y_min"), cfg.get("cal_y_max"),
        )

    state = {
        "lock":       threading.Lock(),
        "left_hand":  cfg.get("dominant_hand") == "left",
        "calibrated": cfg.get("calibrated", False),
        "fps":        0.0,
        "kb_visible": False,
        "cam_top":    True,
        "dwell_sec":  cfg.get("dwell_sec", 1.5),
        "do_calib":   False,
    }

    stop_event = threading.Event()
    ui         = UIManager()

    def _do_calibrate() -> None:
        with state["lock"]:
            state["do_calib"] = True

    def _do_toggle_hand() -> None:
        with state["lock"]:
            state["left_hand"] = not state["left_hand"]
            lh = state["left_hand"]
        cfg.set("dominant_hand", "left" if lh else "right")
        glock.reset()
        print(f"[+] {L.t('hand_changed')}: "
              f"{L.t('hand_left') if lh else L.t('hand_right')}")

    def _do_quit() -> None:
        stop_event.set()
        ui.stop()

    ui.on_calibrate   = _do_calibrate
    ui.on_toggle_hand = _do_toggle_hand
    ui.on_quit        = _do_quit

    def _sig(s, _):
        print(f"\n{L.t('shutting_down')}")
        _do_quit()
    signal.signal(signal.SIGINT, _sig)

    tray = SystemTray(
        on_toggle_cam = lambda: None,
        on_calibrate  = _do_calibrate,
        on_quit       = _do_quit,
    )
    tray.start()

    cam_thread = threading.Thread(
        target = camera_loop,
        args   = (cap, tracker, mouse, keyboard, dwell,
                  glock, calib, state, ui, stop_event),
        daemon = True,
        name   = "GestureMouse-Camera",
    )
    cam_thread.start()

    sound.play_start()
    print(L.t("started_cam") if show_cam else L.t("started_headless"))

    try:
        ui.run()
    except pyautogui.FailSafeException:
        print(f"\n{L.t('failsafe')}")
    except Exception as e:
        print(f"\n[{L.t('error')}] {e}")
        import traceback
        traceback.print_exc()
    finally:
        stop_event.set()
        cam_thread.join(timeout=5)
        if cam_thread.is_alive():
            print("[Warning] Camera thread still alive after timeout")
        tray.stop()
        keyboard.hide()
        mouse.release_all()     # Basili tutulan tus varsa birak
        tracker.close()         # MediaPipe GPU/CPU temizligi
        cap.release()
        cv2.destroyAllWindows()
        print(L.t("closed"))


if __name__ == "__main__":
    main()
