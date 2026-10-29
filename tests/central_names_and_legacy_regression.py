"""v1.2.7 field findings: find people by name, open a folder whose old history has a
second END for one START, and keep the v1.2.6 look on both central windows."""
import os
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
import json
from pathlib import Path
import sys
import tempfile
import time
from types import SimpleNamespace
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))
from PySide6.QtWidgets import QApplication
from central_operator_regression import write_personnel
from position_tracking_central import CentralOperator, PositionRequest
from position_tracking_officer import CentralOfficer
from position_tracking_personnel import PersonnelRecord, PersonnelRepository
from position_tracking_ui_central import CentralOperatorWindow
from position_tracking_ui_officer import CentralOfficerWindow

PEOPLE = (PersonnelRecord("999001", "ΑΣΤ", "ΠΑΠΑΔΟΠΟΥΛΟΣ", "ΓΕΩΡΓΙΟΣ"),
          PersonnelRecord("999002", "ΑΣΤ", "ΠΑΠΑΔΟΠΟΥΛΟΣ", "ΝΙΚΟΛΑΟΣ"),
          PersonnelRecord("999003", "ΑΞΙ", "ΙΩΑΝΝΟΥ", "ΜΑΡΙΑ"))


class FindByName(unittest.TestCase):
    def test_agms_surname_full_name_in_any_order_accents_and_case(self):
        find = PersonnelRepository.find
        self.assertEqual([p.agms for p in find(PEOPLE, "999003")], ["999003"])
        self.assertEqual([p.agms for p in find(PEOPLE, "ιωαννου")], ["999003"])
        self.assertEqual([p.agms for p in find(PEOPLE, "Ιωάννου Μαρία")], ["999003"])
        self.assertEqual([p.agms for p in find(PEOPLE, "μαρια ιωαννου")], ["999003"])
        self.assertEqual([p.agms for p in find(PEOPLE, "Παπαδοπουλος γεωργιος")], ["999001"])
        self.assertEqual(len(find(PEOPLE, "Παπαδοπουλος")), 2)
        self.assertEqual([p.agms for p in find(PEOPLE, "ιωα")], ["999003"])
        self.assertEqual(find(PEOPLE, "ζ"), [])
        self.assertEqual(find(PEOPLE, "123456"), [])
        self.assertEqual(find(PEOPLE, ""), [])


class Folder(unittest.TestCase):
    def make(self, duplicate_end):
        temp = tempfile.TemporaryDirectory(prefix="tde-names-legacy-")
        self.addCleanup(temp.cleanup)
        directory = Path(temp.name)
        root = directory / ".tde_runtime"
        root.mkdir()
        write_personnel(root / "personnel.xlsx")
        day = root / "events" / "2026" / "10" / "2026-10-01"
        day.mkdir(parents=True)
        base = {"agms": "999001", "position": "1", "direction": "ΕΙΣΟΔΟΣ"}
        events = [("20261001_080000_000000_s1", dict(base, event_id="s1", kind="START", timestamp="2026-10-01T08:00:00")),
                  ("20261001_090000_000000_e1", dict(base, event_id="e1", kind="END", start_event_id="s1", timestamp="2026-10-01T09:00:00"))]
        if duplicate_end:
            events.append(("20261001_090500_000000_e2", dict(base, event_id="e2", kind="END", start_event_id="s1", timestamp="2026-10-01T09:05:00")))
        for name, event in events:
            (day / (name + ".json")).write_text(json.dumps(event), encoding="utf-8")
        return directory, day

    def test_history_with_a_second_end_opens_and_keeps_the_first(self):
        directory, day = self.make(True)
        before = {f.name: f.read_bytes() for f in day.glob("*.json")}
        operator = CentralOperator.from_shared_directory(directory)
        person, active = operator.lookup("999001")
        self.assertEqual(person.surname, "SYNTHETIC")
        self.assertIsNone(active)
        self.assertEqual({f.name: f.read_bytes() for f in day.glob("*.json")}, before)  # originals untouched
        with operator._store()._shift_db_connect() as db:
            self.assertEqual(db.execute("SELECT kept_event_id FROM legacy_duplicate_review WHERE event_id='e2'").fetchone()[0], "e1")
        start = PositionRequest("START", "999001", "2", "ΕΙΣΟΔΟΣ")
        self.assertEqual(operator.execute(start).status, "CONFIRMED")
        self.assertIsNotNone(operator.lookup("999001")[1])

    def test_officer_snapshot_works_on_the_same_history_and_accepts_a_name(self):
        directory, _ = self.make(True)
        officer = CentralOfficer.from_shared_directory(directory)
        self.assertEqual(officer.snapshot("999001")["officer"].agms, "999001")
        with self.assertRaises(ValueError):  # two people share the surname
            officer.snapshot("SYNTHETIC")
        self.assertEqual(officer.snapshot("SYNTHETIC SECOND")["officer"].agms, "999002")

    def test_operator_lookup_by_name_resolves_and_reports_ambiguity(self):
        directory, _ = self.make(False)
        operator = CentralOperator.from_shared_directory(directory)
        person, _ = operator.lookup("synthetic first")
        self.assertEqual(person.agms, "999001")
        person, _ = operator.lookup("synthetic")
        self.assertIsNone(person)
        self.assertEqual(len(operator.ambiguous), 2)
        self.assertEqual(operator.lookup("SYNTHETIC SECOND")[0].agms, "999002")


