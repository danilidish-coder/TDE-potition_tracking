# Τεχνική αναφορά modular development — 16/10/2026

## Κατάσταση πιστοποίησης

Η δομική διάσπαση ολοκληρώθηκε: **43 αρχεία Python συνολικά**, κύριο αρχείο
**88 γραμμών**, σύνθεση MainWindow **77 γραμμών**, μεγαλύτερο module **366 γραμμών**.
Ο κώδικας βρίσκεται αποκλειστικά στο `feature/v125-modularization-20261013`.
Η τελική δομική έκδοση `762c3a369a199766ab629007b6b2a3c27885d5e1` έχει πλήρη αυτοματοποιημένη πιστοποίηση:
Windows **38874685744 SUCCESS**, Linux **38874685771 SUCCESS**, modular gate
**38874685792 SUCCESS**, Windows Qt recovery **38874685760 SUCCESS (8/8)**.
Το GitHub ελέγχθηκε ξανά κατά την επανέναρξη στις 16/10/2026, χωρίς νέα εκτέλεση.
45 regression scripts, build/smoke, πραγματικό frozen EXE data workflow PASS:
4 πράξεις, 2 συνεδρίες, ίδια IDs/timestamps. Αυστηρά visual: startup **0/20**,
theme **0/30**, επιβεβαιωμένα clicks **30/30**.
Η νέα επαγγελματική θωράκιση είναι χωριστό στάδιο· δεν απαιτεί νέα modularization.

## Αρχιτεκτονική και συμβατότητα

Η κατεύθυνση εξαρτήσεων είναι entry/composition → GUI controllers → storage,
reporting και μοντέλα → κοινά helpers. Οι συνεργαζόμενες storage capabilities και
GUI controllers συντίθενται με mixins στη μικρή facade τους. Τα runtime paths,
config type και file-opening callback παρέχονται με `WindowServices`.
Δεν υπάρχει κυκλική εξάρτηση ή εισαγωγή του entry από άλλο module.

Τα παλιά ονόματα παραμένουν διαθέσιμα από `position_tracking.py`. Η AppConfig
facade διατηρεί τα overridable path providers και τη dataclass συμπεριφορά.
JSON/SQLite schemas, IDs, timestamps, κατάλογοι, ονόματα αναφορών και τιμές
έκδοσης/PIN δεν άλλαξαν λόγω εξαγωγής. Διατηρήθηκαν τα αρχικά εικαστικά και CSS.
Τα backend/report modules φορτώνουν χωρίς Qt ή το entry, με προαιρετικές
βιβλιοθήκες εγγράφων να φορτώνονται μόνο όταν χρειάζονται.

Το whole-module AST audit έναντι του `0f6fee53ed5194d98318fd9f1037052012056184`
επιβεβαίωσε **66/66 μεθόδους store αμετάβλητες** και **50/50 ενεργές μεθόδους UI**
αμετάβλητες μετά την κανονικοποίηση των ρητών callbacks διαδρομών. Ο constructor
σύνθεσης ελέγχθηκε ξεχωριστά μέσα από πραγματικές Qt ενέργειες. Δύο παλιοί διπλοί
ορισμοί που σκιάζονταν από μεταγενέστερους αφαιρέθηκαν, διατηρώντας την πραγματική
τελευταία υλοποίηση. Η σύγκριση διαβάζει ολόκληρα AST ώστε να διατηρεί και τα
ακριβή multiline SQL/HTML literals.

## Πλήρης κατάλογος modules

Ο κατάλογος/γραμμές παρακάτω αποτυπώνουν το ολοκληρωμένο modularization source
762c3a36. Η μεταγενέστερη θωράκιση 5231b30 προσθέτει το ανεξάρτητο
`position_tracking_diagnostics.py` (150 γραμμές, bounded local watchdog/metrics)
και μικρές τεκμηριωμένες διορθώσεις στους υπάρχοντες controllers/offline journal.
Η αρχιτεκτονική παραμένει ίδια· συνολικά πλέον 44 source files.
Για την τρέχουσα αξιοπιστία/πιστοποίηση δείτε RELIABILITY_REPORT_EL.md.

