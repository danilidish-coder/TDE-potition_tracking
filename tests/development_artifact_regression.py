"""An incomplete or failed validation must never produce an accepted package."""
import hashlib
import json
from pathlib import Path
import sys
import tempfile
import unittest
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT/'tools'))
from package_development_exe import package

class ArtifactGate(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory(); self.addCleanup(self.tmp.cleanup)
        self.base=Path(self.tmp.name);self.exe=self.base/'test.exe';self.exe.write_bytes(b'fixture-exe-not-real')
        self.results=[{'test':p.name,'exit_code':0} for p in (ROOT/'tests').glob('*.py') if p.name!='visual_flicker_windows.py']
        self.functional={'status':'PASS','operations':4,'source_commit':'a'*40,'exe_sha256':hashlib.sha256(self.exe.read_bytes()).hexdigest(),'original_ids_preserved':True,'original_timestamps_preserved':True,'completed_sessions':2,'idle_exit':{'status':'PASS','exit_code':0,'operations':0,'central_created':False,'configured_personnel_missing':True}}
        self.report={'capture_supported':True,'startup_runs':[{'application_frames':20,'endpoint_flicker_detected':False} for _ in range(20)],'theme_toggles':[{'theme_changed':True,'endpoint_flicker_detected':False} for _ in range(30)],'startup_endpoint_flicker_runs':0,'theme_endpoint_flicker_toggles':0,'theme_clicks_confirmed':30}
    def run_package(self):
        regressions=self.base/'results.json';visual=self.base/'visual.json'
        regressions.write_text(json.dumps(self.results));visual.write_text(json.dumps(self.report))
        functional=self.base/'functional.json'
        functional.write_text(json.dumps(self.functional))
        return package(self.exe,regressions,visual,'a'*40,self.base/'package',functional)
    def test_complete_gate_keeps_bytes_hash_and_source_identity(self):
        manifest=self.run_package()
        self.assertEqual(manifest['source_commit'],'a'*40)
        self.assertEqual(manifest['version'], 'v1.2.6')
        self.assertEqual(manifest['sha256'],hashlib.sha256(self.exe.read_bytes()).hexdigest())
        self.assertEqual((self.base/'package'/'test.exe').read_bytes(),self.exe.read_bytes())
    def test_application_manifest_and_windows_resource_versions_agree(self):
        import ast
        sys.path.insert(0, str(ROOT/'src'))
        from position_tracking_constants import APP_VERSION
        self.assertEqual('v'+APP_VERSION, (ROOT/'VERSION.txt').read_text().strip())
        tree=ast.parse((ROOT/'tools/windows_version_info.txt').read_text())
        strings={node.args[0].value:node.args[1].value for node in ast.walk(tree)
                 if isinstance(node,ast.Call) and isinstance(node.func,ast.Name)
                 and node.func.id=='StringStruct'}
        self.assertEqual(strings['ProductVersion'],APP_VERSION)
        self.assertEqual(strings['FileVersion'],APP_VERSION+'.0')
        fixed=next(node for node in ast.walk(tree) if isinstance(node,ast.Call)
                   and isinstance(node.func,ast.Name) and node.func.id=='FixedFileInfo')
        for field in ('filevers','prodvers'):
            value=next(k.value for k in fixed.keywords if k.arg==field)
            self.assertEqual(ast.literal_eval(value), tuple(map(int,APP_VERSION.split('.')))+(0,))

    def test_wrong_exe_or_failed_functional_workflow_cannot_be_packaged(self):
        for key,value in [('status','FAILED'),('exe_sha256','0'*64),('source_commit','b'*40),('operations',3),('original_ids_preserved',False)]:
            old=self.functional[key];self.functional[key]=value
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'functional'):self.run_package()
            self.functional[key]=old
        self.assertFalse((self.base/'package').exists())
    def test_missing_or_failed_idle_exit_cannot_be_packaged(self):
        original=self.functional['idle_exit']
        for value in [None,{},dict(original,status='FAILED'),dict(original,exit_code=1),
                      dict(original,operations=1),dict(original,central_created=True),
                      dict(original,configured_personnel_missing=False)]:
            self.functional['idle_exit']=value
            with self.subTest(value=value),self.assertRaisesRegex(ValueError,'idle exit'):self.run_package()
        self.functional['idle_exit']=original
        self.functional['completed_sessions']=1
        with self.assertRaisesRegex(ValueError,'completed sessions'):self.run_package()
        self.assertFalse((self.base/'package').exists())

    def test_failed_or_missing_regression_cannot_be_packaged(self):
        self.results[0]['exit_code']=1
        with self.assertRaisesRegex(ValueError,'regression'):self.run_package()
        self.results=self.results[1:]
        with self.assertRaisesRegex(ValueError,'regression'):self.run_package()
        self.assertFalse((self.base/'package').exists())
    def test_visual_failure_or_missing_click_or_partial_run_cannot_be_packaged(self):
        for key,value in [('startup_endpoint_flicker_runs',1),('theme_endpoint_flicker_toggles',1),('theme_clicks_confirmed',29),('startup_runs',[])]:
            old=self.report[key];self.report[key]=value
            with self.subTest(key=key),self.assertRaisesRegex(ValueError,'visual'):self.run_package()
            self.report[key]=old
        self.assertFalse((self.base/'package').exists())

if __name__=='__main__':unittest.main()
