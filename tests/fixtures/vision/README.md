# Vision Regression Fixtures

This folder stores deterministic vision test cases for the OpenCV + YOLO + homography pipeline.

Current baseline:

- `synthetic_cases.json` describes synthetic board geometry, expected detections, and expected FEN output.
- `tests/unit/test_vision_regression.py` renders the synthetic board in memory, validates auto corner detection, maps synthetic detections to board cells, and checks the generated FEN.

To add real camera cases later:

1. Place stable sample images in this folder or a subfolder such as `real/`.
2. Add case metadata with image path, expected board corners, detections or expected FEN.
3. Keep image names date-free and descriptive, for example `overhead_bright_startpos_01.jpg`.
4. Avoid temporary screenshots, logs, or personally identifying background content.

Useful fields for new cases:

- `name`: stable case id.
- `image.path`: relative path from this folder.
- `image.board_quad`: expected board corners in TL, TR, BR, BL order.
- `grid`: board grid dimensions and rectified output size.
- `detections`: expected class labels, confidence, and cells for synthetic tests.
- `expected_fen`: final FEN after mapping detections.
