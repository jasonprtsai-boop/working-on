# Protected Asset Manifest

This folder stores runtime-critical binary assets. Do not edit, rename, delete,
or replace these files during normal refactoring or documentation cleanup.

## Rules

- Treat files in this folder as immutable runtime assets.
- Keep this manifest with the protected files.
- If an asset must be upgraded, copy the new file here intentionally and update
  the size and SHA256 below.
- Runtime configuration should prefer this folder over working or test copies.
- Release hygiene checks must keep these assets while excluding local secrets,
  logs, databases, caches, dependency folders, and generated reports.

## Assets

| Asset | Size bytes | SHA256 | Source copy |
| --- | ---: | --- | --- |
| `engine/pikafish-avx2.exe` | 1618432 | `33D588911BE6DC65A48B7CDDA7DFB1573B58B6C4C6A8A4661AF07512D039EBF3` | Protected canonical copy |
| `engine/pikafish.nnue` | 53212941 | `C4026370D7516D9B0F668447F9CA1931241538BDC689CDE6FEC6A991AC4D5F77` | Protected canonical copy |
| `vision/best.pt` | 5410565 | `306B9117D88EBBDF42525D078ABEF0374D2FE94BE8134E13DACBC5D0ECB075DD` | Protected canonical copy |
