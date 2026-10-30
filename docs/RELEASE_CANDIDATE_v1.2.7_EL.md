# ΥΠΟΨΗΦΙΑ ΕΚΔΟΣΗ v1.2.7 — ΚΑΤΑΓΡΑΦΗ ΘΕΣΕΩΝ
Ημερομηνία απόφασης: 2026-10-28 (Ελλάδα)
Κατάσταση: ΔΟΚΙΜΑΣΤΙΚΟ EXE ΤΕΧΝΙΚΑ ΚΑΤΑΣΚΕΥΑΣΜΕΝΟ / ΠΑΡΑΔΟΘΗΚΕ ΓΙΑ ΔΟΚΙΜΗ. ΟΧΙ ΕΓΚΕΚΡΙΜΕΝΗ, ΟΧΙ ΕΓΚΑΤΕΣΤΗΜΕΝΗ.
Απόφαση χρήστη: ονομασία v1.2.7 και αυστηρός διαχωρισμός από την εγκεκριμένη v1.2.6.

## v1.2.7 — τρέχουσα υποψήφια
- Repository: danilidish-coder/TDE-potition_tracking
- Απομονωμένο branch: feature/central-only-simple-20261027 (ΟΧΙ main).
- Επαληθευμένο source commit του δοκιμαστικού EXE: 4c16f8e24387b1b0d1c4d578242ab03a7b84ca0d. Μεταγενέστερα docs-only commits δεν αλλάζουν το περιεχόμενο αυτού του EXE.
- Windows CI run 40764487136: source-gates FAILURE (Full source regressions), trial-exe SKIPPED. Προηγούμενο commit bdad6b67f0ce1a5b04c0f3b665106bc17636c9d0 πέρασε 64/64 υποχρεωτικά scripts στο Windows run 40760052465, αλλά αυτό ΔΕΝ εγκρίνει το νεότερο source.
- ΔΟΚΙΜΑΣΤΙΚΟ EXE v1.2.7: TDE_Katagrafi_Theseon_TRIAL.exe (εσωτερικό όνομα στο GitHub ZIP), ίδια πραγματικά bytes με το διανεμόμενο ως TDE_Katagrafi_Theseon_v1.2.7_TRIAL.exe.
- EXE SHA256: e302b82d9c06ce0e1673367de74c56792fa4840d8798c1c103ad55b542561430. EXE bytes: 52245654.
- Windows GitHub Actions: https://github.com/danilidish-coder/TDE-potition_tracking/actions/runs/40766791150 (source-gates SUCCESS, 65/65 υποχρεωτικά scripts PASS; 1 μη υποχρεωτικό ιστορικό script 5 FAIL, αποδεκτός περιορισμός χωρίς ισχυρή ταυτοποίηση ΑΞΥΠ).
- Trial-exe job SUCCESS: PyInstaller Windows EXE build και packaged frozen startup σε περιβάλλον χειριστή και ΑΞΥΠ PASS. Πραγματική ολοκλήρωση επιχειρησιακών λειτουργιών στο frozen EXE NOT RUN.
- GitHub artifact ID 12851257427, https://github.com/danilidish-coder/TDE-potition_tracking/actions/runs/40766791150/artifacts/12851257427 , προσωρινό GitHub retention έως 04/11/2026.
- ZIP bytes: 51914590, ZIP SHA256: b7f00217a84f4497cbb2308015e01c64a35fe2c63133b45d76c4e5ab3e33d3db.
- Drive ZIP: https://drive.google.com/file/d/1ZS7gcA-YNjKxFO9hEiSkVQUmYQxGYj-k/view , φάκελος δοκιμής https://drive.google.com/drive/folders/12xiAFPQZvbCySV7CxtOnR8sQE177shLC .
- ΕΠΑΛΗΘΕΥΣΗ ΜΕΤΑ ΤΗ ΛΗΨΗ: ZIP GitHub και ZIP Drive ίδιο SHA256 b7f002... και ίδια bytes 51914590. Αποσυμπιεσμένο EXE εντός και των δύο ZIP: SHA256 e302b82d... και 52245654 bytes. Δεν τεκμαίρεται επιτόπια έγκριση.
- Αποδοχή πραγματικών Windows/SMB/πολλών φυσικών σταθμών: NOT RUN.
- Το ZIP του GitHub περιέχει το αρχικό TDE_Katagrafi_Theseon_TRIAL.exe. Το εξαγόμενο και επαληθευμένο για άμεση λήψη αρχείο ονομάστηκε TDE_Katagrafi_Theseon_v1.2.7_TRIAL.exe χωρίς μεταβολή περιεχομένου.

## v1.2.6 — προστατευμένη εγκεκριμένη παραγωγική βάση
- Αποκλειστική τρέχουσα πηγή: CURRENT_APPROVED.json στο main, μέχρι νέα ρητή έγκριση.
- Source commit 4340c41865328cd893e6dc23fcdcedfefa7f9bf2.
- EXE: TDE_Katagrafi_Theseon.exe, SHA256 e59587390a398808ad454a1fb4de9d46c7d6139f203785489294655242b6de0d, 63.808.868 bytes.
- Drive: https://drive.google.com/file/d/1sjcXwqM2je6AAZponb4tRZqTThRgY_vd/view
- Δεν αλλάζουμε CURRENT_APPROVED.json, main, εγκατάσταση, shortcuts ή πραγματικά δεδομένα κατά την ανάπτυξη v1.2.7.
- Προσοχή: ιστορικό docs/ACTIVE_FIELD_VERSIONS_EL.md (18/10) περιγράφει παλαιότερο, διαφορετικό build v1.2.6 (SHA256 7671ef27..., 63.865.026 bytes). Δεν είναι αυτό το εγκεκριμένο binary που ορίζει το CURRENT_APPROVED.json (26/10). Απαιτείται ταυτοποίηση με hash, όχι τίτλο.

