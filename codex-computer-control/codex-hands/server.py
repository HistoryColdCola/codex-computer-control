"""Local stdio MCP server. Importing it performs no desktop actions."""
from __future__ import annotations

import io
import json
import math
import os
import atexit
import select
import signal
import sys
import threading
import platform
import subprocess
import tempfile
import time
from contextvars import ContextVar
from functools import lru_cache
from pathlib import Path
from typing import Annotated, Literal, Union
from uuid import uuid4

from mcp.server.fastmcp import FastMCP, Image
from mcp.types import CallToolResult, TextContent
from pydantic import BaseModel, ConfigDict, Field, TypeAdapter

DATA = Path.home() / ".local/share/codex-hands"
STOP = DATA / "STOP"
mcp = FastMCP("codex-hands")
EXPECTED_APP = ContextVar("expected_app", default=None)
STEP_PROGRESS = ContextVar("step_progress", default=None)
VIEWS = {}
PROFILES = {"fast": (768, 30), "ultra": (512, 20), "detail": (None, 85)}
_BRIDGE = None
_WORKER = None
_WORKER_LOCK = threading.Lock()
_WORKER_PARENT = os.getppid() if "--worker" in sys.argv else None


class EventBridge:
    """Use documented per-process event delivery rather than the HID power path."""
    def __init__(self, quartz):
        self.quartz = quartz
        self.modifiers = 0
        self.held_events = {}

    def __getattr__(self, name):
        return getattr(self.quartz, name)

    def CGEventPost(self, _tap, event):
        kind = self.quartz.CGEventGetType(event)
        q = self.quartz
        key = None
        releasing = False
        if kind in (q.kCGEventKeyDown, q.kCGEventKeyUp):
            key = ("key", q.CGEventGetIntegerValueField(event, q.kCGKeyboardEventKeycode))
            releasing = kind == q.kCGEventKeyUp
        for down, up, button in ((q.kCGEventLeftMouseDown, q.kCGEventLeftMouseUp, "left"),
                                  (q.kCGEventRightMouseDown, q.kCGEventRightMouseUp, "right"),
                                  (q.kCGEventOtherMouseDown, q.kCGEventOtherMouseUp, "other")):
            if kind in (down, up):
                key, releasing = ("mouse", button), kind == up
        # Only releases of our own held inputs may bypass STOP/focus checks.
        # Deliver them to the original process, never to a newly focused app.
        pid = self.held_events.get(key) if releasing else None
        if pid is None:
            check_stop()
            from AppKit import NSWorkspace
            front_app_path()
            app = NSWorkspace.sharedWorkspace().frontmostApplication()
            if app is None:
                raise RuntimeError("No foreground application for event delivery.")
            pid = app.processIdentifier()
        if kind in (self.quartz.kCGEventKeyDown, self.quartz.kCGEventKeyUp):
            code = key[1]
            masks = {55: 1 << 20, 54: 1 << 20, 56: 1 << 17, 60: 1 << 17,
                     58: 1 << 19, 61: 1 << 19, 59: 1 << 18, 62: 1 << 18}
            mask = masks.get(code, 0)
            flags = self.quartz.CGEventGetFlags(event)
            if kind == self.quartz.kCGEventKeyDown:
                self.modifiers |= mask
            else:
                self.modifiers &= ~mask
                flags &= ~mask
            self.quartz.CGEventSetFlags(event, flags | self.modifiers)
        if kind in (self.quartz.kCGEventMouseMoved, self.quartz.kCGEventLeftMouseDragged,
                    self.quartz.kCGEventRightMouseDragged, self.quartz.kCGEventOtherMouseDragged):
            if self.quartz.CGWarpMouseCursorPosition(self.quartz.CGEventGetLocation(event)) != 0:
                raise RuntimeError("Unable to move cursor in the current session.")
        self.quartz.CGEventPostToPid(pid, event)
        if key is not None:
            if releasing:
                self.held_events.pop(key, None)
            else:
                self.held_events[key] = pid


def backend():
    global _BRIDGE
    if platform.system() != "Darwin":
        raise RuntimeError("This version supports macOS only.")
    import pyautogui
    import Quartz
    pyautogui.FAILSAFE = True
    pyautogui.PAUSE = 0.005
    if _BRIDGE is None:
        _BRIDGE = EventBridge(Quartz)
        pyautogui.platformModule.Quartz = _BRIDGE
    return pyautogui, _BRIDGE


def check_stop():
    if _WORKER_PARENT is not None and os.getppid() != _WORKER_PARENT:
        raise RuntimeError("Controller disconnected; workflow aborted.")
    if STOP.exists():
        raise RuntimeError("Emergency stop is active. Ask the user to run resume.command.")
    expected = EXPECTED_APP.get()
    if expected is not None and front_app_path() != expected:
        raise RuntimeError("Foreground app changed. Batch stopped; do not automatically replay completed actions.")