| Αρχείο | Γραμμές | Ευθύνη |
|---|---:|---|
| [position_tracking.py](../src/position_tracking.py) | 88 | Συμβατό σημείο εισόδου, παλιά exports και σύνθεση runtime providers |
| [position_tracking_artwork.py](../src/position_tracking_artwork.py) | 4 | Αρχικά ενσωματωμένα εικαστικά υπηρεσίας και χάρτη |
| [position_tracking_bootstrap.py](../src/position_tracking_bootstrap.py) | 68 | Τοπικό αντίγραφο EXE, checksum, launcher και συντόμευση |
| [position_tracking_common.py](../src/position_tracking_common.py) | 25 | Κανονικοποίηση και ασφαλή ονόματα |
| [position_tracking_communication.py](../src/position_tracking_communication.py) | 187 | Heartbeats, μηνύματα, εντολές και acknowledgements |
| [position_tracking_constants.py](../src/position_tracking_constants.py) | 6 | Αμετάβλητη ταυτότητα εφαρμογής, έκδοση και hash εξουσιοδότησης ιστορικού |
| [position_tracking_documents.py](../src/position_tracking_documents.py) | 78 | Αναφορές Word και ονομασία αρχείου αρχειοθέτησης |
| [position_tracking_event_queries.py](../src/position_tracking_event_queries.py) | 252 | Προβολές συμβάντων, χρονικά παράθυρα και αναζητήσεις βαρδιών |
| [position_tracking_handoff.py](../src/position_tracking_handoff.py) | 134 | Συντονισμός αλλαγής Windows χρήστη πριν από replay |
| [position_tracking_machine_queue.py](../src/position_tracking_machine_queue.py) | 83 | Κοινή ουρά ανά μηχάνημα και προστασία παλιών προσωπικών εκκρεμοτήτων |
| [position_tracking_offline.py](../src/position_tracking_offline.py) | 258 | Durable SQLite outbox, αρχικά IDs/timestamps και ατομική ενημέρωση cache |
| [position_tracking_pdf.py](../src/position_tracking_pdf.py) | 256 | Αναφορές PDF, σύνοψη ιστορικού και προσωρινά αρχεία |
| [position_tracking_personnel.py](../src/position_tracking_personnel.py) | 299 | Αμετάβλητα records και read-only OOXML προσωπικού/roster |
| [position_tracking_positions.py](../src/position_tracking_positions.py) | 305 | START/END, idempotent receipts, διορθώσεις ώρας και handoff adapter |
| [position_tracking_rendering.py](../src/position_tracking_rendering.py) | 33 | Συνεκτική ζωγραφική ολόκληρου widget tree κατά την αλλαγή θέματος |
| [position_tracking_report_text.py](../src/position_tracking_report_text.py) | 159 | Καθαρή μορφοποίηση αναφορών text/HTML |
| [position_tracking_session_index.py](../src/position_tracking_session_index.py) | 250 | Ευρετήριο προσωπικών συνεδριών και reconciliation |
| [position_tracking_settings.py](../src/position_tracking_settings.py) | 132 | Ρυθμίσεις, migration, ατομική αποθήκευση και διαδρομές |
| [position_tracking_shift_index.py](../src/position_tracking_shift_index.py) | 166 | Σχήμα SQLite, snapshots και ευρετήριο αναφορών βάρδιας |
| [position_tracking_shifts.py](../src/position_tracking_shifts.py) | 323 | Κύκλος βάρδιας, pending/approved/excluded και ασφαλής λήξη |
| [position_tracking_statistics.py](../src/position_tracking_statistics.py) | 127 | Στατιστικά Excel και γραφήματα |
| [position_tracking_store.py](../src/position_tracking_store.py) | 116 | Μικρή σύνθεση storage capabilities, audit και backups |
| [position_tracking_store_io.py](../src/position_tracking_store_io.py) | 124 | Κλειδώματα αρχείων, ατομικά JSON και συνδέσεις SQLite |
| [position_tracking_theme.py](../src/position_tracking_theme.py) | 152 | Παλέτες και καθαρή παραγωγή stylesheet |
| [position_tracking_ui_admin.py](../src/position_tracking_ui_admin.py) | 172 | Διοικητικές ενέργειες, audit, backups και πλοήγηση |
| [position_tracking_ui_application.py](../src/position_tracking_ui_application.py) | 18 | Διάρκεια ζωής QApplication και εκκίνηση παραθύρου |
| [position_tracking_ui_assets.py](../src/position_tracking_ui_assets.py) | 89 | Qt renderers εμβλήματος, watermark, βελών και network icon |
| [position_tracking_ui_communication.py](../src/position_tracking_ui_communication.py) | 151 | Ασύγχρονο heartbeat, WTS polling και ειδοποιήσεις μηνυμάτων |
| [position_tracking_ui_configuration.py](../src/position_tracking_ui_configuration.py) | 112 | Ρυθμίσεις GUI και τοπική cache προσωπικού |
| [position_tracking_ui_context.py](../src/position_tracking_ui_context.py) | 13 | Ρητά runtime callbacks διαδρομών, config και ανοίγματος αρχείων |
| [position_tracking_ui_history.py](../src/position_tracking_ui_history.py) | 366 | Εξουσιοδοτημένο ιστορικό προσωπικού, αναζήτηση και PDF |
| [position_tracking_ui_lifecycle.py](../src/position_tracking_ui_lifecycle.py) | 77 | Ασφαλής έξοδος χειριστή και καθαρισμός clients/executors |
| [position_tracking_ui_main.py](../src/position_tracking_ui_main.py) | 77 | Αρχικοποίηση παραθύρου και σύνθεση controllers |
| [position_tracking_ui_map.py](../src/position_tracking_ui_map.py) | 288 | Ζωντανός χάρτης θέσεων και ασύγχρονη ανανέωση |
| [position_tracking_ui_messages.py](../src/position_tracking_ui_messages.py) | 194 | Διάλογοι μηνυμάτων, παραληπτών και επιβεβαιωμένων close requests |
| [position_tracking_ui_positions.py](../src/position_tracking_ui_positions.py) | 179 | GUI καταχώριση START/END, offline worker και εμφάνιση conflicts |
| [position_tracking_ui_presentation.py](../src/position_tracking_ui_presentation.py) | 58 | Πρώτη native παρουσίαση μετά την ολοκληρωμένη ζωγραφική Qt |
| [position_tracking_ui_reports.py](../src/position_tracking_ui_reports.py) | 187 | Τρέχουσα αναφορά και αναζήτηση αρχείου βαρδιών |
| [position_tracking_ui_selection.py](../src/position_tracking_ui_selection.py) | 111 | Επιλογή προσωπικού και ασύγχρονη κατάσταση κουμπιών |
| [position_tracking_ui_shift_end.py](../src/position_tracking_ui_shift_end.py) | 284 | Διάλογος λήξης, ατομικά/ομαδικά END και guards |
| [position_tracking_ui_shifts.py](../src/position_tracking_ui_shifts.py) | 227 | Προεπισκόπηση, αποδοχή μελών και κατάσταση βάρδιας |
| [position_tracking_ui_view.py](../src/position_tracking_ui_view.py) | 193 | Κεντρική διάταξη widgets και εφαρμογή θέματος |
| [position_tracking_windows_session.py](../src/position_tracking_windows_session.py) | 46 | Έλεγχος ενεργής συνεδρίας Windows/WTS |

