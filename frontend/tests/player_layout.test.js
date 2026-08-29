import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const playerCss = readFileSync(
  resolve(process.cwd(), 'frontend/static/css/views/player.css'),
  'utf8'
);

const responsiveCss = readFileSync(
  resolve(process.cwd(), 'frontend/static/css/responsive.css'),
  'utf8'
);

test('player view keeps the board centered in a fixed one-screen layout', () => {
  expect(playerCss).toContain('height: 100dvh;');
  expect(playerCss).toContain('max-height: 100dvh;');
  expect(playerCss).toContain('overflow: hidden;');
  expect(playerCss).toContain('"guide board turn"');
  expect(playerCss).toContain('justify-content: center;');
});

test('responsive player layout does not re-enable vertical scrolling', () => {
  expect(responsiveCss).not.toContain('.view-player.active {\n        height: auto;');
  expect(responsiveCss).not.toContain('min-height: calc(100vh - 104px);\n        overflow: visible;');
  expect(responsiveCss).toContain('height: 100dvh;');
  expect(responsiveCss).toContain('max-height: 100dvh;');
  expect(responsiveCss).toContain('"board"');
});