## Ακριβείς κανόνες απόφασης
1. «Δεν κάνει»: η υποψήφια v1.2.7 χαρακτηρίζεται ΑΠΟΡΡΙΦΘΗΚΕ. Αποσύρονται από τα ενεργά δοκιμαστικά μόνο τα ακριβώς ταυτοποιημένα προσωρινά EXE/artifacts κατόπιν σχετικής εντολής. Δεν πειράζουμε v1.2.6, ιστορικό commits, logs, ή αποδεικτικά διάγνωσης. Καμία καταστροφική ενέργεια σε υπηρεσιακά δεδομένα.
2. «Είναι ΟΚ»: επιτόπια αποδοχή από τον χρήστη, έπειτα ταυτοποίηση του ίδιου EXE (source SHA, Windows run ID, EXE SHA256 και bytes, Drive/GitHub location). Μόνο τότε ενημέρωση CURRENT_APPROVED.json και του ενεργού μητρώου για την v1.2.7 ως τρέχουσα λειτουργική. v1.2.6 διατηρείται για rollback.
3. Δεν σημαίνει επιτυχία το απλό build ή πράσινο CI. Χρειάζεται δοκιμή στα πραγματικά σενάρια χρήσης.
4. Κάθε νέο candidate build v1.2.7 απαιτεί δικό του συγκεκριμένο manifest με commit, run, SHA256, bytes και αποτελέσματα. Δεν αντιγράφουμε στοιχεία προηγούμενου EXE.

## Άμεσο τεχνικό βήμα
Ολοκληρώθηκαν source gates 65/65 PASS και sandbox trial EXE build + δύο startup smoke PASS στο run 40766791150. ΕΠΟΜΕΝΟ: πραγματική δοκιμή μόνο στο TDE_TRIAL_SANDBOX με δοκιμαστικά δεδομένα, operator START/END, panel ΑΞΥΠ, παλιές βάρδιες/ιστορικά, αναφορές, σύγχρονη πρόσβαση, διακοπή/επανεκκίνηση SMB. Καταγραφή PASS/FAIL/NOT RUN. Το frozen end-to-end και 15 πραγματικοί σταθμοί παραμένουν NOT RUN. Μετά από ρητή αποδοχή trial απαιτείται production candidate (διαφορετικό EXE), δικές του δοκιμές και έγκριση. ΟΧΙ αλλαγή παραγωγής.

## Υποχρεωτικό όριο trial έναντι παραγωγικής v1.2.7 (έλεγχος 28/10/2026)
- Το δοκιμαστικό entry `src/position_tracking_trial.py` απαιτεί φυσικό φάκελο με όνομα `TDE_TRIAL_SANDBOX` και απορρίπτει `central_root` εκτός του sandbox. Είναι σκόπιμη ασφαλιστική δικλίδα, ΟΧΙ τελικό EXE έτοιμο για τον παραγωγικό φάκελο.
- Επομένως «το δοκιμαστικό v1.2.7 είναι ΟΚ» σημαίνει αποδοχή της συμπεριφοράς στο απομονωμένο περιβάλλον. Δεν επιτρέπεται η απλή μετονομασία/μεταφορά του ίδιου trial EXE πάνω από το εγκεκριμένο v1.2.6: θα αρνηθεί την εκκίνηση εκτός sandbox ή θα χρησιμοποιεί μόνο δοκιμαστικά δεδομένα.
- Απαιτείται **ξεχωριστή, επαληθευμένη παραγωγική υποψήφια κατασκευή v1.2.7** με central-only entry, ίδια επιχειρησιακή λογική, κανονικό πραγματικό κοινόχρηστο κεντρικό root, διαγνωστικούς και regression/frozen Windows ελέγχους. Θα έχει διαφορετικό EXE SHA256 και δικό της manifest.
- Η παραγωγική v1.2.7 μπορεί να χαρακτηριστεί **τρέχουσα λειτουργική** μόνο με ρητή αποδοχή του χρήστη για το ακριβές τελικό binary και ασφαλή διαδικασία εγκατάστασης/rollback. Η v1.2.6 διατηρείται ανέπαφη μέχρι τότε.
- Για τη σαφήνεια ονομάτων της δοκιμαστικής διανομής χρησιμοποιούμε ετικέτα `v1.2.7 TRIAL` μαζί με πλήρες SHA256· το αρχικό όνομα από το παρόν workflow `TDE_Katagrafi_Theseon_TRIAL.exe` δεν αποδεικνύει έκδοση μόνο του.
- Η τρέχουσα πύλη trial μετά τα source gates εκτελεί frozen STARTUP μόνο (χειριστής/ΑΞΥΠ) και όχι πλήρες frozen end-to-end / 15 φυσικοί σταθμοί / SMB. Αυτά παραμένουν NOT RUN μέχρι αποδεικτικό.