Τα ακριβή commits ανά αρχείο και τα commits της ημέρας διατηρούνται στα
`validation/structure-20261016/modules.json` και `commits.json`. Το audit βρίσκεται
στο `validation/structure-20261016/ast-audit.json`.

## Πραγματική διάγνωση και διορθώσεις

1. Τα πρωτότυπα startup PNGs αποκάλυψαν δύο διαφορετικές καταστάσεις: αλλαγή
   1.043 από 835.200 pixels μόνο στο περίγραμμα της runner κονσόλας όταν χάνει
   focus, και πραγματική ολόλευκη native επιφάνεια πριν από την πρώτη Qt ζωγραφική.
   Δεν χαρακτηρίστηκαν όλα αυθαίρετα ως φυσιολογική φόρτωση.
2. Το visual fixture απέκτησε δικό του responsive Win32 message loop και
   ελεγχόμενη ενεργοποίηση πριν από κάθε reference. Το όριο 0.08 παρέμεινε ίδιο.
3. Η αρχική native επιφάνεια παραμένει DWM-cloaked ενώ ζωγραφίζεται πραγματικά το
   Qt backing store και παρουσιάζεται μία φορά μετά το πλήρες πρώτο paint.
   Ο μηχανισμός δεν εφαρμόζεται σε μετέπειτα αλλαγές θέματος. Δεν χρησιμοποιεί
   screenshots/overlays, timed delay ή nested processEvents.
4. Το `WA_NoSystemBackground` δοκιμάστηκε, αποδείχθηκε αναποτελεσματικό και
   αφαιρέθηκε. Δεν παρουσιάζεται ως επιτυχής διόρθωση.
5. Το rendering integration test ξεκινούσε από timer 100 ms πριν το παράθυρο
   γίνει exposed. Αναπαραγωγή: iteration=0, exposed=False, όλα τα widgets χωρίς
   Paint. Πλέον περιμένει το πραγματικό αρχικό Paint με hard timeout, διατηρώντας
   και τις 60 αυστηρές synchronous paint/persistence επαληθεύσεις.
