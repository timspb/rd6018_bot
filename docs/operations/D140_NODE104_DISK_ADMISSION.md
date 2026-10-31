# D140 — pre-stop rollback capacity gate

Read-only evaluation on node104 after D138 candidate preparation.

- Installed app allocated bytes: **11,202,560**.
- Installed venv allocated bytes: **275,472,384**.
- Backup copy required bytes: **286,674,944**.
- Safety reserve: **268,435,456** (256 MiB).
- Filesystem/journal overhead: **16,777,216** (16 MiB).
- **Minimum free**: **571,887,616** bytes.
- **Observed free**: **420,859,904** bytes.
- **Missing**: **151,027,712** bytes.
- Result: **capacity_pass=false**; release activation stays BLOCKED.

D140 adds `tools/d140_disk_guard.py`, a read-only conservative allocation check and an invocation from the existing canonical D090 transaction owner's software-release `activate()` path *before* its activation journal write or service stop. It reuses the established D090 owner; it does not create an independent production cutover executor. Four isolated negative/threshold tests PASS on node104.

The free-space check is not a substitute for physical OFF, Native/ESP proof freshness, correct session authority, candidate integrity or actual release acceptance. Real production code is **not deployed**: these are canonical source changes only, and node104's earlier installed D090 CLI is not overwritten. A future production activation must pass the gate freshly.

Do not delete historical D090 backup (2.4 GB under the broader backups directory), current venv, retired session or any unreviewed evidence to create space. Before any cutover, safely offload truly disposable test-only temporary archives with copy verification, remeasure actual disk capacity, and complete physical/safety gate checks.

No service stop, Output ON, battery setting, OVP/OCP or 900s lease change performed.
