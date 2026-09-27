# TDE Position Tracking

Windows standalone εφαρμογή για Καταγραφή Θέσεων του Τ.Δ.Ε. Κρυσταλλοπηγής.

## Δομή
- `src/position_tracking.py`: πραγματικός πηγαίος κώδικας.
- `requirements.txt`: εξαρτήσεις build/runtime.
- `tests/`: αυτοματοποιημένα tests και επιβεβαιωμένα reports.
- `release/`: έτοιμα Windows EXE όπου απαιτείται.
- `.github/workflows/build-windows.yml`: Windows build, tests και smoke test.
- `DEVELOPMENT_RULES.md`: μόνιμοι κανόνες εργασίας για μελλοντικές αλλαγές.

## Κανόνας αποθήκευσης
Το GitHub `main` είναι η πηγή αλήθειας. Ο πηγαίος κώδικας παραμένει ξεζιπαρισμένος στο GitHub. ZIP δημιουργείται μόνο όταν ζητείται ρητά ως πακέτο μεταφοράς/λήψης.
