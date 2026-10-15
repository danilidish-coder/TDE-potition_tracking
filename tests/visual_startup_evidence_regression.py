"""Exercise screenshot evidence on Linux without importing Windows APIs."""
import ast
import argparse
import json
import sys
import tempfile
import unittest
from unittest.mock import patch
from pathlib import Path

from PIL import Image


SOURCE = Path(__file__).resolve().parent / "visual_flicker_windows.py"
tree = ast.parse(SOURCE.read_text(encoding="utf-8"))
names = {"normalized_image_distance", "startup_endpoint_check"}
functions = [node for node in tree.body if isinstance(node, ast.FunctionDef) and node.name in names]
namespace = {"Path": Path}
exec(compile(ast.Module(body=functions, type_ignores=[]), str(SOURCE), "exec"), namespace)
check = namespace["startup_endpoint_check"]


class StartupEvidenceContract(unittest.TestCase):
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
