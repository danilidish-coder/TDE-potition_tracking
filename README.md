# TDE Position Tracking

Windows standalone εφαρμογή για Καταγραφή Θέσεων του Τ.Δ.Ε. Κρυσταλλοπηγής.

## Δομή
- `src/position_tracking.py`: πραγματικός πηγαίος κώδικας.
- `requirements.txt`: εξαρτήσεις build/runtime.
- `tests/reports/`: επιβεβαιωμένα reports δοκιμών.
- `release/`: έτοιμα Windows EXE.
- `.github/workflows/build-windows.yml`: Windows build + smoke test.

## Κανόνας αποθήκευσης
Ο πηγαίος κώδικας παραμένει ξεζιπαρισμένος στο GitHub. ZIP δημιουργείται μόνο όταν απαιτείται πακέτο μεταφοράς.
