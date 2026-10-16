# Αδρανής έξοδος και επαγγελματική θωράκιση χάρτη — 16/10/2026

## Τρέχουσα κατάσταση

Αφετηρία checkpoint 278307b6ff46223db0685bcc867f9229b7e1554b.
Αποκλειστικά feature/v125-modularization-20261013. Δεν επαναλήφθηκε η ολοκληρωμένη
modularization ή εγκατάσταση. Δεν άλλαξαν main, σταθερή v1.2.5 ή υπηρεσιακά δεδομένα.
Η νέα έκδοση έχει πλήρες τοπικό PASS 50 scripts. Windows/Linux/gate και το νέο
accepted test EXE αναμένονται στον έναν συνδυασμένο τελικό κύκλο.

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

- 10 πραγματικά Python subprocess/Qt application-loop σενάρια idle exit: άδειο
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
