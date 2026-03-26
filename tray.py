"""
System tray — pystray tabanlı, dil destekli.
"""
import threading, platform
import lang as _lang_mod

_OS = platform.system()

class SystemTray:
    def __init__(self, on_toggle_cam, on_calibrate, on_quit):
        self._on_toggle_cam = on_toggle_cam
        self._on_calibrate  = on_calibrate
        self._on_quit       = on_quit
        self._icon          = None
        self.available      = False

    def start(self) -> None:
        L = _lang_mod.get()
        try:
            import pystray
            from PIL import Image, ImageDraw
            menu = pystray.Menu(
                pystray.MenuItem(L.t("tray_toggle_cam"), lambda: self._on_toggle_cam()),
                pystray.MenuItem(L.t("tray_calibrate"),  lambda: self._on_calibrate()),
                pystray.Menu.SEPARATOR,
                pystray.MenuItem(L.t("tray_quit"),       lambda: self._on_quit()),
            )
            self._icon = pystray.Icon("GestureMouse", self._make_icon(),
                                      "GestureMouse", menu)
            self.available = True
            threading.Thread(target=self._run, daemon=True).start()
            print(L.t("tray_started"))
        except ImportError:
            print(L.t("tray_no_lib"))
        except Exception as e:
            print(f"[Tray] {e}")

    def stop(self) -> None:
        if self._icon:
            try: self._icon.stop()
            except Exception: pass

    def _run(self) -> None:
        try: self._icon.run()
        except Exception: pass

    def _make_icon(self):
        from PIL import Image, ImageDraw
        img = Image.new("RGBA", (64, 64), (0,0,0,0))
        d   = ImageDraw.Draw(img)
        d.ellipse([2,2,62,62], fill=(30,30,50,255), outline=(80,200,120,255), width=2)
        for fx1,fy1,fx2,fy2 in [(22,20,28,42),(29,16,35,42),(36,18,42,42),(43,22,49,42)]:
            d.rounded_rectangle([fx1,fy1,fx2,fy2], radius=3, fill=(80,200,120,255))
        d.rounded_rectangle([18,38,52,56], radius=5, fill=(80,200,120,255))
        return img
