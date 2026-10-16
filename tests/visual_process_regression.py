"""Fresh visual runs must own their windows and terminate bootloader children."""
import os
import subprocess
import sys
import time
import unittest

from support.windows_visual_processes import (
    descendant_pids, process_snapshot, stop_process_tree,
    use_physical_pixel_coordinates, theme_button_point, stable_visual_desktop,
)


class VisualProcessContract(unittest.TestCase):
    def test_bootloader_descendants_exclude_other_instances(self):
        self.assertEqual(descendant_pids(10, [(10, 1), (11, 10), (12, 11), (20, 1), (21, 20)]), {10, 11, 12})

    def test_out_of_order_snapshot_and_cycle_terminate(self):
        self.assertEqual(descendant_pids(10, [(12, 11), (11, 10), (10, 12)]), {10, 11, 12})

    def test_theme_click_scales_to_physical_monitor_pixels(self):
        self.assertEqual(theme_button_point((10, 20, 1210, 820), 96), (1006, 71))
        self.assertEqual(theme_button_point((10, 20, 1810, 1220), 144), (1504, 96))

    @unittest.skipUnless(os.name == 'nt', 'Actual Windows visual background fixture')
    def test_native_background_fixture_covers_desktop_and_is_destroyed(self):
        import ctypes
        from ctypes import wintypes
        with stable_visual_desktop() as hwnd:
            user=ctypes.WinDLL('user32')
            user.IsWindow.argtypes=[wintypes.HWND]
            self.assertTrue(user.IsWindow(hwnd))
            rect=wintypes.RECT()
            user.GetWindowRect.argtypes=[wintypes.HWND,ctypes.POINTER(wintypes.RECT)]
            self.assertTrue(user.GetWindowRect(hwnd,ctypes.byref(rect)))
            self.assertEqual(rect.right-rect.left,user.GetSystemMetrics(78))
            self.assertEqual(rect.bottom-rect.top,user.GetSystemMetrics(79))
        self.assertFalse(user.IsWindow(hwnd))

    @unittest.skipUnless(os.name == 'nt', 'Actual Windows DPI API contract')
    def test_native_physical_pixel_context(self):
        use_physical_pixel_coordinates()

    @unittest.skipUnless(os.name == 'nt', 'Actual Windows process API contract')
    def test_native_snapshot_contains_current_process(self):
        self.assertIn(os.getpid(), {pid for pid, _ in process_snapshot()})

    @unittest.skipUnless(os.name == 'nt', 'Actual Windows taskkill tree contract')
    def test_native_cleanup_removes_parent_and_child(self):
        child_code = 'import time; time.sleep(60)'
        parent_code = (
            'import subprocess,sys,time; '
            f'p=subprocess.Popen([sys.executable,"-c",{child_code!r}]); '
            'print(p.pid,flush=True); time.sleep(60)'
        )
        process = subprocess.Popen([sys.executable, '-c', parent_code], stdout=subprocess.PIPE, text=True)
        try:
            child_pid = int(process.stdout.readline().strip())
            self.assertIn(child_pid, descendant_pids(process.pid, process_snapshot()))
            stop_process_tree(process)
            deadline = time.monotonic() + 5
            while time.monotonic() < deadline and child_pid in {pid for pid, _ in process_snapshot()}:
                time.sleep(0.05)
            self.assertNotIn(child_pid, {pid for pid, _ in process_snapshot()})
        finally:
            stop_process_tree(process)
            process.stdout.close()


if __name__ == '__main__':
    unittest.main()