class Windows(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.app = QApplication.instance() or QApplication([])
        cls.app.setQuitOnLastWindowClosed(False)

    def wait(self, predicate, timeout=8):
        end = time.monotonic() + timeout
        while not predicate() and time.monotonic() < end:
            self.app.processEvents(); time.sleep(0.005)
        self.assertTrue(predicate())

    def test_operator_window_finds_a_person_typed_by_name_and_has_the_v126_look(self):
        temp = tempfile.TemporaryDirectory(prefix="tde-names-ui-")
        self.addCleanup(temp.cleanup)
        directory = Path(temp.name)
        (directory / ".tde_runtime").mkdir()
        write_personnel(directory / ".tde_runtime" / "personnel.xlsx")
        window = CentralOperatorWindow(SimpleNamespace(app_dir=lambda: directory))
        self.addCleanup(window.shutdown)
        window.show()
        window.agms_input.setText("synthetic second")
        self.wait(lambda: window.start_btn.isEnabled())
        self.assertIn("999002", window.person_name.text())
        window.agms_input.setText("synthetic")
        self.wait(lambda: "πολλοί" in window.active_status.text())
        self.assertFalse(window.start_btn.isEnabled())
        self.assertEqual(window.start_btn.objectName(), "startButton")
        self.assertEqual(window.end_btn.objectName(), "endButton")
        self.assertEqual(window.exit_btn.objectName(), "exitButton")
        self.assertIn("serviceHeader", window.styleSheet())
        self.assertIsNotNone(window.findChild(type(window.centralWidget()), "rootPanel"))

    def test_a_broken_central_folder_shows_the_real_reason(self):
        temp = tempfile.TemporaryDirectory(prefix="tde-names-ui-")
        self.addCleanup(temp.cleanup)
        directory = Path(temp.name)
        (directory / ".tde_runtime").mkdir()  # exists, but there is no personnel list at all
        window = CentralOperatorWindow(SimpleNamespace(app_dir=lambda: directory))
        self.addCleanup(window.shutdown)
        window.show()
        window.agms_input.setText("999001")
        self.wait(lambda: window.info.text().startswith("Αιτία:"))

    def test_officer_window_look_and_name_login(self):
        temp = tempfile.TemporaryDirectory(prefix="tde-names-ui-")
        self.addCleanup(temp.cleanup)
        directory = Path(temp.name)
        (directory / ".tde_runtime").mkdir()
        write_personnel(directory / ".tde_runtime" / "personnel.xlsx")
        window = CentralOfficerWindow(SimpleNamespace(app_dir=lambda: directory, open_path=lambda p: None))
        self.addCleanup(window.close)
        window.show()
        self.assertEqual(window.start_shift.objectName(), "startButton")
        self.assertEqual(window.end_shift.objectName(), "endButton")
        window.officer.setText("synthetic first")
        window.refresh()
        self.wait(lambda: window._state is not None)
        self.assertEqual(window.officer.text(), "999001")  # from now on the AGMS travels


class WorkbookLayouts(unittest.TestCase):
    def load(self, rows, suffix=".xlsm"):
        from openpyxl import Workbook
        temp = tempfile.TemporaryDirectory(prefix="tde-layout-")
        self.addCleanup(temp.cleanup)
        path = Path(temp.name) / ("list" + suffix)
        workbook = Workbook()
        for row in rows:
            workbook.active.append(row)
        workbook.save(path)
        workbook.close()
        return [(p.agms, p.rank, p.surname, p.given_name) for p in PersonnelRepository.load(path)]

    def test_titles_with_dots_numeric_agms(self):
        self.assertEqual(self.load([["Α.Γ.Μ.Σ.", "Βαθμός", "Επώνυμο", "Όνομα"], [254054, "Αστ", "Παπαδόπουλος", "Γιώργος"]]),
                         [("254054", "Αστ", "Παπαδόπουλος", "Γιώργος")])

    def test_full_name_column_and_title_rows_before_the_header(self):
        self.assertEqual(self.load([["ΠΡΟΣΩΠΙΚΟ ΤΜΗΜΑΤΟΣ"], [], ["Αρ. Μητρώου", "Ονοματεπώνυμο"], ["254054", "ΠΑΠΑ ΓΙΩΡΓΟΣ"]]),
                         [("254054", "", "ΠΑΠΑ", "ΓΙΩΡΓΟΣ")])

    def test_no_titles_at_all_still_gets_the_names(self):
        self.assertEqual(self.load([[254054, "Αστ", "Παπαδόπουλος", "Γιώργος"]]), [("254054", "Αστ", "Παπαδόπουλος", "Γιώργος")])
        self.assertEqual(self.load([[254054, "Παπαδόπουλος", "Γιώργος"]]), [("254054", "", "Παπαδόπουλος", "Γιώργος")])
        self.assertEqual(self.load([["254054", "ΠΑΠΑΔΟΠΟΥΛΟΣ ΓΙΩΡΓΟΣ"]]), [("254054", "", "ΠΑΠΑΔΟΠΟΥΛΟΣ", "ΓΙΩΡΓΟΣ")])


if __name__ == "__main__":
    unittest.main()
