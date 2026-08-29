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
| `vision/best.pt` | 5403269 | `9452278AEAD49BAFB5B1D3329E6C3BC950A586C60D75A91A459BF6F469B847BF` | Configured Ultralytics YOLO runtime model |
| `vision/dataset_mapping.yaml` | 511 | `F5AF27794DAC1E2E84EA5073EE14A537564AEFE96DFEE7D66572765C1E943B99` | Preserved dataset class mapping |
| `vision/args.yaml` | 1607 | `833DDE4DF86E96789DF9BE20D8E0F0FDF05F82C16A50D27E606B1DAD4CDDF869` | Preserved YOLO training/export args |