6. Διορθώθηκαν πραγματικά ελαττώματα των νέων tests: Windows 8.3 έναντι canonical
   temp path, assertions ακριβούς whitespace/quotes αντί Qt constructors, και
   ακούσια εξάρτηση του stdlib-only backend gate από Qt. Δεν αφαιρέθηκαν σενάρια.

Οι προηγούμενες διορθώσεις durable START μετά από χαμένη SMB acknowledgement και
ατομικού APPLIED/cache transaction με προστασία delayed replay διατηρήθηκαν και
επανελέγχθηκαν. Δεν έγιναν νέες αλλαγές σε business logic START/END κατά την
εξαγωγή των storage modules.

## Έλεγχοι και διατηρημένες αποτυχίες

| Έκδοση / run | Πραγματικό αποτέλεσμα |
|---|---|
| Checkpoint 22bc3bd / Windows 38806871707 | FAIL: 12/20 startup, 0/30 theme, 30 clicks |
| 0f6fee5 / Windows 38861912057 | 36 regressions/build/smoke PASS, visual FAIL: 14 startup, 1 theme· src tree ίδιο με ec80b132 |
| f31fe5c / Windows 38862995734 | FAIL στο νέο test canonical temp path· build/visual δεν εκτελέστηκαν |
| da9b4d1 / Windows 38863724150 | 40 regressions/build/smoke PASS, visual FAIL: 17 startup, 0 theme |
| 7444dc9 / Windows 38865045894, Linux 38865045885 | FAIL στο pre-exposure rendering timer test· native visual δεν εκτελέστηκε |
| 7444dc9 / module gate 38865045892 | FAIL λόγω Qt import στο stdlib-only backend contract |
| b943a869 / Windows 38865827943 | Full SUCCESS: 41 scripts, EXE build/smoke, 0/20 startup, 0/30 theme, 30/30 clicks, upload artifacts |
| b943a869 / Linux 38865827783, gate 38865827824 | PASS |
| d128e6db / Linux 38868080997, gate 38868081064 | PASS |
| d128e6db / Windows 38868081099 | FAIL στον εξωτερικό driver: SQLite reader cleanup έκρυψε αρχικό error, όχι visual PASS |
| f44331e / Windows 38869909515 | 44 regressions/build/smoke PASS· FAIL επανενεργοποίησης test background μετά πληκτρολόγηση, pending δεδομένα άθικτα |
| e243e53 / Linux 38870905814, gate 38870905823 | PASS |
| e243e53 / Windows 38870905825 | FAIL: timeout στο Qt recovery· ιστορικό, όχι σημερινή εκκρεμότητα |
| f4af1bdd / Windows 38872859841 | Functional EXE PASS, συνολικό FAIL στην κονσόλα cp1252 μετά το report |
| 762c3a36 / Windows 38874685744 | SUCCESS: 45 regressions, EXE workflow, strict visual, accepted upload |
| 762c3a36 / Linux 38874685771, gate 38874685792, recovery 38874685760 | SUCCESS, recovery 8/8 |

Τα τοπικά αποτελέσματα κάθε μικρής αλλαγής, συμπεριλαμβανομένων τριών αποτυχημένων
σταδίων πριν από διόρθωση, αποθηκεύτηκαν στο `validation/local-20261016/` με index.
Το τελευταίο πλήρες τοπικό suite έχει **45 scripts PASS**, compileall src/tests/tools
και git diff --check PASS. Τέσσερις native Windows process/fixture περιπτώσεις
παραλείπονται ρητά στο Linux. Ο εξωτερικός EXE driver δεν εκτελείται στο Linux.
Τα παλιά αποθηκευμένα reports δεν προσμετρήθηκαν ως νέες εκτελέσεις.

Το νέο Qt workflow χρησιμοποιεί κανονικά Qt mouse/key events, προσωρινό προσωπικό,
offline θέση 14 ΕΞΟΔΟΣ START/END, κλείσιμο/επανέναρξη, replay με ίδια IDs/timestamps,
online θέση 1 ΕΙΣΟΔΟΣ START/END, δύο sessions, dialogs αρχείου/χάρτη και wrong PIN.
Ο Windows-only εξωτερικός driver επαναλαμβάνει το data workflow στο πραγματικό
PyInstaller EXE με native mouse/keyboard και αναγκαστικό stop του process tree.
Η πύλη packaging απαιτεί το functional report για το ίδιο SHA256 EXE και commit.

## Δοκιμαστικό EXE και όρια παράδοσης

