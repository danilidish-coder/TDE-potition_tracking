"""Keep the entry small, dependency graph acyclic and backend usable without Qt."""
import ast
import os
from pathlib import Path
import subprocess
import sys
import unittest
ROOT=Path(__file__).resolve().parents[1]
SRC=ROOT/'src'

class ModularArchitecture(unittest.TestCase):
    def test_small_modules_and_no_reverse_entry_import_or_cycles(self):
        sources={p.stem:p for p in SRC.glob('*.py')}
        graph={name:set() for name in sources}
        for name,path in sources.items():
            text=path.read_text(encoding='utf-8')
            self.assertLessEqual(len(text.splitlines()),450,path.name)
            for node in ast.walk(ast.parse(text)):
                imports=([node.module] if isinstance(node,ast.ImportFrom) else
                         [a.name for a in node.names] if isinstance(node,ast.Import) else [])
                for dependency in imports:
                    if dependency in sources:
                        graph[name].add(dependency)
                        if name!='position_tracking':self.assertNotEqual(dependency,'position_tracking',name)
        active=set();visited=set()
        def visit(name):
            self.assertNotIn(name,active,'Dependency cycle at '+name)
            if name in visited:return
            active.add(name)
            for dependency in graph[name]:visit(dependency)
            active.remove(name);visited.add(name)
        for name in graph:visit(name)
        self.assertLess(len(sources['position_tracking'].read_text().splitlines()),200)
    def test_backend_and_report_imports_without_entry_qt_or_optional_document_libraries(self):
        modules=[p.stem for p in SRC.glob('*.py') if p.stem!='position_tracking'
                 and not p.stem.startswith('position_tracking_ui_')
                 and p.stem!='position_tracking_rendering']
        code="import sys,importlib;sys.modules.update({k:None for k in ['position_tracking','PySide6','docx','openpyxl']});[importlib.import_module(m) for m in "+repr(modules)+"]"
        result=subprocess.run([sys.executable,'-c',code],env=dict(os.environ,PYTHONPATH=str(SRC)),capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
    def test_owned_function_and_method_annotations_resolve(self):
        import importlib,inspect,typing
        sys.path.insert(0,str(SRC))
        for path in SRC.glob('*.py'):
            module=importlib.import_module(path.stem)
            for value in vars(module).values():
                if getattr(value,'__module__',None)!=module.__name__:continue
                members=vars(value).values() if inspect.isclass(value) else [value]
                for member in members:
                    if isinstance(member,(classmethod,staticmethod)):member=member.__func__
                    if inspect.isfunction(member):
                        with self.subTest(module=path.stem,function=member.__qualname__):
                            typing.get_type_hints(member)

    def test_legacy_entry_can_be_imported_without_qt(self):
        code="import sys;sys.modules['PySide6']=None;import position_tracking as app;assert app.APP_VERSION=='1.2.5';assert callable(app.run);assert callable(app.SharedEventStore.start)"
        result=subprocess.run([sys.executable,'-c',code],env=dict(os.environ,PYTHONPATH=str(SRC)),capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)

if __name__=='__main__':unittest.main()
