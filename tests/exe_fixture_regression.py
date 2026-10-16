"""The external EXE driver must close its own SQLite readers before cleanup."""
import ast
from contextlib import closing
from pathlib import Path
import sqlite3
import tempfile
import types
import unittest

SOURCE=Path(__file__).resolve().parents[1]/'tools'/'exercise_windows_exe.py'

class ExeFixtureContract(unittest.TestCase):
    def test_readonly_reader_explicitly_closes_and_keeps_operation_identity(self):
        calls=[]
        class Connection(sqlite3.Connection):
            def close(self):calls.append(True);super().close()
        proxy=types.SimpleNamespace(Row=sqlite3.Row,connect=lambda *a,**k:sqlite3.connect(*a,factory=Connection,**k))
        tree=ast.parse(SOURCE.read_text(encoding='utf-8'))
        function=next(n for n in tree.body if isinstance(n,ast.FunctionDef) and n.name=='operations')
        namespace={'sqlite3':proxy,'closing':closing}
        exec(compile(ast.Module(body=[function],type_ignores=[]),str(SOURCE),'exec'),namespace)
        with tempfile.TemporaryDirectory() as directory:
            path=Path(directory)/'queue.sqlite3'
            with closing(sqlite3.connect(path)) as db:
                db.execute('CREATE TABLE operations(id,kind,position,direction,created_at,start_id,status)')
                db.execute("INSERT INTO operations VALUES('original-id','START','14','EXIT','original-time','','PENDING')");db.commit()
            rows=namespace['operations'](path)
            self.assertEqual((rows[0]['id'],rows[0]['created_at']),('original-id','original-time'))
            self.assertEqual(calls,[True])
            path.unlink()
            self.assertEqual(namespace['operations'](path),[])
    def test_both_driver_sqlite_connections_have_explicit_closing(self):
        tree=ast.parse(SOURCE.read_text(encoding='utf-8'))
        connections=[n for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Attribute) and isinstance(n.func.value,ast.Name) and n.func.value.id=='sqlite3' and n.func.attr=='connect']
        wrapped=[n.args[0] for n in ast.walk(tree) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='closing' and n.args]
        self.assertEqual(len(connections),2)
        self.assertTrue(all(n in wrapped for n in connections))

if __name__=='__main__':unittest.main()
