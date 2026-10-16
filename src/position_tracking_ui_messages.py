"""Operator message dialogs, target selection and confirmed remote close requests."""
from __future__ import annotations
from position_tracking_common import _clean
from position_tracking_store import SharedEventStore
from position_tracking_ui_assets import ArrowComboBox
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QFormLayout, QHBoxLayout, QLabel, QMessageBox, QPushButton, QVBoxLayout, QDialog, QListWidget, QListWidgetItem, QPlainTextEdit


class MessageDialogsMixin:
    def _resolve_message_targets(self, selector: str, online: list[dict]) -> list[str]:
        selector = _clean(selector)
        own = self.client_id
        if selector == "ALL":
            return [_clean(x.get("client_id")) for x in online if _clean(x.get("client_id")) != own]
        if selector.startswith("CLIENT:"):
            cid = selector.split(":", 1)[1]
            return [cid] if cid and cid != own else []

        wanted_computers: set[str] = set()
        if self.store:
            for item in self.store.active_all():
                match = False
                if selector.startswith("DIR:"):
                    match = _clean(item.get("direction")).upper() == selector.split(":", 1)[1].upper()
                elif selector.startswith("POS:"):
                    match = _clean(item.get("position")) == selector.split(":", 1)[1]
                if match:
                    wanted_computers.add(_clean(item.get("computer")).upper())
        return [
            _clean(client.get("client_id"))
            for client in online
            if _clean(client.get("client_id")) != own
            and _clean(client.get("computer")).upper() in wanted_computers
        ]


    def _open_messages(self):
        if not self.store:
            QMessageBox.warning(self, "Μηνύματα", "Δεν είναι διαθέσιμος ο κοινός φάκελος δεδομένων.")
            return
        officer = self._officer_selected()
        if not officer:
            QMessageBox.warning(self, "Μηνύματα", "Πληκτρολογήστε πρώτα έγκυρο Α.Γ.Μ.Σ. Αξιωματικού Υπηρεσίας.")
            return

        dlg = QDialog(self)
        dlg.setWindowTitle("ΜΗΝΥΜΑΤΑ / ΟΔΗΓΙΕΣ ΑΞΙΩΜΑΤΙΚΟΥ ΥΠΗΡΕΣΙΑΣ")
        dlg.resize(900, 680)
        lay = QVBoxLayout(dlg)
        lay.setContentsMargins(20, 18, 20, 18)
        lay.setSpacing(10)

        online = self.store.online_clients()
        labels = self._client_worker_labels(online)
        recipient = ArrowComboBox()
        recipient.addItem("ΟΛΟΙ ΟΙ ΕΝΕΡΓΟΙ ΣΤΑΘΜΟΙ", "ALL")
        recipient.addItem("ΟΛΗ Η ΕΙΣΟΔΟΣ", "DIR:ΕΙΣΟΔΟΣ")
        recipient.addItem("ΟΛΗ Η ΕΞΟΔΟΣ", "DIR:ΕΞΟΔΟΣ")
        active_positions = sorted({_clean(x.get("position")) for x in self.store.active_all() if _clean(x.get("position"))})
        for pos in active_positions:
            recipient.addItem(f"ΘΕΣΗ {pos}", f"POS:{pos}")
        for client in online:
            cid = _clean(client.get("client_id"))
            if cid and cid != self.client_id:
                recipient.addItem(labels.get(cid, cid), f"CLIENT:{cid}")

        priority = ArrowComboBox()
        priority.addItems(["ΟΔΗΓΙΑ", "ΕΠΕΙΓΟΝ", "ΕΝΗΜΕΡΩΣΗ"])
        editor = QPlainTextEdit()
        editor.setPlaceholderText("Γράψτε τι πρέπει να γνωρίζουν ή να κάνουν οι παραλήπτες...")
        editor.setMaximumHeight(130)

        form = QFormLayout()
        form.addRow("Παραλήπτες", recipient)
        form.addRow("Τύπος", priority)
        form.addRow("Μήνυμα / οδηγία", editor)
        lay.addLayout(form)

        send_btn = QPushButton("ΑΠΟΣΤΟΛΗ")
        send_btn.setMinimumHeight(44)
        lay.addWidget(send_btn)

        online_label = QLabel(f"Ενεργοί σταθμοί αυτή τη στιγμή: {len(online)}")
        lay.addWidget(online_label)
        sent_list = QListWidget()
        lay.addWidget(sent_list, 1)

        def refresh_sent():
            sent_list.clear()
            for msg in self.store.recent_sent_messages(20):
                targets = [_clean(x) for x in msg.get("targets", []) if _clean(x)]
                acks = msg.get("acknowledgements", [])
                created = _clean(msg.get("created_at")).replace("T", " ")
                target_label = _clean(msg.get("target_label")) or "—"
                body = _clean(msg.get("text"))
                if len(body) > 90:
                    body = body[:87] + "..."
                sent_list.addItem(
                    f"{created} | {msg.get('priority','')} | {target_label} | "
                    f"ΕΛΑΒΑΝ {len(acks)}/{len(targets)} | {body}"
                )

        def do_send():
            target_ids = self._resolve_message_targets(_clean(recipient.currentData()), online)
            try:
                self.store.send_message(
                    SharedEventStore._person_payload(officer),
                    target_ids,
                    editor.toPlainText(),
                    priority.currentText(),
                    recipient.currentText(),
                )
                editor.clear()
                refresh_sent()
            except Exception as exc:
                QMessageBox.warning(dlg, "Αποστολή", str(exc))

        send_btn.clicked.connect(do_send)
        refresh_sent()
        dlg.exec()


    def _close_remaining_clients_dialog(self):
        if not self.store:
            return
        clients = [
            c for c in self.store.online_clients()
            if _clean(c.get("client_id")) and _clean(c.get("client_id")) != self.client_id
        ]
        if not clients:
            QMessageBox.information(self, "Τερματικά", "Δεν υπάρχουν άλλα ενεργά τερματικά.")
            return

        labels = self._client_worker_labels(clients)
        dlg = QDialog(self)
        dlg.setWindowTitle("ΕΝΕΡΓΑ ΤΕΡΜΑΤΙΚΑ ΜΕΤΑ ΤΗ ΛΗΞΗ ΒΑΡΔΙΑΣ")
        dlg.resize(820, 520)
        lay = QVBoxLayout(dlg)
        title = QLabel(
            "Οι παρακάτω εφαρμογές παραμένουν ανοικτές.\n"
            "Επιλέξτε ποιες θέλετε να κλείσετε ή κλείστε τες όλες."
        )
        title.setWordWrap(True)
        lay.addWidget(title)
        listing = QListWidget()
        for client in clients:
            cid = _clean(client.get("client_id"))
            item = QListWidgetItem(labels.get(cid, cid))
            item.setData(Qt.UserRole, cid)
            item.setFlags(item.flags() | Qt.ItemIsUserCheckable)
            item.setCheckState(Qt.Unchecked)
            listing.addItem(item)
        lay.addWidget(listing, 1)

        buttons = QHBoxLayout()
        selected_btn = QPushButton("ΚΛΕΙΣΕ ΕΠΙΛΕΓΜΕΝΟΥΣ")
        all_btn = QPushButton("ΚΛΕΙΣΕ ΟΛΟΥΣ")
        leave_btn = QPushButton("ΑΣΤΑ ΑΝΟΙΧΤΑ")
        buttons.addWidget(selected_btn)
        buttons.addWidget(all_btn)
        buttons.addStretch()
        buttons.addWidget(leave_btn)
        lay.addLayout(buttons)

        def send_to(ids: list[str]):
            ids = [x for x in ids if x]
            if not ids:
                QMessageBox.warning(dlg, "Τερματικά", "Δεν έχει επιλεγεί κανένα τερματικό.")
                return
            sender = self._sender_payload()
            for cid in ids:
                self.store.send_close_command(sender, cid, "Λήξη βάρδιας από Αξιωματικό Υπηρεσίας")
            QMessageBox.information(
                dlg,
                "Τερματικά",
                f"Εστάλη εντολή κλεισίματος σε {len(ids)} τερματικά. "
                "Θα κλείσουν μόλις παραλάβουν την εντολή."
            )
            dlg.accept()

        def close_selected():
            ids = []
            for i in range(listing.count()):
                item = listing.item(i)
                if item.checkState() == Qt.Checked:
                    ids.append(_clean(item.data(Qt.UserRole)))
            send_to(ids)

        selected_btn.clicked.connect(close_selected)
        all_btn.clicked.connect(lambda: send_to([_clean(x.get("client_id")) for x in clients]))
        leave_btn.clicked.connect(dlg.reject)
        dlg.exec()

