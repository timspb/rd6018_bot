# AUTONOMOUS validation freeze

Software validation is complete for the frozen repository baseline. The next
workflow stage is physical RD6018 validation and evidence collection only.

## Freeze rules

- The repository is frozen for the duration of physical validation.
- Runtime Python changes are prohibited during the hardware run.
- ESPHome and firmware changes are prohibited during the hardware run.
- Safety logic, authority paths, thresholds and configuration must not be
  changed as part of evidence collection.
- Only physical evidence and test results may be added to the validation
  records.
- A suspected defect must first be preserved and classified with evidence as
  `EXPECTED`, `SOFTWARE DEFECT`, `FIRMWARE DEFECT`, `HARDWARE ISSUE` or
  `OPERATOR/SETUP ISSUE` before any patching is considered.

Use [the physical validation results ledger](autonomous_physical_validation_results.md)
and [the master field validation run](autonomous_full_field_validation_run.md)
as the operator entry points. Missing or ambiguous evidence is `BLOCKED`, not
an inferred pass or defect.