def accessibility_allowed():
    from ApplicationServices import AXIsProcessTrusted
    return bool(AXIsProcessTrusted())


def require_desktop(q):
    display = q.CGMainDisplayID()
    session = q.CGSessionCopyCurrentDictionary() or {}
    if session.get("CGSSessionScreenIsLocked") or not q.CGDisplayIsActive(display) or q.CGDisplayIsAsleep(display):
        raise RuntimeError("Desktop unavailable: display asleep/inactive or session locked. Wake/unlock the Mac; no input was sent.")


def control():
    check_stop()
    p, q = backend()
    require_desktop(q)
    if not accessibility_allowed():
        raise RuntimeError("Enable Accessibility for the hosting app/Python in macOS System Settings.")
    p.failSafeCheck()
    return p, q


def finite(value: float, low: float, high: float, label: str):
    if not math.isfinite(value) or not low <= value <= high:
        raise ValueError(f"{label} must be between {low} and {high}.")


def point(p, x: int, y: int):
    width, height = p.size()
    if not 0 <= x < width or not 0 <= y < height:
        raise ValueError(f"Coordinates outside primary display ({width} x {height}).")
    if x == 0 and y == 0:
        raise ValueError("The top-left corner is reserved for emergency stop.")


@mcp.tool()
def desktop_status() -> dict:
    """Get permissions, primary display size and pointer position without moving it."""
    p, q = backend()
    return {"platform": platform.system(), "accessibility": accessibility_allowed(),
            "screen_recording": bool(q.CGPreflightScreenCaptureAccess()),
            "desktop_active": bool(q.CGDisplayIsActive(q.CGMainDisplayID())),
            "display_asleep": bool(q.CGDisplayIsAsleep(q.CGMainDisplayID())),
            "width": p.size().width, "height": p.size().height,
            "mouse": list(p.position()), "stopped": STOP.exists(),
            "stop_file": str(STOP), "coordinates": "primary-display logical pixels"}


def native_screen(q):
    """Fast in-memory capture on macOS versions with CGDisplayCreateImage."""
    from PIL import Image as PILImage
    try:
        # Apple removed this API in macOS 15. Keep the existing CLI fallback there.
        if int(platform.mac_ver()[0].split(".")[0]) >= 15:
            return None
        captured = q.CGDisplayCreateImage(q.CGMainDisplayID())
        if captured is None or q.CGImageGetBitsPerPixel(captured) != 32:
            return None
        if q.CGImageGetBitsPerComponent(captured) != 8:
            return None
        first = q.CGImageGetAlphaInfo(captured) in (2, 4, 6)
        little = (q.CGImageGetBitmapInfo(captured) & 0x7000) == 0x2000
        raw_mode = ("BGRX" if first else "XBGR") if little else ("XRGB" if first else "RGBX")
        size = (q.CGImageGetWidth(captured), q.CGImageGetHeight(captured))
        stride = q.CGImageGetBytesPerRow(captured)
        pixels = bytes(q.CGDataProviderCopyData(q.CGImageGetDataProvider(captured)))
        return PILImage.frombytes("RGB", size, pixels, "raw", raw_mode, stride, 1)
    except (AttributeError, TypeError, ValueError, RuntimeError):
        return None


def read_screen():
    check_stop()
    p, q = backend()
    require_desktop(q)
    if not q.CGPreflightScreenCaptureAccess():
        raise RuntimeError("Enable Screen Recording for the hosting app/Python in macOS System Settings.")
    from PIL import Image as PILImage
    im = native_screen(q)
    if im is None:
        with tempfile.TemporaryDirectory(prefix="codex-hands-") as folder:
            target = Path(folder) / "screen.png"
            subprocess.run(["/usr/sbin/screencapture", "-x", "-m", str(target)],
                           check=True, capture_output=True, timeout=10)
            with PILImage.open(target) as file_image:
                im = file_image.convert("RGB")
    logical = tuple(p.size())
    if im.size != logical:
        im = im.resize(logical, PILImage.Resampling.LANCZOS)
    return im


def capture_screen(format: Literal["jpeg", "png"] = "jpeg") -> Image:
    im = read_screen()
    buffer = io.BytesIO()
    if format == "jpeg":
        im.save(buffer, "JPEG", quality=80)
    else:
        im.save(buffer, "PNG")
    return Image(data=buffer.getvalue(), format=format)


class Region(BaseModel):
    model_config = ConfigDict(extra="forbid")
    x: int = Field(ge=0)
    y: int = Field(ge=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)


def crop_screen(im, region):
    if region is None:
        return im
    if region.x + region.width > im.width or region.y + region.height > im.height:
        raise ValueError("Crop region is outside the primary display.")
    return im.crop((region.x, region.y, region.x + region.width, region.y + region.height))


