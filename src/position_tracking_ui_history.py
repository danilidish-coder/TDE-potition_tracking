"""PIN-guarded personnel history search, statistics and PDF export dialog."""
from __future__ import annotations
import hashlib
from datetime import datetime, time as dtime
from position_tracking_common import _clean, _norm_search
from position_tracking_constants import STATISTICS_PIN_SHA256
from position_tracking_pdf import summarize_personnel_history, create_personnel_history_pdf
from position_tracking_report_text import _format_seconds
from position_tracking_settings import _open_path
from position_tracking_ui_assets import ArrowComboBox
from PySide6.QtCore import QDate, QTime
from PySide6.QtWidgets import QDateEdit, QFormLayout, QHBoxLayout, QLabel, QLineEdit, QMessageBox, QPushButton, QVBoxLayout, QInputDialog, QDialog, QSpinBox, QTableWidget, QTableWidgetItem, QHeaderView, QAbstractItemView, QCheckBox, QTimeEdit
from position_tracking_constants import STATISTICS_PIN_SHA256


class PersonnelHistoryMixin:
    def _personnel_history(self):
        if not self.store:
            QMessageBox.warning(self, "Έλεγχος", "Δεν είναι διαθέσιμο το .tde_runtime.")
            return
        pin, ok = QInputDialog.getText(self, "Ιστορικό προσωπικού", "Κωδικός πρόσβασης", QLineEdit.Password)
        if not ok:
            return
        if hashlib.sha256(_clean(pin).encode("utf-8")).hexdigest() != STATISTICS_PIN_SHA256:
            QMessageBox.warning(self, "Ιστορικό προσωπικού", "Λανθασμένος κωδικός.")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("ΙΣΤΟΡΙΚΟ ΠΡΟΣΩΠΙΚΟΥ")
        dlg.resize(1180, 780)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(9)

        title = QLabel("ΙΣΤΟΡΙΚΟ ΠΡΟΣΩΠΙΚΟΥ")
        title.setStyleSheet("font-size:18px;font-weight:900")
        lay.addWidget(title)
        hint = QLabel(
            "Βασικές αναζητήσεις: «ΠΟΥ/ΠΟΤΕ ΔΟΥΛΕΨΕ Ο ΤΑΔΕ;» ή «ΠΟΙΟΣ ΗΤΑΝ ΕΚΕΙ ΤΟΤΕ;». "
            "Τα υπόλοιπα φίλτρα είναι προαιρετικά και συνδυάζονται μεταξύ τους."
        )
        hint.setWordWrap(True)
        lay.addWidget(hint)

        workers = self.store.list_personnel_workers()
        person_combo = ArrowComboBox()
        person_combo.setEditable(True)
        person_combo.addItem("ΟΛΟΙ ΟΣΟΙ ΕΧΟΥΝ ΔΟΥΛΕΨΕΙ", "")
        for worker in workers:
            label = _clean(
                f"{worker.get('rank','')} {worker.get('surname','')} {worker.get('given_name','')} "
                f"(ΑΓΜΣ {worker.get('agms','')})"
            )
            person_combo.addItem(label, _clean(worker.get("agms")))

        use_dates = QCheckBox("Φίλτρο ημερομηνιών")
        from_date = QDateEdit()
        to_date = QDateEdit()
        from_date.setCalendarPopup(True)
        to_date.setCalendarPopup(True)
        from_date.setDisplayFormat("dd/MM/yyyy")
        to_date.setDisplayFormat("dd/MM/yyyy")
        from_date.setDate(QDate.currentDate().addMonths(-1))
        to_date.setDate(QDate.currentDate())
        from_date.setEnabled(False)
        to_date.setEnabled(False)

        positions = self.store.list_session_positions()
        position_combo = ArrowComboBox()
        position_combo.addItem("ΟΛΕΣ")
        for pos in positions:
            position_combo.addItem(pos)
        direction_combo = ArrowComboBox()
        direction_combo.addItems(["ΟΛΑ", "ΕΙΣΟΔΟΣ", "ΕΞΟΔΟΣ"])

        use_clock = QCheckBox("Φίλτρο ώρας μέσα στην ημέρα")
        time_from = QTimeEdit()
        time_to = QTimeEdit()
        time_from.setDisplayFormat("HH:mm")
        time_to.setDisplayFormat("HH:mm")
        time_from.setTime(QTime(0, 0))
        time_to.setTime(QTime(23, 59))
        time_from.setEnabled(False)
        time_to.setEnabled(False)

        exact_moment = QCheckBox("Στιγμιαία αναζήτηση — ποιος ήταν εκεί τότε")
        moment_date = QDateEdit()
        moment_time = QTimeEdit()
        moment_date.setCalendarPopup(True)
        moment_date.setDisplayFormat("dd/MM/yyyy")
        moment_date.setDate(QDate.currentDate())
        moment_time.setDisplayFormat("HH:mm")
        moment_time.setTime(QTime.currentTime())
        moment_date.setEnabled(False)
        moment_time.setEnabled(False)

        min_duration = QSpinBox()
        max_duration = QSpinBox()
        for box in (min_duration, max_duration):
            box.setRange(0, 24 * 60)
            box.setSuffix(" λεπτά")
            box.setSpecialValueText("Χωρίς όριο")
        min_duration.setToolTip("Ελάχιστη διάρκεια μίας συνεχόμενης παραμονής στη θέση")
        max_duration.setToolTip("Μέγιστη διάρκεια μίας συνεχόμενης παραμονής στη θέση")

        form = QFormLayout()
        form.addRow("Άτομο", person_combo)
        form.addRow("", use_dates)
        form.addRow("Από ημερομηνία", from_date)
        form.addRow("Έως ημερομηνία", to_date)
        form.addRow("Θέση", position_combo)
        form.addRow("Κατεύθυνση", direction_combo)
        form.addRow("", use_clock)
        form.addRow("Ώρα από", time_from)
        form.addRow("Ώρα έως", time_to)
        form.addRow("", exact_moment)
        form.addRow("Ημερομηνία στιγμής", moment_date)
        form.addRow("Ώρα στιγμής", moment_time)
        form.addRow("Διάρκεια από", min_duration)
        form.addRow("Διάρκεια έως", max_duration)
        lay.addLayout(form)

        quick = QHBoxLayout()
        person_mode_btn = QPushButton("ΠΟΥ / ΠΟΤΕ ΔΟΥΛΕΨΕ Ο ΤΑΔΕ;")
        moment_mode_btn = QPushButton("ΠΟΙΟΣ ΗΤΑΝ ΕΚΕΙ ΤΟΤΕ;")
        quick.addWidget(person_mode_btn)
        quick.addWidget(moment_mode_btn)
        quick.addStretch()
        lay.addLayout(quick)

        actions = QHBoxLayout()
        search_btn = QPushButton("ΑΝΑΖΗΤΗΣΗ")
        clear_btn = QPushButton("ΚΑΘΑΡΙΣΜΟΣ")
        pdf_btn = QPushButton("PDF ΑΠΟΤΕΛΕΣΜΑΤΩΝ")
        actions.addWidget(search_btn)
        actions.addWidget(clear_btn)
        actions.addWidget(pdf_btn)
        actions.addStretch()
        lay.addLayout(actions)

        summary_box = QLabel("")
        summary_box.setWordWrap(True)
        summary_box.setObjectName("infoBox")
        lay.addWidget(summary_box)

        result_label = QLabel("")
        lay.addWidget(result_label)

        table = QTableWidget(0, 8)
        table.setHorizontalHeaderLabels(
            ["ΗΜΕΡΟΜΗΝΙΑ", "ΑΓΜΣ", "ΟΝΟΜΑ", "ΘΕΣΗ", "ΚΑΤΕΥΘΥΝΣΗ", "ΕΝΑΡΞΗ", "ΛΗΞΗ", "ΔΙΑΡΚΕΙΑ"]
        )
        table.setAlternatingRowColors(True)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeToContents)
        table.horizontalHeader().setStretchLastSection(True)
        lay.addWidget(table, 1)

        current_rows: list[dict] = []
        current_criteria = ""

        def qtime_to_time(value: QTime) -> dtime:
            return dtime(value.hour(), value.minute())

        def selected_person_query() -> str:
            text_value = _clean(person_combo.currentText())
            if _norm_search(text_value) == _norm_search("ΟΛΟΙ ΟΣΟΙ ΕΧΟΥΝ ΔΟΥΛΕΨΕΙ"):
                return ""
            idx = person_combo.currentIndex()
            if idx >= 0 and text_value == _clean(person_combo.itemText(idx)):
                data = person_combo.itemData(idx)
                if _clean(data):
                    return _clean(data)
            return text_value

        def summary_text(rows: list[dict]) -> str:
            summary = summarize_personnel_history(rows)
            line1 = (
                f"Καταχωρίσεις: {len(rows)}   |   Άτομα: {summary['people']}   |   "
                f"Συνολικός χρόνος: {_format_seconds(summary['total_seconds'])}"
            )
            parts = [line1]
            for direction in ("ΕΙΣΟΔΟΣ", "ΕΞΟΔΟΣ"):
                sec = int(summary["by_direction"].get(direction, 0))
                if not sec:
                    continue
                pos_parts = []
                for (d, pos), psec in sorted(summary["by_direction_position"].items(), key=lambda x: (x[0][0], x[0][1])):
                    if d == direction and psec:
                        pos_parts.append(f"Θέση {pos}: {_format_seconds(psec)}")
                detail = " · ".join(pos_parts)
                parts.append(f"{direction}: {_format_seconds(sec)}" + (f"   |   {detail}" if detail else ""))
            return "\n".join(parts)

        def criteria_text() -> str:
            bits = []
            pq = selected_person_query()
            if pq:
                bits.append(f"Άτομο: {person_combo.currentText()}")
            else:
                bits.append("Άτομο: ΟΛΟΙ")
            if exact_moment.isChecked():
                bits.append(
                    f"Στιγμή: {moment_date.date().toString('dd/MM/yyyy')} {moment_time.time().toString('HH:mm')}"
                )
            elif use_dates.isChecked():
                bits.append(
                    f"Ημερομηνίες: {from_date.date().toString('dd/MM/yyyy')}–{to_date.date().toString('dd/MM/yyyy')}"
                )
            pos = _clean(position_combo.currentText())
            direction = _clean(direction_combo.currentText())
            if pos != "ΟΛΕΣ":
                bits.append(f"Θέση: {pos}")
            if direction != "ΟΛΑ":
                bits.append(f"Κατεύθυνση: {direction}")
            if use_clock.isChecked() and not exact_moment.isChecked():
                bits.append(f"Ώρες: {time_from.time().toString('HH:mm')}–{time_to.time().toString('HH:mm')}")
            if min_duration.value():
                bits.append(f"Διάρκεια ≥ {min_duration.value()} λεπτά")
            if max_duration.value():
                bits.append(f"Διάρκεια ≤ {max_duration.value()} λεπτά")
            return " | ".join(bits)

        def render_rows(rows: list[dict], label_prefix: str = "Βρέθηκαν"):
            nonlocal current_rows, current_criteria
            current_rows = rows
            current_criteria = criteria_text()
            table.setRowCount(len(rows))
            for r, row in enumerate(rows):
                try:
                    sdt = datetime.fromisoformat(row["start_at"])
                    edt = datetime.fromisoformat(row["end_at"])
                    date_text = sdt.strftime("%d/%m/%Y")
                    start_text = sdt.strftime("%H:%M:%S")
                    end_text = edt.strftime("%H:%M:%S")
                except Exception:
                    date_text = _clean(row.get("start_at"))[:10]
                    start_text = _clean(row.get("start_at"))[11:19]
                    end_text = _clean(row.get("end_at"))[11:19]
                name = _clean(f"{row.get('rank','')} {row.get('surname','')} {row.get('given_name','')}") or _clean(row.get("full_name"))
                values = [
                    date_text,
                    _clean(row.get("agms")),
                    name,
                    _clean(row.get("position")),
                    _clean(row.get("direction")),
                    start_text,
                    end_text,
                    _format_seconds(int(row.get("duration_seconds") or 0)),
                ]
                for col, value in enumerate(values):
                    table.setItem(r, col, QTableWidgetItem(str(value)))
            result_label.setText(f"{label_prefix} {len(rows)} καταχωρίσεις.")
            summary_box.setText(summary_text(rows) if rows else "Δεν βρέθηκαν καταχωρίσεις με αυτά τα κριτήρια.")

        def do_search():
            d_from = from_date.date().toPython() if use_dates.isChecked() and not exact_moment.isChecked() else None
            d_to = to_date.date().toPython() if use_dates.isChecked() and not exact_moment.isChecked() else None
            if d_from and d_to and d_from > d_to:
                QMessageBox.warning(dlg, "Ιστορικό", "Η ημερομηνία «Από» είναι μετά την ημερομηνία «Έως».")
                return
            moment = None
            if exact_moment.isChecked():
                qd = moment_date.date()
                qt = moment_time.time()
                moment = datetime(qd.year(), qd.month(), qd.day(), qt.hour(), qt.minute())
            tf = qtime_to_time(time_from.time()) if use_clock.isChecked() and not exact_moment.isChecked() else None
            tt = qtime_to_time(time_to.time()) if use_clock.isChecked() and not exact_moment.isChecked() else None
            if max_duration.value() and min_duration.value() and max_duration.value() < min_duration.value():
                QMessageBox.warning(dlg, "Ιστορικό", "Η μέγιστη διάρκεια είναι μικρότερη από την ελάχιστη.")
                return

            rows = self.store.search_personnel_sessions(
                person_query=selected_person_query(),
                date_from=d_from,
                date_to=d_to,
                position=_clean(position_combo.currentText()),
                direction=_clean(direction_combo.currentText()),
                time_from=tf,
                time_to=tt,
                moment=moment,
                min_duration_minutes=min_duration.value(),
                max_duration_minutes=max_duration.value(),
            )
            render_rows(rows)
            try:
                self.store.log_admin_action("PERSONNEL_HISTORY_SEARCH", {
                    "criteria": criteria_text(), "results": len(rows)
                })
            except Exception:
                pass

        def clear_search():
            person_combo.setCurrentIndex(0)
            use_dates.setChecked(False)
            from_date.setDate(QDate.currentDate().addMonths(-1))
            to_date.setDate(QDate.currentDate())
            position_combo.setCurrentIndex(0)
            direction_combo.setCurrentIndex(0)
            use_clock.setChecked(False)
            time_from.setTime(QTime(0, 0))
            time_to.setTime(QTime(23, 59))
            exact_moment.setChecked(False)
            moment_date.setDate(QDate.currentDate())
            moment_time.setTime(QTime.currentTime())
            min_duration.setValue(0)
            max_duration.setValue(0)
            rows = self.store.search_personnel_sessions(limit=100)
            render_rows(rows, "Τελευταίες")

        def export_pdf():
            if not current_rows:
                QMessageBox.warning(dlg, "PDF", "Δεν υπάρχουν αποτελέσματα για εξαγωγή.")
                return
            try:
                path = create_personnel_history_pdf(
                    current_rows,
                    current_criteria,
                    summarize_personnel_history(current_rows),
                )
                self._services.open_path(path)
            except Exception as exc:
                QMessageBox.critical(dlg, "PDF", str(exc))

        def update_filter_states():
            moment_on = exact_moment.isChecked()
            date_on = use_dates.isChecked() and not moment_on
            clock_on = use_clock.isChecked() and not moment_on
            from_date.setEnabled(date_on)
            to_date.setEnabled(date_on)
            time_from.setEnabled(clock_on)
            time_to.setEnabled(clock_on)
            moment_date.setEnabled(moment_on)
            moment_time.setEnabled(moment_on)
            use_dates.setEnabled(not moment_on)
            use_clock.setEnabled(not moment_on)

        def choose_person_mode():
            exact_moment.setChecked(False)
            person_combo.setFocus()
            if person_combo.lineEdit():
                person_combo.lineEdit().selectAll()

        def choose_moment_mode():
            person_combo.setCurrentIndex(0)
            exact_moment.setChecked(True)
            position_combo.setCurrentIndex(0)
            direction_combo.setCurrentIndex(0)
            moment_date.setFocus()

        use_dates.toggled.connect(update_filter_states)
        use_clock.toggled.connect(update_filter_states)
        exact_moment.toggled.connect(update_filter_states)
        search_btn.clicked.connect(do_search)
        clear_btn.clicked.connect(clear_search)
        pdf_btn.clicked.connect(export_pdf)
        person_mode_btn.clicked.connect(choose_person_mode)
        moment_mode_btn.clicked.connect(choose_moment_mode)
        person_combo.lineEdit().returnPressed.connect(do_search)

        update_filter_states()
        rows = self.store.search_personnel_sessions(limit=100)
        render_rows(rows, "Τελευταίες")
        dlg.exec()

