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
| `vision/best.onnx` | 44996805 | `755554C97A2BA94FBE78794DFE8B50140BDCA4F6895B0B8DE0750959D81D3C16` | Configured YOLO26-compatible ONNX runtime model |
| `vision/best.pt` | 22499306 | `123DF038FB7977D6D1FF947E4BF468D0F806726A1A516DEBD37AABEC0ECE83DF` | Preserved YOLO training/export artifact |
| `vision/dataset_mapping.yaml` | 628 | `91D46F301B1A8FA94D78909B528EA65CE7F294D7685C40613F7DAEE438735A4C` | Preserved dataset class mapping |
| `vision/args.yaml` | 1607 | `833DDE4DF86E96789DF9BE20D8E0F0FDF05F82C16A50D27E606B1DAD4CDDF869` | Preserved YOLO training/export args |