def capture_view(profile="ultra", crop=None):
    from PIL import Image as PILImage
    im = crop_screen(read_screen(), crop)
    width, height = im.size
    maximum, quality = PROFILES[profile]
    if maximum and width > maximum:
        im = im.resize((maximum, max(1, round(height * maximum / width))), PILImage.Resampling.BILINEAR)
    data = io.BytesIO()
    im.save(data, "JPEG", quality=quality)
    token = uuid4().hex[:12]
    geometry = {"origin": [crop.x, crop.y] if crop else [0, 0],
                "logical_size": [width, height], "image_size": list(im.size),
                "app_path": front_app_path(), "created": time.monotonic()}
    if len(VIEWS) >= 16:
        VIEWS.pop(next(iter(VIEWS)))
    VIEWS[token] = geometry
    public = {k: v for k, v in geometry.items() if k not in ("created", "app_path")}
    public.update({"view_id": token, "profile": profile, "image_bytes": len(data.getvalue())})
    return Image(data=data.getvalue(), format="jpeg"), public


def view_point(view, x, y):
    width, height = view["image_size"]
    if not 0 <= x < width or not 0 <= y < height:
        raise ValueError("Image coordinates are outside the supplied view.")
    ox, oy = view["origin"]
    lw, lh = view["logical_size"]
    return round(ox + x * lw / width), round(oy + y * lh / height)


def ax_attr(ax, element, name):
    error, value = ax.AXUIElementCopyAttributeValue(element, name, None)
    return value if error == 0 else None


def accessibility_text(region=None):
    """Bounded text extraction; never traverses other/background app windows."""
    import ApplicationServices as ax
    from AppKit import NSWorkspace
    if not accessibility_allowed():
        return []
    front_app_path()  # refresh Cocoa activation notifications
    current = NSWorkspace.sharedWorkspace().frontmostApplication()
    root = ax.AXUIElementCreateApplication(current.processIdentifier())
    ax.AXUIElementSetMessagingTimeout(root, 0.02)
    window = ax_attr(ax, root, "AXFocusedWindow")
    if window is None:
        return []
    todo, rows, visited = [window], [], 0
    deadline = time.monotonic() + 0.15
    while todo and visited < 200 and time.monotonic() < deadline:
        element = todo.pop()
        visited += 1
        if ax_attr(ax, element, "AXHidden") is True:
            continue
        role = ax_attr(ax, element, "AXRole")
        if role == "AXSecureTextField":
            continue
        for attribute in ("AXTitle", "AXValue", "AXDescription"):
            text = ax_attr(ax, element, attribute)
            if not isinstance(text, str) or not text.strip() or len(text) > 500:
                continue
            pos, size = ax_attr(ax, element, "AXPosition"), ax_attr(ax, element, "AXSize")
            if pos is None or size is None:
                continue
            okp, pos = ax.AXValueGetValue(pos, ax.kAXValueCGPointType, None)
            oks, size = ax.AXValueGetValue(size, ax.kAXValueCGSizeType, None)
            if not okp or not oks or size.width <= 0 or size.height <= 0:
                continue
            cx, cy = round(pos.x + size.width / 2), round(pos.y + size.height / 2)
            width, height = backend()[0].size()
            if not (0 <= cx < width and 0 <= cy < height):
                continue
            if region and not (region.x <= cx < region.x + region.width and region.y <= cy < region.y + region.height):
                continue
            rows.append({"text": text, "role": str(role), "x": cx, "y": cy})
            break
        todo.extend(ax_attr(ax, element, "AXChildren") or [])
    # Apps with only a window/group label (e.g. QQ) need the OCR fallback.
    return [row for row in rows if row["role"] not in ("AXWindow", "AXGroup")]


def recognize_text(region=None):
    """Local Apple Vision OCR; boxes are in logical SCREEN coordinates."""
    import Vision
    from Foundation import NSData
    im = crop_screen(read_screen(), region)
    data = io.BytesIO()
    im.save(data, "JPEG", quality=80)
    encoded = data.getvalue()
    request = Vision.VNRecognizeTextRequest.alloc().init()
    request.setRecognitionLevel_(Vision.VNRequestTextRecognitionLevelAccurate)
    request.setRecognitionLanguages_(["zh-Hans", "en-US"])
    request.setUsesLanguageCorrection_(False)
    handler = Vision.VNImageRequestHandler.alloc().initWithData_options_(
        NSData.dataWithBytes_length_(encoded, len(encoded)), {})
    success, error = handler.performRequests_error_([request], None)
    if not success:
        raise RuntimeError(f"Local OCR failed: {error}")
    ox, oy = (region.x, region.y) if region else (0, 0)
    rows = []
    for observation in request.results() or []:
        candidates = observation.topCandidates_(1)
        if not candidates:
            continue
        box = observation.boundingBox()
        cx = round(ox + (box.origin.x + box.size.width / 2) * im.width)
        cy = round(oy + (1 - box.origin.y - box.size.height / 2) * im.height)
        rows.append({"text": str(candidates[0].string()), "x": cx, "y": cy,
                     "confidence": round(float(candidates[0].confidence()), 2)})
    return rows


