"""Exercise screenshot evidence on Linux without importing Windows APIs."""
import ast
import argparse
import json
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from PIL import Image, ImageChops


SOURCE = Path(__file__).resolve().parent / "visual_flicker_windows.py"
tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
names = {"normalized_image_distance", "startup_endpoint_check"}
functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
namespace = {"Path": Path, "ImageChops": ImageChops}
exec(compile(ast.Module(body=functions, type_ignores=[]), str(SOURCE), "exec"), namespace)
check = namespace["startup_endpoint_check"]


class StartupEvidenceContract(unittest.TestCase):
    def test_zero_frame_capture_is_a_failure(self):
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, 'No startup frames'):
                check([], Path(directory), 'empty')
    def test_exact_prelaunch_desktop_is_loading_and_all_frames_are_retained(self):
        desktop = Image.new('RGB', (32, 24), 'blue')
        application = Image.new('RGB', (32, 24), 'white')
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = check([(0, desktop), (.025, application), (.05, application)], root, 'loading', desktop_reference=desktop)
            self.assertFalse(result['endpoint_flicker_detected'])
            self.assertEqual(result['desktop_loading_frames'], 1)
            self.assertEqual(result['application_frames'], 2)
            self.assertGreater(result['endpoint_distances'][0]['distance'], .08)
            self.assertEqual(len(list((root / 'loading_sequence').glob('*.png'))), 3)

    def test_partial_black_ui_and_return_to_desktop_are_not_excused(self):
        desktop = Image.new('RGB', (32, 24), 'blue')
        application = Image.new('RGB', (32, 24), 'white')
        black = Image.new('RGB', (32, 24), 'black')
        mixed = application.copy()
        mixed.paste(black.crop((0, 0, 32, 12)), (0, 0))
        for first in [black, mixed]:
            with self.subTest(first=first.getpixel((0, 0))), tempfile.TemporaryDirectory() as directory:
                result = check([(0, first), (.025, application)], Path(directory), 'bad', desktop_reference=desktop)
                self.assertTrue(result['endpoint_flicker_detected'])
                self.assertEqual(result['desktop_loading_frames'], 0)
        with tempfile.TemporaryDirectory() as directory:
            result = check([(0, application), (.025, desktop), (.05, application)], Path(directory), 'return', desktop_reference=desktop)
            self.assertTrue(result['endpoint_flicker_detected'])
            self.assertEqual(result['desktop_loading_frames'], 0)

    def test_desktop_only_cannot_pass_as_application_startup(self):
        desktop = Image.new('RGB', (32, 24), 'blue')
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(RuntimeError, 'No application pixels'):
                check([(0, desktop), (.025, desktop)], Path(directory), 'absent', desktop_reference=desktop)

    def test_capture_failure_preserves_partial_report_and_original_error(self):
        main_node = next(node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name == 'main')
        def fail(exe, out, report):
            report['startup_runs'].append({'run': 1, 'frames': 0})
            raise RuntimeError('injected clipped desktop')
        scope = {'Path': Path, 'argparse': argparse, 'json': json, '_run_visual_tests': fail}
        exec(compile(ast.Module(body=[main_node], type_ignores=[]), str(SOURCE), 'exec'), scope)
        with tempfile.TemporaryDirectory() as temporary:
            with patch.object(sys, 'argv', ['visual', '--exe', 'test.exe', '--out', temporary]):
                with self.assertRaisesRegex(RuntimeError, 'injected clipped desktop'):
                    scope['main']()
            report = json.loads((Path(temporary) / 'report.json').read_text())
            self.assertEqual(report['error']['message'], 'injected clipped desktop')
            self.assertEqual(report['startup_runs'], [{'run': 1, 'frames': 0}])

    def test_stable_frames_keep_references_without_false_failure(self):
        image = Image.new("RGB", (32, 24), "white")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = check([(0.0, image), (0.025, image)], root, "stable")
            self.assertFalse(result["endpoint_flicker_detected"])
            self.assertEqual(result["endpoint_threshold"], 0.08)
            self.assertTrue((root / "stable_first.png").is_file())
            self.assertTrue((root / "stable_reference.png").is_file())
            self.assertFalse((root / "stable_sequence").exists())

    def test_initial_paint_is_still_rejected_and_all_frames_retained(self):
        dark = Image.new("RGB", (32, 24), "black")
        light = Image.new("RGB", (32, 24), "white")
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            result = check([(0.0, dark), (0.025, light), (0.05, light)], root, "paint")
            self.assertTrue(result["endpoint_flicker_detected"])
            self.assertEqual(result["endpoint_anomaly_frames"], 1)
            self.assertEqual(len(list((root / "paint_sequence").glob("*.png"))), 3)
            self.assertEqual([x["distance"] for x in result["endpoint_distances"]], [1.0, 0.0, 0.0])
            with Image.open(root / "paint_first.png") as image:
                self.assertEqual(image.getpixel((0, 0)), (0, 0, 0))
            with Image.open(root / "paint_reference.png") as image:
                self.assertEqual(image.getpixel((0, 0)), (255, 255, 255))


if __name__ == "__main__":
    unittest.main()
