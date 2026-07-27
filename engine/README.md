# Reference Xiangqi Engine

This directory contains a small pure-Python reference engine used for learning,
experiments, and isolated rule/search checks. It is not the production runtime
engine for the robot.

Production and release builds should use the protected Pikafish assets under:

- `backend/infrastructure/protected_assets/engine/pikafish-avx2.exe`
- `backend/infrastructure/protected_assets/engine/pikafish.nnue`

Do not wire this reference engine into robot auto-execution unless it has a
separate safety review and integration test coverage.