def normalized(text):
    return "".join(text.split())


def find_text(text, region=None, timeout_ms=0):
    deadline = time.monotonic() + timeout_ms / 1000
    while True:
        check_stop()
        rows = accessibility_text(region)
        matches = [r for r in rows if normalized(r["text"]) == normalized(text)]
        if not matches:
            rows = recognize_text(region)
            # Vision's scores differ across recognition languages (this Mac
            # reports 0.3 for clearly rendered Chinese). Require exact scoped,
            # unique text instead of an arbitrary cross-language score cutoff.
            matches = [r for r in rows if normalized(r["text"]) == normalized(text)]
        # Identical AX attributes from one control count as one match.
        matches = list({(r["x"], r["y"]): r for r in matches}.values())
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise RuntimeError("Text target is ambiguous. Specify a tighter screen region.")
        if time.monotonic() >= deadline:
            raise RuntimeError(f"Expected exact text not found: {text}")
        time.sleep(0.03)


@mcp.tool()
def desktop_screenshot(format: Literal["jpeg", "png"] = "jpeg") -> Image:
    """Capture primary display at logical mouse coordinates. JPEG is faster; PNG is lossless."""
    return capture_screen(format)


@mcp.tool()
def desktop_move(x: int, y: int, duration: float = 0.1) -> dict:
    """Move pointer to primary-display logical coordinates."""
    finite(duration, 0, 5, "duration")
    p, _ = control()
    point(p, x, y)
    p.moveTo(x, y, duration=duration)
    return {"mouse": [x, y]}


@mcp.tool()
def desktop_click(x: int, y: int, button: Literal["left", "right", "middle"] = "left",
                  clicks: int = 1) -> dict:
    """Click a visible target; clicks=2 for double-click."""
    if not 1 <= clicks <= 3:
        raise ValueError("clicks must be 1 to 3.")
    p, _ = control()
    point(p, x, y)
    p.click(x, y, clicks=clicks, interval=0.06 if clicks > 1 else 0, button=button)
    return {"clicked": [x, y], "button": button, "clicks": clicks}


@mcp.tool()
def desktop_drag(start_x: int, start_y: int, end_x: int, end_y: int,
                 duration: float = 0.8, button: Literal["left", "right"] = "left") -> dict:
    """Drag between two observed points, releasing the button even on interruption."""
    finite(duration, 0.1, 5, "duration")
    p, _ = control()
    point(p, start_x, start_y)
    point(p, end_x, end_y)
    p.moveTo(start_x, start_y, duration=0.2)
    try:
        p.mouseDown(button=button)
        # Short segments allow STOP and the corner failsafe to interrupt long drags.
        count = max(1, math.ceil(duration / 0.05))
        for i in range(1, count + 1):
            check_stop()
            p.failSafeCheck()
            p.platformModule._dragTo(round(start_x + (end_x - start_x) * i / count),
                                     round(start_y + (end_y - start_y) * i / count), button)
            time.sleep(duration / count)
    finally:
        # A safety release must work even if the pointer is in the failsafe corner.
        p.platformModule._mouseUp(*p.position(), button)
    return {"dragged_to": [end_x, end_y]}


@mcp.tool()
def desktop_scroll(clicks: int, horizontal: bool = False) -> dict:
    """Scroll at the current pointer. Positive is up/right; negative is down/left."""
    if not -100 <= clicks <= 100:
        raise ValueError("clicks must be between -100 and 100.")
    p, _ = control()
    (p.hscroll if horizontal else p.scroll)(clicks)
    return {"scrolled": clicks, "horizontal": horizontal}


def key_names(p, keys: list[str]) -> list[str]:
    aliases = {"cmd": "command", "meta": "command", "option": "alt", "control": "ctrl",
               "return": "enter", "escape": "esc", "arrowup": "up", "arrowdown": "down",
               "arrowleft": "left", "arrowright": "right"}
    result = [aliases.get(k.lower(), k.lower()) for k in keys]
    if not result or len(result) > 6 or any(k not in p.KEYBOARD_KEYS for k in result):
        raise ValueError("Use 1 to 6 valid keyboard names, such as command, shift, a, enter.")
    return result


