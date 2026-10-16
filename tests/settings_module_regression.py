"""Settings migration/persistence contracts, exclusively in temporary directories."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src'))
import position_tracking as legacy
import position_tracking_settings as settings


class SettingsContract(unittest.TestCase):
    def test_defaults_normalization_and_facade_dataclass_roundtrip(self):
        for cls in (settings.AppConfig, legacy.AppConfig):
            with self.subTest(cls=cls), tempfile.TemporaryDirectory() as directory:
                path = Path(directory) / 'nested' / settings.SETTINGS_NAME
                config = cls(central_root='Ελληνικός φάκελος', positions=[' 99 ', '1', ''])
                self.assertEqual(config.positions, ['99', '1'] + [str(i) for i in range(2, 15)])
                self.assertEqual(config.cutoff, '10:00')
                with patch.object(legacy, '_settings_path', return_value=path):
                    if cls is legacy.AppConfig:
                        self.assertEqual(config.save(), path)
                        loaded = cls.load()
                    else:
                        self.assertEqual(config.save(path=path), path)
                        loaded = cls.load(path=path)
                self.assertIs(type(loaded), cls)
                self.assertEqual(loaded, config)
                self.assertEqual(json.loads(path.read_text(encoding='utf-8'))['central_root'], 'Ελληνικός φάκελος')

    def test_migration_keeps_shared_original_and_existing_local_wins(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory); app = base / 'app'; local = base / 'local' / settings.SETTINGS_NAME
            shared = app / '.tde_runtime' / settings.SETTINGS_NAME
            shared.parent.mkdir(parents=True)
            original = json.dumps({'theme':'dark', 'central_root':'shared'}, ensure_ascii=False).encode()
            shared.write_bytes(original)
            loaded = settings.AppConfig.load(path=local, app_directory=app)
            self.assertEqual(loaded.central_root, 'shared')
            self.assertEqual(local.read_bytes(), original)
            self.assertEqual(shared.read_bytes(), original)
            settings.AppConfig(central_root='local').save(path=local)
            self.assertEqual(settings.AppConfig.load(path=local, app_directory=app).central_root, 'local')
            self.assertEqual(shared.read_bytes(), original)

    def test_failed_replace_preserves_previously_committed_settings(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / settings.SETTINGS_NAME
            settings.AppConfig(theme='dark').save(path=path)
            old = path.read_bytes()
            with patch.object(settings.os, 'replace', side_effect=PermissionError('denied')):
                with self.assertRaises(PermissionError):
                    settings.AppConfig(theme='light').save(path=path)
            self.assertEqual(path.read_bytes(), old)
            self.assertEqual(settings.AppConfig.load(path=path).theme, 'dark')

    def test_corrupt_or_missing_settings_use_defaults_without_rewriting(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / settings.SETTINGS_NAME
            self.assertEqual(settings.AppConfig.load(path=path).positions, [str(i) for i in range(1,15)])
            self.assertFalse(path.exists())
            path.write_bytes(b'{broken')
            self.assertEqual(settings.AppConfig.load(path=path).theme, 'light')
            self.assertEqual(path.read_bytes(), b'{broken')
            path.write_text(json.dumps({'theme':'invalid', 'cutoff':'', 'positions':[' 17 ']}))
            loaded = settings.AppConfig.load(path=path)
            self.assertEqual((loaded.theme, loaded.cutoff), ('light', '10:00'))
            self.assertEqual(loaded.positions[0], '17')

    def test_legacy_injected_paths_and_frozen_app_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            base = Path(directory)
            with patch.object(legacy, '_local_root', return_value=base / 'local'), patch.object(legacy, '_app_dir', return_value=base):
                self.assertEqual(legacy._runtime_root(), base / '.tde_runtime')
                self.assertEqual(legacy._exe_dir(), base)
                self.assertEqual(legacy.AppConfig(theme='dark').save(), base / 'local' / settings.SETTINGS_NAME)
                self.assertEqual(legacy.AppConfig.load().theme, 'dark')
            with patch.object(settings.sys, 'frozen', True, create=True), patch.object(settings.sys, 'executable', str(base / 'client.exe')):
                self.assertEqual(settings._app_dir(), base.resolve())

    def test_import_independent_of_entry_and_qt(self):
        code = "import sys;sys.modules['position_tracking']=None;sys.modules['PySide6']=None;import position_tracking_settings as s;assert s.AppConfig().cutoff=='10:00'"
        env = dict(os.environ, PYTHONPATH=str(ROOT / 'src'))
        result = subprocess.run([sys.executable, '-c', code], env=env, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == '__main__':
    unittest.main()
