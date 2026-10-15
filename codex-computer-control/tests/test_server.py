import importlib.util
import io
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock, patch, call

from PIL import Image

spec = importlib.util.spec_from_file_location("computer_control", Path(__file__).parents[1] / "server.py")
s = importlib.util.module_from_spec(spec)
sys.modules[spec.name] = s
spec.loader.exec_module(s)
CAPTURE_VIEW = s.capture_view
REQUEST_WORKER = s.request_worker


class ComputerControlTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.stop_patch = patch.object(s, "STOP", Path(self.temp.name) / "STOP")
        self.stop_patch.start()
        self.p = Mock()
        self.p.size.return_value = (800, 600)
        self.p.position.return_value = (100, 200)
        self.p.KEYBOARD_KEYS = ["command", "shift", "alt", "ctrl", "a", "enter", "esc"]
        self.q = Mock()
        self.q.AXIsProcessTrusted.return_value = True
        self.q.CGPreflightScreenCaptureAccess.return_value = True
        self.q.CGDisplayIsActive.return_value = 1
        self.q.CGDisplayIsAsleep.return_value = 0
        self.q.CGSessionCopyCurrentDictionary.return_value = {}
        self.q.kCGHIDEventTap = 0
        self.backend_patch = patch.object(s, "backend", return_value=(self.p, self.q))
        self.backend_patch.start()
        self.accessibility_patch = patch.object(s, "accessibility_allowed", side_effect=self.q.AXIsProcessTrusted)
        self.accessibility_patch.start()
        self.front_patch = patch.object(s, "front_app_path", return_value="/Applications/QQ.app")
        self.front_patch.start()
        self.view_patch = patch.object(s, "capture_view", return_value=(s.Image(data=b"test", format="jpeg"), {}))
        self.view_patch.start()
        self.cache_patch = patch.object(s, "VIEWS", {})
        self.cache_patch.start()
        self.worker_patch = patch.object(s, "request_worker", side_effect=lambda args: s.run_step(**args))
        self.worker_patch.start()

    def tearDown(self):
        self.worker_patch.stop()
        self.cache_patch.stop()
        self.view_patch.stop()
        self.front_patch.stop()
        self.accessibility_patch.stop()
        self.backend_patch.stop()
        self.stop_patch.stop()
        self.temp.cleanup()

    def test_coordinates_reject_outside_and_stop_corner(self):
        for x, y in [(-1, 0), (800, 30), (30, 600), (0, 0)]:
            with self.assertRaises(ValueError):
                s.desktop_click(x, y)
        self.p.click.assert_not_called()

    def test_nonfinite_duration_rejected_before_backend(self):
        for duration in [float("nan"), float("inf"), -1, 6]:
            with self.assertRaises(ValueError):
                s.desktop_move(10, 10, duration)
        self.p.moveTo.assert_not_called()

    def test_permission_denied_prevents_mouse(self):
        self.q.AXIsProcessTrusted.return_value = False
        with self.assertRaises(RuntimeError):
            s.desktop_click(20, 20)
        self.p.click.assert_not_called()

    def test_stop_blocks_screen_input_and_app_launch(self):
        s.STOP.touch()
        with patch.object(s.subprocess, "run") as run:
            for call in [lambda: s.desktop_click(20, 20), s.desktop_screenshot,
                         lambda: s.desktop_type_text("test"), lambda: s.desktop_open_app("Calculator")]:
                with self.assertRaises(RuntimeError):
                    call()
            run.assert_not_called()
        self.p.click.assert_not_called()
        self.q.CGEventPost.assert_not_called()

    def test_hotkey_releases_modifier_when_second_key_fails(self):
        self.p.keyDown.side_effect = [None, RuntimeError("interrupted")]
        with self.assertRaises(RuntimeError):
            s.desktop_hotkey(["cmd", "a"])
        self.assertEqual(self.p.platformModule._keyUp.call_args_list, [call("a"), call("command")])

    def test_hotkey_attempts_all_releases_when_one_fails(self):
        self.p.platformModule._keyUp.side_effect = [RuntimeError("release failed"), None]
        with self.assertRaises(RuntimeError):
            s.desktop_hotkey(["cmd", "a"])
        self.assertEqual(self.p.platformModule._keyUp.call_args_list, [call("a"), call("command")])

    def test_drag_releases_button_on_stop(self):
        self.p.mouseDown.side_effect = lambda **_: s.STOP.touch()
        with self.assertRaises(RuntimeError):
            s.desktop_drag(20, 20, 80, 90)
        self.p.platformModule._mouseUp.assert_called_once_with(100, 200, "left")

    def test_drag_emits_drag_events_instead_of_move_events(self):
        s.desktop_drag(20, 20, 80, 90, duration=0.1)
        self.assertEqual(self.p.platformModule._dragTo.call_count, 2)
        self.p.platformModule._dragTo.assert_called_with(80, 90, "left")

    def test_unicode_utf16_length_and_no_clipboard(self):
        result = s.desktop_type_text("中文🙂")
        self.assertEqual(result["typed_characters"], 3)
        self.assertEqual(self.q.CGEventPost.call_count, 2)
        for call in self.q.CGEventKeyboardSetUnicodeString.call_args_list:
            self.assertEqual(call.args[1:], (4, "中文🙂"))

    def test_typing_checks_stop_between_chunks(self):
        self.q.CGEventPost.side_effect = lambda *_: s.STOP.touch()
        with self.assertRaises(RuntimeError):
            s.desktop_type_text("a" * 40)
        self.assertEqual(self.q.CGEventPost.call_count, 2)

    def test_retina_screenshot_is_logical_size(self):
        def capture(args, **kwargs):
            Image.new("RGB", (1600, 1200)).save(args[-1])
        with patch.object(s, "native_screen", return_value=None), patch.object(s.subprocess, "run", side_effect=capture):
            result = s.desktop_screenshot()
        with Image.open(io.BytesIO(result.data)) as im:
            self.assertEqual(im.size, (800, 600))

    def test_native_capture_color_channels_and_row_padding(self):
        self.q.CGDisplayCreateImage.return_value = object()
        self.q.CGImageGetBitsPerPixel.return_value = 32
        self.q.CGImageGetBitsPerComponent.return_value = 8
        self.q.CGImageGetAlphaInfo.return_value = 6
        self.q.CGImageGetBitmapInfo.return_value = 0x2006
        self.q.CGImageGetWidth.return_value = 2
        self.q.CGImageGetHeight.return_value = 1
        self.q.CGImageGetBytesPerRow.return_value = 12
        self.q.CGDataProviderCopyData.return_value = bytes([0, 0, 255, 0, 0, 255, 0, 0, 0, 0, 0, 0])
        with patch.object(s.platform, "mac_ver", return_value=("13.7.8", (), "")):
            im = s.native_screen(self.q)
        self.assertEqual([im.getpixel((x, 0)) for x in range(2)], [(255, 0, 0), (0, 255, 0)])

    def test_native_capture_falls_back_on_new_macos(self):
        with patch.object(s.platform, "mac_ver", return_value=("15.0", (), "")):
            self.assertIsNone(s.native_screen(self.q))
        self.q.CGDisplayCreateImage.assert_not_called()

    def test_application_name_is_single_argument(self):
        with patch.object(s.subprocess, "run") as run:
            s.desktop_open_app("Some App; $(echo test)")
            self.assertEqual(run.call_args.args[0], ["/usr/bin/open", "-a", "Some App; $(echo test)"])
            self.assertNotIn("shell", run.call_args.kwargs)

    def test_step_validates_later_action_before_first_click(self):
        with self.assertRaises(ValueError):
            s.desktop_step([{"action": "click", "x": 20, "y": 20},
                            {"action": "press", "key": "not-a-key"}], settle_ms=0)
        self.p.click.assert_not_called()

    def test_step_returns_image_and_timing_in_same_result(self):
        with patch.object(s, "capture_screen", return_value=s.Image(data=b"test", format="jpeg")):
            result = s.desktop_step([{"action": "click", "x": 20, "y": 20},
                                     {"action": "type", "text": "你好"}], settle_ms=0)
        self.assertFalse(result.isError)
        self.assertEqual(result.structuredContent["completed"], 2)
        self.assertEqual([c.type for c in result.content], ["text", "image"])
        self.assertEqual(result.content[1].mimeType, "image/jpeg")
        self.assertGreaterEqual(result.structuredContent["total_ms"], 0)

    def test_step_stops_when_foreground_changes(self):
        foreground = ["/Applications/QQ.app"]
        self.p.click.side_effect = lambda *a, **kw: foreground.__setitem__(0, "/Applications/Other.app")
        with patch.object(s, "app_path", return_value="/Applications/QQ.app"), \
             patch.object(s, "focus_app"), \
             patch.object(s, "front_app_path", side_effect=lambda: foreground[0]), \
             patch.object(s, "capture_screen", return_value=s.Image(data=b"test", format="jpeg")):
            result = s.desktop_step([{"action": "click", "x": 20, "y": 20},
                                     {"action": "type", "text": "do not type"}], app="QQ", settle_ms=0)
        self.assertTrue(result.isError)
        self.assertEqual(result.structuredContent["completed"], 1)
        self.assertIn("Foreground app changed", result.structuredContent["error"])
        self.q.CGEventPost.assert_not_called()
        self.assertIsNone(s.EXPECTED_APP.get())

    def test_step_missing_screen_permission_prevents_input(self):
        self.q.CGPreflightScreenCaptureAccess.return_value = False
        with self.assertRaises(RuntimeError):
            s.desktop_step([{"action": "click", "x": 20, "y": 20}])
        self.p.click.assert_not_called()

    def test_step_rejects_unknown_fields_and_too_many_actions(self):
        with self.assertRaises(ValueError):
            s.desktop_step([{"action": "click", "x": 20, "y": 20, "shell": "bad"}])
        with self.assertRaises(ValueError):
            s.desktop_step([{"action": "press", "key": "enter"}] * 33)
        self.p.press.assert_not_called()

    def test_thumbnail_crop_coordinates_map_to_screen(self):
        with patch.object(s, "read_screen", return_value=Image.new("RGB", (1600, 900))):
            picture, metadata = CAPTURE_VIEW("ultra", s.Region(x=200, y=100, width=1024, height=512))
        self.assertEqual(metadata["image_size"], [512, 256])
        view = s.VIEWS[metadata["view_id"]]
        self.assertEqual(s.view_point(view, 100, 50), (400, 200))
        with Image.open(io.BytesIO(picture.data)) as im:
            self.assertEqual(im.size, (512, 256))

    def test_step_uses_view_coordinates_before_click(self):
        s.VIEWS["frame"] = {"origin": [100, 50], "logical_size": [400, 200],
                            "image_size": [200, 100], "app_path": "/Applications/QQ.app",
                            "created": s.time.monotonic()}
        result = s.desktop_step([{"action": "click", "x": 50, "y": 25}], view_id="frame", output="none")
        self.assertFalse(result.isError)
        self.p.click.assert_called_once_with(200, 100, clicks=1, interval=0, button="left")
        s.capture_view.assert_not_called()

    def test_expired_view_rejected_before_input(self):
        s.VIEWS["old"] = {"created": s.time.monotonic() - 121}
        with self.assertRaises(ValueError):
            s.desktop_step([{"action": "click", "x": 10, "y": 10}], view_id="old")
        self.p.click.assert_not_called()

    def test_assertion_failure_prevents_send_and_does_not_repeat_input(self):
        with patch.object(s, "find_text", side_effect=RuntimeError("Expected exact text not found")):
            result = s.desktop_step([{"action": "type", "text": "test"},
                {"action": "assert_text", "text": "test"}, {"action": "press", "key": "enter"}], output="none")
        self.assertTrue(result.isError)
        self.assertEqual(result.structuredContent["completed"], 1)
        self.p.press.assert_not_called()
        self.assertEqual(self.q.CGEventPost.call_count, 2)
        s.capture_view.assert_called_once()

    def test_text_target_ambiguity_prevents_click(self):
        with patch.object(s, "accessibility_text", return_value=[
                {"text": "爸爸", "x": 10, "y": 10}, {"text": "爸爸", "x": 20, "y": 20}]):
            with self.assertRaises(RuntimeError):
                s.click_text("爸爸")
        self.p.click.assert_not_called()

    def test_text_fallback_boxes_use_screen_coordinates(self):
        with patch.object(s, "accessibility_text", return_value=[]), \
             patch.object(s, "recognize_text", return_value=[{"text": "爸 爸", "x": 150, "y": 120, "confidence": 0.99}]):
            s.click_text("爸爸")
        self.p.click.assert_called_once_with(150, 120, clicks=1, interval=0, button="left")

    def test_text_only_output_contains_no_image(self):
        with patch.object(s, "accessibility_text", return_value=[{"text": "爸爸", "x": 40, "y": 50}]):
            result = s.desktop_step([], output="text")
        self.assertFalse(result.isError)
        self.assertEqual([part.type for part in result.content], ["text"])
        self.assertEqual(result.structuredContent["text_coordinates"], "screen")
        s.capture_view.assert_not_called()

    def test_budget_stops_remaining_actions(self):
        clock = [0.0]
        self.p.click.side_effect = lambda *a, **kw: clock.__setitem__(0, 1.0)
        with patch.object(s.time, "monotonic", side_effect=lambda: clock[0]):
            result = s.desktop_step([{"action": "click", "x": 10, "y": 10},
                {"action": "press", "key": "enter"}], budget_ms=100, output="none")
        self.assertTrue(result.isError)
        self.assertEqual(result.structuredContent["completed"], 1)
        self.p.press.assert_not_called()

    def test_hard_deadline_kills_worker_and_never_replays(self):
        child = Mock()
        child.stdin.fileno.return_value = 123
        child.stdout.fileno.return_value = 456
        clock = [0.0]
        def tick():
            clock[0] += 0.4
            return clock[0]
        progress = b'{"kind":"progress","data":{"completed":0,"current":"press"}}\n'
        selections = [([child.stdout], [child.stdin], [])] + [([], [], [])] * 20
        with patch.object(s, "ensure_worker", return_value=child) as start, \
             patch.object(s, "stop_worker") as stop, \
             patch.object(s.select, "select", side_effect=selections), \
             patch.object(s.os, "read", return_value=progress), \
             patch.object(s.os, "write", return_value=100000), \
             patch.object(s.time, "monotonic", side_effect=tick), \
             patch.object(s, "DATA", Path(self.temp.name)):
            result = REQUEST_WORKER({"actions": [{"action": "press", "key": "enter"}], "budget_ms": 100})
        self.assertTrue(result.isError)
        self.assertTrue(s.STOP.exists())
        self.assertEqual(result.structuredContent["uncertain_action"], "press")
        self.assertTrue(result.structuredContent["observe_again_required"])
        start.assert_called_once()
        stop.assert_called_once()

    def test_native_delivery_targets_foreground_pid_and_warps_cursor(self):
        quartz = Mock()
        quartz.kCGEventMouseMoved = 5
        quartz.kCGEventKeyDown = 10
        quartz.kCGEventKeyUp = 11
        quartz.CGEventGetType.return_value = 5
        quartz.CGEventGetLocation.return_value = (250, 120)
        quartz.CGWarpMouseCursorPosition.return_value = 0
        workspace = Mock()
        workspace.frontmostApplication.return_value.processIdentifier.return_value = 999
        fake_appkit = SimpleNamespace(NSWorkspace=SimpleNamespace(sharedWorkspace=lambda: workspace))
        with patch.dict(sys.modules, {"AppKit": fake_appkit}):
            s.EventBridge(quartz).CGEventPost(0, "event")
        quartz.CGEventPostToPid.assert_called_once_with(999, "event")
        quartz.CGWarpMouseCursorPosition.assert_called_once_with((250, 120))
        quartz.CGEventPost.assert_not_called()

    def test_pid_delivery_preserves_shortcut_modifier_flags(self):
        quartz = Mock()
        quartz.kCGEventKeyDown, quartz.kCGEventKeyUp = 10, 11
        quartz.CGEventGetType.side_effect = [10, 10, 11]
        quartz.CGEventGetIntegerValueField.side_effect = [55, 0, 55]
        quartz.CGEventGetFlags.return_value = 0
        workspace = Mock()
        workspace.frontmostApplication.return_value.processIdentifier.return_value = 999
        fake_appkit = SimpleNamespace(NSWorkspace=SimpleNamespace(sharedWorkspace=lambda: workspace))
        with patch.dict(sys.modules, {"AppKit": fake_appkit}):
            bridge = s.EventBridge(quartz)
            for event in ("cmd-down", "a-down", "cmd-up"):
                bridge.CGEventPost(0, event)
        self.assertEqual([c.args[1] for c in quartz.CGEventSetFlags.call_args_list], [1 << 20, 1 << 20, 0])

    def test_release_after_stop_goes_to_original_pid(self):
        quartz = Mock()
        quartz.kCGEventKeyDown, quartz.kCGEventKeyUp = 10, 11
        quartz.CGEventGetType.side_effect = [10, 11, 10]
        quartz.CGEventGetIntegerValueField.return_value = 55
        quartz.CGEventGetFlags.return_value = 0
        workspace = Mock()
        workspace.frontmostApplication.return_value.processIdentifier.return_value = 999
        fake = SimpleNamespace(NSWorkspace=SimpleNamespace(sharedWorkspace=lambda: workspace))
        with patch.dict(sys.modules, {"AppKit": fake}):
            bridge = s.EventBridge(quartz)
            bridge.CGEventPost(0, "down")
            s.STOP.touch()
            workspace.frontmostApplication.return_value.processIdentifier.return_value = 777
            bridge.CGEventPost(0, "up")
            with self.assertRaises(RuntimeError):
                bridge.CGEventPost(0, "new-down")
        self.assertEqual(quartz.CGEventPostToPid.call_args_list, [call(999, "down"), call(999, "up")])
        self.assertEqual(bridge.modifiers, 0)
        self.assertEqual(bridge.held_events, {})

    def test_unicode_attempts_release_when_post_raises(self):
        self.q.CGEventPost.side_effect = [RuntimeError("interrupted"), None]
        with self.assertRaises(RuntimeError):
            s.desktop_type_text("hello")
        self.assertEqual(self.q.CGEventPost.call_count, 2)

    def test_drag_releases_when_mouse_down_wrapper_raises(self):
        self.p.mouseDown.side_effect = RuntimeError("post-event failure")
        with self.assertRaises(RuntimeError):
            s.desktop_drag(20, 20, 80, 90)
        self.p.platformModule._mouseUp.assert_called_once()

    def test_sleeping_display_rejected_before_any_input(self):
        self.q.CGDisplayIsAsleep.return_value = 1
        with self.assertRaisesRegex(RuntimeError, "display asleep"):
            s.desktop_step([{"action": "press", "key": "enter"}])
        self.p.press.assert_not_called()


if __name__ == "__main__":
    unittest.main()
