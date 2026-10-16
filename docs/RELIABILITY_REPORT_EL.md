# Επαγγελματική θωράκιση — 16/10/2026

## Επαληθευμένη αφετηρία

Η modularization ολοκληρώθηκε στο source
`762c3a369a199766ab629007b6b2a3c27885d5e1`.
Επιβεβαιώθηκαν τα υπάρχοντα Windows 38874685744, Linux 38874685771,
gate 38874685792 και recovery 38874685760 (8/8): SUCCESS. Το προηγούμενο EXE
και το ακριβές hash περιγράφονται στο MODULARIZATION_REPORT_EL.md. Δεν
επανεκτελέστηκαν οι ίδιοι έλεγχοι χωρίς αλλαγή κώδικα.

## Αναπαραγωγές και ελάχιστες διορθώσεις

| Πρόβλημα | Πραγματική απόδειξη | Διόρθωση / έλεγχος |
|---|---|---|
| Απεριόριστη συσσώρευση αναγνώσεων επιλογής | 200 αλλαγές με μπλοκαρισμένη remote ανάγνωση άφησαν 199 queued εργασίες | 4ef0041: μία ενεργή ανάγνωση, η τελευταία επιλογή ανανεώνεται μετά την ανάκαμψη. Πλήρης suite 46 PASS |
| Καθυστερημένο START ανέστησε κλεισμένη εγγραφή στην κοινή cache | Δεύτερο journal ολοκλήρωσε END· παλιά GUI ανάγνωση επανέγραψε START | 39b44f0: ατομικό compare revision σε SQLite πριν από remember, χωρίς lock κατά το SMB I/O. Delayed START και delayed empty-read regressions PASS, suite 46 PASS |
| GUI μπλοκάρισμα στην κανονική/απομακρυσμένη έξοδο | Ελεγχόμενο κεντρικό I/O κράτησε το Qt callback περίπου 0.8s | 1589663: μία ασύγχρονη επιβεβαιωμένη έξοδος, heartbeat Qt ζωντανό, duplicate guard, ACK μόνο μετά END, αποτυχία/pending δεν κλείνει την εφαρμογή. 5 targeted tests και suite 47 PASS |
| Απουσία ανεξάρτητης αιτιολόγησης παγώματος | Οι παλιές αποτυχίες έλειπαν από stack/resource στοιχεία | Τοπικός watchdog καταγράφει GUI/worker stall και ανακάμψεις, stacks χωρίς locals/source lines/πλήρη paths, πόρους/ουρές. 4 targeted tests και suite 48 PASS |

Τα αρχικά FAIL και τα αποτελέσματα μετά τη διόρθωση βρίσκονται στο
`validation/reliability-20261016/`. Τα ενδιάμεσα commits διατηρήθηκαν με skip CI
για να μην παράγουν επαναλαμβανόμενα EXE. Η τελική έκδοση απαιτεί νέο native CI
επειδή άλλαξαν πραγματικές λειτουργίες. Δεν μεταφέρεται το προηγούμενο PASS.
Schemas, αρχικά event IDs/timestamps, START/END links και queue location
παραμένουν συμβατά. Η παλιά remember API παραμένει διαθέσιμη.

## Κάλυψη που ήδη υπήρχε και επανελέγχθηκε στις νέες αλλαγές

Η πλήρης σουίτα καλύπτει 15 ξεχωριστές συνθετικές διεργασίες με offline restart,
14 φυσικές θέσεις και έναν εμφανή conflict, αντί διπλής κράτησης. Περιλαμβάνει
250 διαδοχικούς κύκλους θέσης, 56 concurrent claims, OS lock contention,
100 κύκλους αλλαγής βάρδιας/membership, stale START IDs, ACK-loss recovery,
cache transaction rollback, account handoff order και όριο 10:00/12/24ωρων.
Οι προσομοιωμένες ταυτότητες δεν είναι πραγματικά Windows logoff/session tests.
Ο έλεγχος πραγματικού frozen EXE και τα αυστηρά visual είναι χωριστές Windows πύλες.

## Μετρήσιμη δοκιμή διάρκειας

