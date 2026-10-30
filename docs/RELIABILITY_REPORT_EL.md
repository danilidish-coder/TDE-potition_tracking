# Αδρανής έξοδος και επαγγελματική θωράκιση χάρτη — 16/10/2026

## Τελική αυτοματοποιημένη αποδοχή της διόρθωσης

Source SHA: `410bf72fe197e6e7d9a4a1a299a135a716c71bf3`.
Windows **38916161811 SUCCESS**, Linux **38916162147 SUCCESS**, module gate
**38916162111 SUCCESS**. 50 regression scripts, build/smoke και πραγματικό EXE:
αδρανής έξοδος με normal process exit **0**, **0 καταγραφές**, χωρίς central/roster.
Παράλληλα PASS το αρχικό data workflow: 4 πράξεις, 2 sessions, ίδια IDs/timestamps.
Strict visual **0/20** startup, **0/30** theme, **30/30** επιβεβαιωμένα clicks.
12 idle subprocess cases (μαζί με καθυστερημένη αποτυχία), 8 map και 6 exit tests PASS.

[Νέο δοκιμαστικό EXE — Artifacts του επιτυχημένου run](https://github.com/danilidish-coder/TDE-potition_tracking/actions/runs/38916161811):
`POSITION_TRACKING_WINDOWS_TEST-410bf72fe197e6e7d9a4a1a299a135a716c71bf3-38916161811` (60.6 MB, διατήρηση 7 ημερών).
**EXE SHA256:** `3f896e307abfcbde477e201259e02f2e2cd683eafe18064b9ecea3a81a790f24`.
Archive SHA256: `ff3736fe28a824b5bfd9207412b18d9e49506662d5902594c2eeac7d0c2c29fd`.
Η διαθεσιμότητα επιβεβαιώθηκε στη completed Actions σελίδα· hash του EXE από
πραγματικό native report και υποχρεωτική packaging gate, χωρίς download archive
στο cloud. Evidence: `validation/windows-visual-38916161811-1/` και
`validation/idle-exit-20261016/final-verification.json` / `commit-ledger.json`.

Η τοπική άδεια είναι συντηρητική: αφορά παράθυρο που δεν επιχείρησε καταχώριση
και έχει την παρακάτω απόδειξη. Σε παράθυρο με attempted καταχώριση/αβεβαιότητα
παραμένει κεντρικός έλεγχος. Το απλό κλείσιμο δεν ισοδυναμεί με αποδέσμευση θέσης.
Οι πραγματικές software/field εκκρεμότητες παρακάτω δεν χαρακτηρίζονται PASS.


## Τρέχουσα κατάσταση

Αφετηρία checkpoint 278307b6ff46223db0685bcc867f9229b7e1554b.
Αποκλειστικά feature/v125-modularization-20261013. Δεν επαναλήφθηκε η ολοκληρωμένη
modularization ή εγκατάσταση. Δεν άλλαξαν main, σταθερή v1.2.5 ή υπηρεσιακά δεδομένα.
Η τελική έκδοση έχει πλήρες τοπικό και Windows/Linux/gate PASS και διαθέσιμο
accepted test EXE όπως τεκμηριώνεται παραπάνω.

## Αιτίες και διορθώσεις

| Πρόβλημα / πραγματική αναπαραγωγή | Ελάχιστη διόρθωση |
|---|---|
| Home launch χωρίς central/roster/START/END: πραγματικό QApplication quit αποτυγχάνει με σφάλμα reconciliation | c7cdfd5: ξεχωριστή απόδειξη ασφαλούς απλού κλεισίματος. Δεν επιχειρείται END όταν δεν υπάρχει υποχρέωση |
| Map selected read κρατά το Qt callback 0.800s | 8eb31dc: read στο υπάρχον single map worker, Qt μόνο για widgets/confirmations |
| Map END κλείνει νεότερο START που αντικατέστησε το επιλεγμένο στη διάρκεια confirmation | expected_start_event_id στην υπάρχουσα κλειδωμένη END API, χωρίς νέο END σε replacement |
| Map correction επίσης μπλοκάρει Qt 0.800s και γράφει διόρθωση σε replacement START | async read/write και optional expected_start_event_id έλεγχος μέσα στο υπάρχον officer lock. Legacy τετραπαραμετρική API παραμένει |
| Κλείσιμο/remote app exit μπορεί να προσπεράσει pending map mutation | Owner-tracked future, strict app exit το περιμένει. Pending write δεν εγκαταλείπεται με κλείσιμο map. Read-only close δεν συνεχίζει αργότερα σε END |

Η απόδειξη αδρανούς εξόδου δεν βασίζεται σε κενό προσωπικό ή αποσύνδεση:
απαιτεί ρητά αχρησιμοποίητη θέση στο συγκεκριμένο παράθυρο, ολοκληρωμένες σχετικές
εργασίες, κανένα handoff error και μία συνεπή τοπική SQL snapshot χωρίς
pending/conflict/άγνωστες εγγραφές ή ενεργές/invalid observations. Κάθε START
πρέπει να έχει εφαρμοσμένο END με το ίδιο START ID και AGMS. Corruption/αβεβαιότητα
δεν θεωρείται κενό. Το shortcut δεν γράφει END/ACK και δεν δηλώνει αποδέσμευση
άλλων θέσεων. Με attempted START/END ή remote CLOSE ισχύει η αυστηρή κεντρική οδός.
Τα confirmation/error κείμενα διακρίνουν πλέον κλείσιμο εφαρμογής από ΛΗΞΗ θέσης.

Τα map I/O γίνονται εκτός GUI, με μία πράξη κάθε φορά. Δεν κλείνεται replacement
START και δεν αλλάζει το raw START timestamp στη διόρθωση. Η επικύρωση γίνεται
κάτω από το ίδιο lock που προστατεύει την εγγραφή. Δεν άλλαξαν schemas, αρχικά
IDs/timestamps, outbox, receipts, cache durability ή υπάρχουσες αναφορές.

## Επαληθευμένοι έλεγχοι και διατήρηση FAILs

- 12 πραγματικά Python subprocess/Qt application-loop σενάρια idle exit: άδειο
  προφίλ, confirmed closed history και αρνητικά pending, conflict, unmatched
  APPLIED START με άδεια cache, active/corrupt observation, in-flight εργασία,
  attempted action και remote command. Τα θετικά τερματίζουν πραγματικά το process.
- 8 Qt map tests: responsiveness, stale END/correction, έλλειψη START ID,
  κλείσιμο κατά read/write, duplicate guard και επιτυχής correction με raw event
  και ID αμετάβλητα. 6 exit tests, μαζί με αναμονή map mutation πριν remote ACK.
- Πλήρες portable suite: 49 PASS μετά το idle fix, 50 PASS μετά map END και
  ξανά 50 PASS μετά την πραγματική νέα correction διόρθωση. Δεν επαναλήφθηκαν
  full suites απλώς για checkpoint. Native-only περιπτώσεις δεν εκτελούνται στο Linux.
- Packaging gate 5 tests και driver fixture 3 tests PASS, compileall src/tests/tools
  και diff checks PASS. Το νέο native idle proof ΔΕΝ έχει εκτελεστεί τοπικά στο Linux.

Αρχικά FAILs/τελικά outcomes: validation/idle-exit-20261016/,
validation/live-map-end-20261016/, validation/live-map-correction-20261016/.
Τα προηγούμενα Windows artifacts/CI/600s soak διατηρούνται ιστορικά στο
validation/idle-exit-20261016/reliability-history.md. Δεν πιστοποιούν αυτόματα
τον μεταγενέστερο κώδικα ούτε χρησιμοποιήθηκαν ως ψευδές νέο PASS.

## Καθυστερημένη αποτυχία σύνδεσης

Πρόσθετη αναπαραγωγή έδειξε ότι η πρώτη διόρθωση απαιτούσε η σύνδεση να έχει
ήδη αποτύχει πριν πατηθεί ΕΞΟΔΟΣ. Αν αποτύγχανε αργότερα, το ίδιο άδειο προφίλ
παρέμενε ανοικτό με σφάλμα. Τώρα, μετά την ολοκλήρωση της εργασίας, επανελέγχεται
η ίδια αυστηρή απόδειξη αδρανούς κατάστασης. Δεν αγνοείται ενεργή εργασία,
pending START, άγνωστη κατάσταση ή remote ACK. Οι 12 real-process περιπτώσεις
και ολόκληρη η suite των 50 scripts PASS. Αρχικό FAIL/τελικά reports βρίσκονται
στο validation/idle-exit-late-20261016/. Αυτή η πραγματική αλλαγή δικαιολογεί
τελικό νέο native κύκλο· δεν μεταφέρεται το PASS από προγενέστερο commit.

## Native EXE acceptance πριν από νέο artifact

Ο εξωτερικός Windows driver χρησιμοποιεί νέο προσωπικό/machine test profile,
ανύπαρκτο central και roster, κανονικό παράθυρο EXE, native Exit/Yes και απαιτεί
κανονική λήξη ολόκληρης της διεργασίας, χωρίς καταγραφές/δημιουργία κεντρικού.
Δεν υπάρχει κρυφό test mode. Κατόπιν παραμένει υποχρεωτικό το υπάρχον πραγματικό
EXE offline START/END, restart, replay, online START/END, 4 αρχικά IDs/timestamps
και 2 sessions. Packaging απορρίπτει ελλιπές/αποτυχημένο idle exit, μαζί με όλες
τις υπάρχουσες αυστηρές regression/visual/source-SHA/EXE-hash πύλες.

## Πραγματικές εκκρεμότητες

- History/reports, messaging/ACK, roster και τμήματα shift/admin παραμένουν
  συγχρονισμένες shared-I/O διαδρομές προς στοχευμένη διάγνωση/διόρθωση. Δεν
  ισχυριζόμαστε ότι όλο το GUI έχει πλέον απαλλαγεί από πιθανά SMB stalls.
- Python thread/future timeouts δεν ακυρώνουν blocked Windows kernel SMB I/O.
  Η GUI διατηρεί απόκριση στις διορθωμένες οδούς, αλλά πραγματικός process exit
  με μόνιμα μπλοκαρισμένο I/O δεν έχει πιστοποιηθεί. Δεν προστέθηκε force-kill
  ή ακύρωση αβέβαιης καταγραφής. Ο χάρτης μένει ανοικτός όσο write εκκρεμεί.
- SQLite GUI reads διατηρούν busy timeout 2s. Watchdog παραμένει τοπικός, bounded
  ανά process, χωρίς προσωπικά περιεχόμενα· retention μεταξύ sessions εκκρεμεί.
- FIELD_ACCEPTANCE_EL.md: 15 πραγματικά PCs/SMB/ACL, Windows users/session/logoff/
  reboot, power loss/replay, 10:00 και 12/24h, DPI/printing/cold cached launch.
  Αυτές οι δοκιμές παραμένουν ΑΝΕΚΤΕΛΕΣΤΕΣ. Δεν υπάρχει παραγωγική έγκριση/release.

## Οικονομία κύκλων και ιστορικό

Ο ενδιάμεσος ec8eab7 πέρασε Windows 38914933955/Linux 38914934027/gate 38914933969,
περιλαμβάνοντας πραγματικό native idle exit. Δεν ήταν τυφλή αποτυχία CI: νέα
στοχευμένη τοπική δοκιμή αποκάλυψε εκ των υστέρων τη delayed-connection περίπτωση.
Η ελάχιστη διόρθωση 410bf72 και τα δύο επιπλέον θετικά/αρνητικά cases δικαιολόγησαν
τον τελικό νέο cycle. Αρχικά FAILs, ενδιάμεσα PASS και τελικά αποτελέσματα
διατηρούνται με ακριβή SHA/run IDs. Δεν επαναλήφθηκε παλιά modularization/εγκατάσταση
ή το παλιό 600s soak για διαφορετικό source και δεν μεταφέρθηκε η πιστοποίησή του.
