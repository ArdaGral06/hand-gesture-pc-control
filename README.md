# hand-gesture-pc-control
## GestureMouse

Control your PC with hand gestures using a webcam. GestureMouse tracks a single hand with MediaPipe and maps gestures to mouse actions, scrolling, and an on-screen keyboard toggle. It runs on Windows, macOS, and Linux.

## What It Does

- Moves the mouse cursor with your index finger.
- Clicks, right-clicks, scrolls, and drag-holds via gestures.
- Toggles the OS on-screen keyboard.
- Provides a calibration wizard and a lightweight status overlay.

## Supported Operating Systems

- Windows
- macOS
- Linux

## System Requirements (Recommended)

- Python 3.9+ (3.10 or 3.11 recommended)
- A webcam
- A modern dual-core CPU or better
- 4 GB RAM or more
- GPU is optional (CPU mode works fine)

## Python Dependencies

All dependencies are listed in `requirements.txt` and can be installed in one step using pip.

- `mediapipe` for hand tracking
- `opencv-python` for camera capture and frame processing
- `pyautogui` for mouse control
- `numpy` for math and filtering
- `pystray` and `Pillow` for system tray support

## Installation

1. Create and activate a virtual environment.

Windows (PowerShell):

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
```

macOS / Linux (bash):

```bash
python3 -m venv .venv
source .venv/bin/activate
```

2. Install all required libraries from `requirements.txt`.

```bash
python -m pip install -r requirements.txt
```

This command downloads and installs all packages listed in `requirements.txt` automatically.

3. Run the app.

```bash
python main.py
```

On first run, you will be asked to choose a language and whether the camera preview should be visible.

## Gestures

| Gesture | How to do it | Action |
|---|---|---|
| Pointing | Only index finger up | Move cursor |
| Pinch | Thumb tip touches index tip | Left click |
| V sign | Index + middle up | Right click |
| Four fingers | Index + middle + ring + pinky up | Scroll (move hand up/down) |
| Three fingers | Index + middle + ring up | Toggle on-screen keyboard |
| Fist | All fingers closed | Toggle camera window front/back |
| Thumbs up | Make a fist and point the thumb upward | Press and hold left button (drag) |
| Wolf | Index + pinky up, middle + ring touch thumb | Alt+Tab |

## Configuration

Settings are stored in `config.json` next to the scripts. You can edit this file to customize behavior.

Common options:

| Key | Purpose |
|---|---|
| `cam_index` | Camera device index (0, 1, 2...) |
| `frame_w`, `frame_h` | Camera resolution |
| `dwell_sec` | How long to hold a gesture before it fires |
| `scroll_speed` | Scroll speed multiplier |
| `dominant_hand` | `right` or `left` |
| `low_perf` | Use lower resolution for better FPS |
| `sound_enabled` | Enable or disable sound feedback |

## Platform Notes

- macOS: You must allow Accessibility permissions for your terminal or Python so the app can control the mouse.
- Linux: If Tkinter is missing, install it with your package manager (example: `sudo apt install python3-tk`).
- The on-screen keyboard uses OS tools: `osk.exe` (Windows), system shortcut (macOS), or common Linux keyboards if installed.

## Safety

PyAutoGUI has a safety feature: moving the mouse to the top-left corner will immediately stop the program.

## Troubleshooting

- If the camera does not open, change `cam_index` in `config.json`.
- If tracking is unstable, run calibration from the UI and ensure good lighting.
- If FPS is low, set `low_perf` to `true` and reduce `frame_w` / `frame_h`.



