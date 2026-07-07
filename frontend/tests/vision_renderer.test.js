import { VisionRenderer } from '../static/js/modules/board/vision_renderer.js';
import { UIRegistry } from '../static/js/modules/ui/ui_registry.js';
import { installFakeDom, setupContainer } from './test_dom.js';

test('vision overlay maps natural image bbox into contained display rect', () => {
  VisionRenderer.canvas = { width: 800, height: 600 };
  VisionRenderer.video = { naturalWidth: 1280, naturalHeight: 720 };

  const box = VisionRenderer.normalizeBox({
    bbox: [320, 180, 640, 360],
    confidence: 0.8,
  });

  expect(box.x).toBeCloseTo(200);
  expect(box.y).toBeCloseTo(187.5);
  expect(box.w).toBeCloseTo(200);
  expect(box.h).toBeCloseTo(112.5);
});

test('vision overlay supports normalized bbox values', () => {
  VisionRenderer.canvas = { width: 1000, height: 1000 };
  VisionRenderer.video = { naturalWidth: 1000, naturalHeight: 1000 };

  const box = VisionRenderer.normalizeBox({
    bbox: [0.1, 0.2, 0.3, 0.4],
  });

  expect(box.x).toBeCloseTo(100);
  expect(box.y).toBeCloseTo(200);
  expect(box.w).toBeCloseTo(200);
  expect(box.h).toBeCloseTo(200);
});

test('vision overlay writes detection coordinate summary', () => {
  installFakeDom();
  const coords = setupContainer('video-overlay-coords');
  UIRegistry.init();

  VisionRenderer.renderDetectionSummary([
    {
      class_name: 'black_cannon',
      confidence: 0.82,
      bbox: [10, 20, 30, 40],
    },
  ]);

  expect(coords.textContent).toContain('black_cannon 82% [10, 20, 30, 40]');
});

test('vision overlay draws calibration grid when enabled and calibrated', () => {
  const calls = [];
  VisionRenderer.canvas = { width: 900, height: 1000 };
  VisionRenderer.video = { naturalWidth: 900, naturalHeight: 1000 };
  VisionRenderer.ctx = {
    save: () => calls.push('save'),
    restore: () => calls.push('restore'),
    beginPath: () => calls.push('begin'),
    moveTo: (x, y) => calls.push(['moveTo', x, y]),
    lineTo: (x, y) => calls.push(['lineTo', x, y]),
    stroke: () => calls.push('stroke'),
    arc: (x, y) => calls.push(['arc', x, y]),
    fill: () => calls.push('fill'),
    set strokeStyle(_value) {},
    set fillStyle(_value) {},
    set lineWidth(_value) {},
  };

  VisionRenderer.calibrationGridVisible = true;
  VisionRenderer.drawCalibrationGrid({
    calibrated: true,
    calibration: { output_size: [900, 1000] },
  });

  expect(calls.filter((item) => item === 'stroke')).toHaveLength(19);
  expect(calls.filter((item) => item === 'fill')).toHaveLength(4);
});