@mcp.tool()
def desktop_hotkey(keys: list[str]) -> dict:
    """Press shortcut keys together, e.g. ['command','l'] or ['command','shift','s']."""
    p, _ = control()
    names = key_names(p, keys)
    held = []
    try:
        for key in names:
            check_stop()
            held.append(key)
            p.keyDown(key)
        time.sleep(0.005)
    finally:
        release_error = None
        for key in reversed(held):
            try:
                p.platformModule._keyUp(key)
            except Exception as exc:
                release_error = release_error or exc
        if release_error is not None:
            raise release_error
    return {"pressed": names}


@mcp.tool()
def desktop_press(key: str, presses: int = 1) -> dict:
    """Press an individual key (enter, tab, esc, arrows, backspace)."""
    if not 1 <= presses <= 50:
        raise ValueError("presses must be 1 to 50.")
    p, _ = control()
    name = key_names(p, [key])[0]
    for _ in range(presses):
        check_stop()
        p.press(name)
    return {"pressed": name, "count": presses}


@mcp.tool()
def desktop_type_text(text: str) -> dict:
    """Type Unicode text, including Chinese, into the focused field without using clipboard."""
    if len(text) > 10000:
        raise ValueError("Text is limited to 10000 characters per call.")
    p, q = control()
    # Small Unicode events stay interruptible and preserve surrogate pairs.
    for offset in range(0, len(text), 16):
        check_stop()
        p.failSafeCheck()
        chunk = text[offset:offset + 16]
        length = len(chunk.encode("utf-16-le")) // 2
        event = q.CGEventCreateKeyboardEvent(None, 0, True)
        release = q.CGEventCreateKeyboardEvent(None, 0, False)
        q.CGEventKeyboardSetUnicodeString(event, length, chunk)
        q.CGEventKeyboardSetUnicodeString(release, length, chunk)
        try:
            q.CGEventPost(q.kCGHIDEventTap, event)
        finally:
            q.CGEventPost(q.kCGHIDEventTap, release)
        time.sleep(0.005)
    return {"typed_characters": len(text)}


@mcp.tool()
def desktop_open_app(name: str) -> dict:
    """Open/activate a named macOS app using open -a; no shell interpolation."""
    check_stop()
    if not name.strip() or len(name) > 200 or "\x00" in name:
        raise ValueError("Provide a valid application name.")
    subprocess.run(["/usr/bin/open", "-a", name], check=True, capture_output=True, timeout=10)
    return {"opened": name}


@mcp.tool()
def desktop_wait(seconds: float = 0.1) -> dict:
    """Wait up to five seconds for an interface update, checking the STOP file."""
    finite(seconds, 0, 5, "seconds")
    deadline = time.monotonic() + seconds
    while time.monotonic() < deadline:
        check_stop()
        time.sleep(min(0.05, max(0, deadline - time.monotonic())))
    return {"waited": seconds}