Το `tools/soak_reliability.py --seconds 600 --out <test-output>` χρησιμοποιεί
πραγματικό Qt παράθυρο και αποκλειστικά νέο πλασματικό dataset. Περιλαμβάνει
περιοδικά offline START/END στη θέση 14 ΕΞΟΔΟΣ, επαναφορά και ακριβή έλεγχο IDs,
timestamps και END links, bursts 100 εισόδων και κύματα 15 ανεξάρτητων clients.
Η αποσύνδεση γίνεται με ελεγχόμενη fault injection, όχι πραγματικό SMB power-off.
Καταγράφει κάθε δευτερόλεπτο RSS, CPU, threads/handles και ουρές ανά 20ms περίπου.
Πύλες: GUI gap <1s, RSS αύξηση μετά warmup <32MiB, handles αύξηση <=16,
CPU <25% ενός core κατά μέσο όρο, bounded queue sizes, ακριβής συμφωνία receipts.
Αυτά είναι όρια της δοκιμής, όχι εγγύηση μηδενικής διαρροής ή υπηρεσιακό SLA.
Το τελικό 600s report και τα native CI αποτελέσματα εκκρεμούν σε αυτό το checkpoint.

## Διαγνωστικά στην υπηρεσιακή δοκιμή

Τα logs βρίσκονται στο προσωπικό `local_root/diagnostics/runtime-PID.jsonl`.
Όριο 512KiB + 3 backups ανά process, χωρίς αποθήκευση στο κοινόχρηστο share.
Παλιές συνεδρίες δεν διαγράφονται αυτόματα· απαιτείται πολιτική retention ανά
υπολογιστή πριν από πολύμηνη χρήση. Δεν περιέχουν roster/AGMS/κείμενα μηνυμάτων,
locals ή exceptions με paths. Είναι διαγνωστικά, όχι αντίγραφο ασφαλείας δεδομένων.
Ο watchdog δεν ακυρώνει threads ούτε αναγνωρίζει εγγραφές ως συγχρονισμένες.

## Ειλικρινή τεχνικά όρια και κίνδυνοι

1. Τα 6/10/15/20s όρια εφαρμογικών locks και τα SQLite busy timeouts αφορούν
   αντίστοιχα contention. Δεν περιορίζουν τη διάρκεια ενός `mkdir`, `open`, read,
   `replace` ή άλλου SMB system call του Windows redirector. `Future.result`
   timeout και `shutdown(wait=False)` δεν τερματίζουν ήδη εκτελούμενο thread.
   Οριστικός τερματισμός process υπό ατέρμονο kernel I/O **δεν πιστοποιείται**.
   Δεν προστέθηκαν επικίνδυνα force-kill ή daemon writers που κόβουν εγγραφές.
2. Παραμένουν συγχρονισμένες ενέργειες GUI σε ιστορικό/αναφορές, μηνύματα/ACK,
   διοικητικό backup/audit, αρχική roster εύρεση χωρίς cache και ορισμένες
   ενέργειες βάρδιας/χάρτη. Το static audit δείχνει δυνατότητα stall υπό SMB
   καθυστέρηση· δεν αποδεικνύει ότι όλες παγώνουν στο πραγματικό δίκτυο.
   Απαιτείται ελεγχόμενη επιτόπια αναπαραγωγή με watchdog logs και στοχευμένη
   μεταφορά συγκεκριμένων I/O ενεργειών, χωρίς μαζικό rewrite ή ψευδές PASS.
3. Τα τοπικά SQLite reads στο GUI έχουν finite busy timeout 2s, που μπορεί να
   γίνει ορατή καθυστέρηση υπό παρατεταμένη τοπική contention. Δεν εξισώνεται
   finite wait με πλήρη responsiveness και δεν αφαιρέθηκε το durability.
4. Το JSON replace και SQLite FULL/rollback journal παραμένουν ως είχαν.
   Δεν αποδεικνύεται συμπεριφορά write-cache/power-loss/SMB lease ανά host από
   τοπική προσομοίωση. Το απομονωμένο πραγματικό hardware trial είναι αναγκαίο.

## Πριν από παραγωγική έγκριση

Εκτέλεση όλου του FIELD_ACCEPTANCE_EL.md σε νέο test share και πλασματικό roster:
15 πραγματικοί clients, δύο πραγματικοί Windows χρήστες στο ίδιο PC, ΕΞΟΔΟΣ/10:00,
lock/disconnect/logoff/reboot, ACL denied, power loss/replay, τουλάχιστον 12/24h
παρακολούθηση πόρων και responsive shutdown με μπλοκαρισμένο SMB. Συλλογή
watchdog logs και ακριβών αρχικών/τελικών IDs/timestamps. Ψυχρή cached εκκίνηση,
πραγματικά DPI/εκτυπώσεις/Office και τελική ανθρώπινη έγκριση παραμένουν υποχρεωτικά.
Δεν εγκρίθηκε παραγωγική εγκατάσταση, release/tag ή μεταβολή πραγματικών δεδομένων.