Διαθέσιμο πιστοποιημένο δοκιμαστικό artifact πλήρους διάσπασης (60.5 MB):
`POSITION_TRACKING_WINDOWS_TEST-762c3a369a199766ab629007b6b2a3c27885d5e1-38874685744`.
https://github.com/danilidish-coder/TDE-potition_tracking/actions/runs/38874685744

Source SHA: `762c3a369a199766ab629007b6b2a3c27885d5e1`.
**EXE SHA256:** `beb836483229f3656e959c0891a7bd27cb7f58a0813b2bfa1015dabbf27699f7`.
Το SHA256 του GitHub artifact archive διαφέρει:
`27d252e4e2b781ed0dc53661e3600619953838452338f714e257a1d01c1f992b`.
Η διαθεσιμότητα/όνομα/μέγεθος επιβεβαιώθηκαν από τη σελίδα GitHub· η άμεση λήψη
archive μέσω API δεν είναι διαθέσιμη στο παρόν περιβάλλον. Το hash του EXE
τεκμηριώνεται στο αποθηκευμένο functional report της ίδιας έκδοσης.

Κάθε αποδεκτό πακέτο περιλαμβάνει EXE, SHA256SUMS, manifest, regressions, visual και
functional report. Διατήρηση 7 ημερών. Δεν δημιουργείται tag ή GitHub release.

## Υποχρεωτική επιτόπια αποδοχή

Χρειάζονται δοκιμαστικά δεδομένα και πραγματικό Windows/SMB περιβάλλον:

- 2+ πραγματικοί clients και host: ταυτόχρονα START/END στην ίδια θέση, ιδίως
  ΕΞΟΔΟΣ, χωρίς διπλή δέσμευση ή χαμένο receipt.
- Πραγματικά NTFS/share ACL, δύο Windows accounts στο ίδιο PC, lock/disconnect,
  logoff/reboot και κοινή PUBLIC ουρά με εκκρεμή END πριν από νέο handoff.
- Host power-off, δικτυακό flapping και διακοπή στη μέση εγγραφής/replay: διατήρηση
  όλων των αρχικών IDs/timestamps και ακριβώς μία οριστική εφαρμογή μετά επαναφορά.
- Πραγματικό όριο 10:00, 12/24ωρες και διαδοχικές βάρδιες, συμφωνία ιστορικού,
  διορθώσεων ώρας και τελικών αναφορών.
- Πολύωρη λειτουργία, κλείσιμο κατά μπλοκαρισμένο SMB I/O, ψυχρή/τοπική εκκίνηση
  χωρίς host, διαφορετικά DPI/μικρές οθόνες, πραγματικός εκτυπωτής και Word/Excel.

Οι προσομοιώσεις και το Windows CI δεν πιστοποιούν αυτά τα πραγματικά σενάρια.
Δεν δίνεται έγκριση παραγωγικής εγκατάστασης ή αντικατάστασης υπηρεσιακού EXE.

## Προστατευμένη κατάσταση

Main: `3c7a785a4008caa7b4fc1c7fd8d240cb8653ff99`.
Tag v1.2.5: `33ea13ca2133ddbfb93b1d051d4b25dc35bd954f`.
`release/`, `VERSION.txt`, production release workflow αμετάβλητα έναντι 129e8cb.
Καμία συγχώνευση, παραγωγική δημοσίευση ή επεξεργασία πραγματικών δεδομένων.

## Πρόσθετες διορθώσεις τελικής επαλήθευσης

Ο εξωτερικός driver έκλεινε λανθασμένα SQLite readers μόνο με το transaction
context manager. Πλέον τους κλείνει ρητά, διατηρεί αρχική εξαίρεση/screenshot και
δεν επιτρέπει στο cleanup να κρύβει την αιτία. Η επόμενη εκτέλεση αποκάλυψε αποτυχία
εστίασης του test background μετά τα native inputs. Η διόρθωση επιβεβαιώνει
WM_NULL acknowledgement και πραγματικό foreground HWND, με προσωρινό input-queue
attachment όπου απαιτείται και άμεσο detach. Τα αρχικά pending IDs/timestamps
διατηρήθηκαν άθικτα και στα δύο αποτυχημένα runs.

Εντοπίστηκαν και διορθώθηκαν τέσσερα missing type imports. Νέος έλεγχος επιλύει
και τα 226 annotations των ιδιόκτητων functions/methods. Κανένας αλγόριθμος ή
σχήμα δεδομένων δεν άλλαξε από αυτές τις διορθώσεις. Το πλήρες επιτόπιο πρωτόκολλο
βρίσκεται στο FIELD_ACCEPTANCE_EL.md και παραμένει ανεκτέλεστο.