class StepAction(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ClickAction(StepAction):
    action: Literal["click"]
    x: int
    y: int
    button: Literal["left", "right", "middle"] = "left"
    clicks: int = Field(default=1, ge=1, le=3)


class MoveAction(StepAction):
    action: Literal["move"]
    x: int
    y: int
    duration: float = Field(default=0.1, ge=0, le=1, allow_inf_nan=False)


class TypeAction(StepAction):
    action: Literal["type"]
    text: str = Field(max_length=10000)


class DragAction(StepAction):
    action: Literal["drag"]
    start_x: int
    start_y: int
    end_x: int
    end_y: int
    duration: float = Field(default=0.3, ge=0.1, le=2, allow_inf_nan=False)
    button: Literal["left", "right"] = "left"


class PressAction(StepAction):
    action: Literal["press"]
    key: str
    presses: int = Field(default=1, ge=1, le=50)


class HotkeyAction(StepAction):
    action: Literal["hotkey"]
    keys: list[str] = Field(min_length=1, max_length=6)


class ScrollAction(StepAction):
    action: Literal["scroll"]
    clicks: int = Field(ge=-100, le=100)
    horizontal: bool = False


class WaitAction(StepAction):
    action: Literal["wait"]
    seconds: float = Field(ge=0, le=1, allow_inf_nan=False)


class ClickTextAction(StepAction):
    action: Literal["click_text"]
    text: str = Field(min_length=1, max_length=500)
    region: Region | None = None
    timeout_ms: int = Field(default=0, ge=0, le=3000)


class AssertTextAction(StepAction):
    action: Literal["assert_text"]
    text: str = Field(min_length=1, max_length=500)
    region: Region | None = None
    timeout_ms: int = Field(default=0, ge=0, le=3000)


def click_text(text, region=None, timeout_ms=0):
    region = Region.model_validate(region) if region else None
    target = find_text(text, region, timeout_ms)
    # Focus/STOP checks happen again immediately before clicking.
    return desktop_click(target["x"], target["y"])


def assert_text(text, region=None, timeout_ms=0):
    region = Region.model_validate(region) if region else None
    target = find_text(text, region, timeout_ms)
    return {"verified": text, "x": target["x"], "y": target["y"]}


Action = Annotated[Union[ClickAction, MoveAction, TypeAction, PressAction,
                         HotkeyAction, ScrollAction, WaitAction, DragAction,
                         ClickTextAction, AssertTextAction], Field(discriminator="action")]
ACTION_LIST = TypeAdapter(list[Action])


@lru_cache(maxsize=32)
def app_path(name: str) -> str:
    from AppKit import NSWorkspace
    found = NSWorkspace.sharedWorkspace().fullPathForApplication_(name)
    if not found:
        raise ValueError(f"Application not found: {name}")
    return str(Path(found).resolve())


def front_app_path() -> str | None:
    from AppKit import NSWorkspace
    from Foundation import NSDate, NSRunLoop
    # NSWorkspace activation notifications need a Cocoa run-loop iteration in
    # this stdio process; otherwise frontmostApplication can remain stale.
    NSRunLoop.currentRunLoop().runUntilDate_(NSDate.dateWithTimeIntervalSinceNow_(0.001))
    app = NSWorkspace.sharedWorkspace().frontmostApplication()
    url = app.bundleURL() if app else None
    return str(Path(url.path()).resolve()) if url else None


def focus_app(name: str, target: str):
    if front_app_path() != target:
        from AppKit import NSWorkspace, NSApplicationActivateIgnoringOtherApps
        running = NSWorkspace.sharedWorkspace().runningApplications()
        candidate = next((a for a in running if a.bundleURL() and
                          str(Path(a.bundleURL().path()).resolve()) == target), None)
        if candidate is not None:
            candidate.activateWithOptions_(NSApplicationActivateIgnoringOtherApps)
        else:
            desktop_open_app(name)
    deadline = time.monotonic() + 2
    while front_app_path() != target:
        check_stop()
        if time.monotonic() >= deadline:
            raise RuntimeError("Application has not become foreground. Wait and inspect; no input was sent.")
        time.sleep(0.02)


def run_step(actions: list[Action], app: str | None = None, settle_ms: int = 0,
                 profile: Literal["fast", "ultra", "detail"] = "ultra",
                 output: Literal["image", "text", "none"] = "image",
                 view_id: str | None = None, crop: Region | None = None,
                 budget_ms: int = 8000, include_text: bool = False) -> CallToolResult:
    """Fast local workflow: up to 32 actions, optional exact-text guards, ONE response.

    Default: low-resolution JPEG. Pass returned view_id for coordinates on that image.
    OCR/AX text coordinates and crop regions are always logical screen coordinates.
    click_text/assert_text run locally: verify recipient header and draft before send.
    output=text reads controls/OCR without an image; output=none skips capture on success.
    On error, completed actions may have taken effect: do not replay blindly.
    """
    started = time.perf_counter()
    finite(settle_ms, 0, 500, "settle_ms")
    finite(budget_ms, 100, 20000, "budget_ms")
    if profile not in PROFILES or output not in ("image", "text", "none"):
        raise ValueError("Unknown capture profile or output mode.")
    crop = Region.model_validate(crop) if crop else None
    parsed = ACTION_LIST.validate_python(actions)
    if len(parsed) > 32:
        raise ValueError("Use at most 32 actions per step.")
    view = VIEWS.get(view_id) if view_id else None
    if view_id and (view is None or time.monotonic() - view["created"] > 120):
        raise ValueError("Unknown/expired view_id. Observe again before using image coordinates.")
    if sum(a.seconds for a in parsed if isinstance(a, WaitAction)) > 2:
        raise ValueError("Total explicit wait time must not exceed 2 seconds.")
    check_stop()
    p, q = backend()
    require_desktop(q)
    width, height = p.size()
    if crop and (crop.x + crop.width > width or crop.y + crop.height > height):
        raise ValueError("Crop region is outside the primary display.")
    if view:
        converted = []
        for item in parsed:
            values = item.model_dump()
            if isinstance(item, (ClickAction, MoveAction)):
                values["x"], values["y"] = view_point(view, item.x, item.y)
            elif isinstance(item, DragAction):
                values["start_x"], values["start_y"] = view_point(view, item.start_x, item.start_y)
                values["end_x"], values["end_y"] = view_point(view, item.end_x, item.end_y)
            converted.append(values)
        parsed = ACTION_LIST.validate_python(converted)
    # Validate the entire batch before opening apps or executing any input.
    if not q.CGPreflightScreenCaptureAccess():
        raise RuntimeError("Enable Screen Recording in macOS System Settings.")
    trusted = accessibility_allowed()
    if parsed and not trusted:
        raise RuntimeError("Enable Accessibility in macOS System Settings.")
    for item in parsed:
        if isinstance(item, (ClickAction, MoveAction)):
            point(p, item.x, item.y)
        elif isinstance(item, DragAction):
            point(p, item.start_x, item.start_y)
            point(p, item.end_x, item.end_y)
        elif isinstance(item, PressAction):
            key_names(p, [item.key])
        elif isinstance(item, HotkeyAction):
            key_names(p, item.keys)
        elif isinstance(item, (ClickTextAction, AssertTextAction)) and item.region:
            if item.region.x + item.region.width > width or item.region.y + item.region.height > height:
                raise ValueError("Text region is outside the primary display.")
    target = app_path(app) if app is not None else None
    if view and view["app_path"] and target and view["app_path"] != target:
        raise ValueError("View belongs to a different app. Observe the intended app first.")
    if target is None and parsed:
        target = view["app_path"] if view else front_app_path()
        if target is None:
            raise RuntimeError("No foreground application; observe and activate the target first.")
    dispatch = {"click": desktop_click, "move": desktop_move, "type": desktop_type_text,
                "press": desktop_press, "hotkey": desktop_hotkey,
                "scroll": desktop_scroll, "wait": desktop_wait, "drag": desktop_drag,
                "click_text": click_text, "assert_text": assert_text}
    completed = 0
    error = None
    token = None
    results = []
    deadline = time.monotonic() + budget_ms / 1000
    try:
        if STEP_PROGRESS.get():
            STEP_PROGRESS.get()({"completed": 0, "current": "focus"})
        if app is not None:
            focus_app(app, target)
        if target is not None:
            token = EXPECTED_APP.set(target)
        for item in parsed:
            check_stop()
            if time.monotonic() >= deadline:
                raise RuntimeError("Workflow time budget exceeded; no remaining actions were run.")
            arguments = item.model_dump(exclude={"action"})
            if "timeout_ms" in arguments:
                arguments["timeout_ms"] = min(arguments["timeout_ms"], max(0, int((deadline-time.monotonic())*1000)))
            if STEP_PROGRESS.get():
                STEP_PROGRESS.get()({"completed": completed, "current": item.action})
            results.append(dispatch[item.action](**arguments))
            completed += 1
            if STEP_PROGRESS.get():
                STEP_PROGRESS.get()({"completed": completed, "current": None})
        if settle_ms:
            desktop_wait(settle_ms / 1000)
    except Exception as exc:
        error = str(exc)
    finally:
        if token is not None:
            EXPECTED_APP.reset(token)
    actions_ms = round((time.perf_counter() - started) * 1000, 1)
    content = []
    observation = {}
    capture_started = time.perf_counter()
    try:
        if output == "text" and error is None:
            check_stop()
            rows = accessibility_text(crop)
            source = "accessibility"
            if not rows:
                rows, source = recognize_text(crop), "ocr"
            observation = {"text": rows, "text_source": source, "text_coordinates": "screen"}
        elif output == "image" or error is not None:
            snapshot, observation = capture_view(profile, crop)
            content.append(snapshot.to_image_content())
            if include_text and error is None:
                rows = accessibility_text(crop)
                source = "accessibility"
                if not rows:
                    rows, source = recognize_text(crop), "ocr"
                observation.update({"text": rows, "text_source": source, "text_coordinates": "screen"})
    except Exception as exc:
        error = error or str(exc)
    info = {"completed": completed, "requested": len(parsed), "error": error,
            "accessibility": trusted, "screen_recording": True,
            "app": app, "results": results, "actions_ms": actions_ms,
            "capture_ms": round((time.perf_counter() - capture_started) * 1000, 1),
            "total_ms": round((time.perf_counter() - started) * 1000, 1)}
    info.update(observation)
    content.insert(0, TextContent(type="text", text=json.dumps(info, ensure_ascii=False)))
    return CallToolResult(content=content, structuredContent=info, isError=error is not None)


def stop_worker():
    global _WORKER
    if _WORKER is not None:
        child, _WORKER = _WORKER, None
        if child.poll() is None:
            child.terminate()
            try:
                child.wait(timeout=0.15)
            except subprocess.TimeoutExpired:
                child.kill()
                child.wait(timeout=0.5)
        for stream in (child.stdin, child.stdout):
            if stream is not None:
                stream.close()


def ensure_worker():
    global _WORKER
    if _WORKER is None or _WORKER.poll() is not None:
        stop_worker()
        _WORKER = subprocess.Popen([sys.executable, str(Path(__file__).resolve()), "--worker"],
                                   stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                   stderr=subprocess.DEVNULL, bufsize=0)
        os.set_blocking(_WORKER.stdin.fileno(), False)
        os.set_blocking(_WORKER.stdout.fileno(), False)
    return _WORKER


def request_worker(parameters):
    """The MCP process stays responsive even if an OS input/OCR call hangs."""
    with _WORKER_LOCK:
        check_stop()
        actions = parameters["actions"]
        names = [a.action if isinstance(a, BaseModel) else a["action"] for a in actions]
        started = time.monotonic()
        hard_seconds = min(20, max(3, parameters["budget_ms"] / 1000 + 2))
        progress = {"completed": 0, "current": "starting"}
        try:
            child = ensure_worker()
            encode = lambda item: item.model_dump() if isinstance(item, BaseModel) else item
            pending = json.dumps(parameters, default=encode).encode() + b"\n"
            buffer = b""
            while time.monotonic() - started < hard_seconds:
                check_stop()
                readable, writable, _ = select.select([child.stdout], [child.stdin] if pending else [], [], 0.02)
                if writable:
                    sent = os.write(child.stdin.fileno(), pending)
                    pending = pending[sent:]
                if readable:
                    data = os.read(child.stdout.fileno(), 65536)
                    if not data:
                        raise RuntimeError("Execution worker exited before returning a result.")
                    buffer += data
                    while b"\n" in buffer:
                        line, buffer = buffer.split(b"\n", 1)
                        record = json.loads(line)
                        if record["kind"] == "progress":
                            progress = record["data"]
                        elif record["kind"] == "reply":
                            result = CallToolResult.model_validate(record["data"])
                            if result.structuredContent is not None:
                                result.structuredContent["transport_ms"] = round((time.monotonic()-started)*1000, 1)
                            return result
            raise TimeoutError(f"Execution exceeded the {hard_seconds:g}s hard deadline.")
        except Exception as exc:
            stop_worker()
            # A native input may already have reached its app. Never replay it.
            completed = progress["completed"]
            potentially_mutating = any(name not in ("assert_text", "wait") for name in names[:completed + 1])
            if potentially_mutating:
                DATA.mkdir(parents=True, exist_ok=True)
                STOP.touch()
            info = {"error": str(exc), "completed": completed, "requested": len(names),
                    "uncertain_action": progress["current"], "stopped": STOP.exists(),
                    "observe_again_required": True, "transport_ms": round((time.monotonic()-started)*1000, 1)}
            return CallToolResult(content=[TextContent(type="text", text=json.dumps(info, ensure_ascii=False))],
                                  structuredContent=info, isError=True)


@mcp.tool()
def desktop_step(actions: list[Action], app: str | None = None, settle_ms: int = 0,
                 profile: Literal["fast", "ultra", "detail"] = "ultra",
                 output: Literal["image", "text", "none"] = "image",
                 view_id: str | None = None, crop: Region | None = None,
                 budget_ms: int = 8000, include_text: bool = False) -> CallToolResult:
    """Run a guarded LOCAL workflow, up to 32 actions, with one result.

    Defaults to 512px JPEG. Return view_id for image coordinates; text/region use screen pixels.
    click_text/assert_text locate and verify exact scoped text locally, avoiding model turns.
    Verify recipient header and draft before send. output=text/none can skip images.
    Native execution has a hard deadline (max 20s); an uncertain input pauses, never replays.
    """
    return request_worker(dict(actions=actions, app=app, settle_ms=settle_ms, profile=profile,
                               output=output, view_id=view_id, crop=crop, budget_ms=budget_ms,
                               include_text=include_text))


def worker_loop():
    def progress(data):
        print(json.dumps({"kind": "progress", "data": data}), flush=True)
    STEP_PROGRESS.set(progress)
    for line in sys.stdin.buffer:
        arguments = {}
        try:
            arguments = json.loads(line)
            result = run_step(**arguments)
        except Exception as exc:
            info = {"error": str(exc), "completed": 0, "requested": len(arguments.get("actions", []))}
            result = CallToolResult(content=[TextContent(type="text", text=json.dumps(info, ensure_ascii=False))],
                                    structuredContent=info, isError=True)
        print(json.dumps({"kind": "reply", "data": result.model_dump(by_alias=True)}, ensure_ascii=False), flush=True)


# Keep the default tool palette small so the model chooses a complete workflow
# instead of a separate tool for every mechanical operation. Legacy opt-in.
if os.environ.get("CODEX_HANDS_LEGACY_TOOLS") != "1":
    for name in ("desktop_click", "desktop_move", "desktop_drag", "desktop_scroll",
                 "desktop_hotkey", "desktop_press", "desktop_type_text",
                 "desktop_open_app", "desktop_wait"):
        mcp.remove_tool(name)


if __name__ == "__main__":
    # Load native bridges during connection startup, before the first AI action.
    if "--worker" in sys.argv:
        backend()
        from AppKit import NSWorkspace
        from ApplicationServices import AXIsProcessTrusted
        worker_loop()
    else:
        atexit.register(stop_worker)
        def terminate_controller(_signal, _frame):
            stop_worker()
            raise SystemExit(0)
        signal.signal(signal.SIGTERM, terminate_controller)
        try:
            mcp.run(transport="stdio")
        finally:
            stop_worker()
