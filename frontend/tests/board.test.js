// board.test.js - Tests for the canonical modular BoardRenderer.

import { BoardRenderer, isValidBoardPos } from '../static/js/modules/board/board_renderer.js';
import { RenderScheduler } from '../static/js/modules/core/render_scheduler.js';

const FILES = 'abcdefghi';

beforeEach(() => {
  RenderScheduler.tasks.clear();
  RenderScheduler.isPending = false;
  document.body.innerHTML = '';
  global.requestAnimationFrame = (callback) => callback();
});

function piecesFromFen(fen) {
  const boardPart = String(fen || '').split(/\s+/)[0] || '';
  const rows = boardPart.split('/');
  const pieces = [];

  rows.forEach((row, rowIndex) => {
    let col = 0;
    for (const char of row) {
      if (/\d/.test(char)) {
        col += Number(char);
        continue;
      }
      const rank = 9 - rowIndex;
      const pos = `${FILES[col]}${rank}`;
      pieces.push({ id: `${char}-${pos}`, type: char, pos });
      col += 1;
    }
  });

  return pieces;
}

test('render full start position shows 32 pieces', () => {
  document.body.innerHTML = '<div id="test-board-pieces"></div>';
  const piecesContainer = document.getElementById('test-board-pieces');
  const renderer = new BoardRenderer('test-board-pieces');

  const startFen = 'rnbakabnr/9/1c5c1/p1p1p1p1p/9/9/P1P1P1P1P/1C5C1/9/RNBAKABNR w - - 0 1';
  renderer.render([], piecesFromFen(startFen));

  const pieces = piecesContainer.querySelectorAll('.piece');
  expect(pieces.length).toBe(32);
  expect(Array.from(pieces).some((piece) => piece.id === 'ui-R-a0')).toBe(true);
});

test('renderer skips invalid piece coordinates instead of writing NaN positions', () => {
  document.body.innerHTML = '<div id="test-board-pieces"></div>';
  const piecesContainer = document.getElementById('test-board-pieces');
  const renderer = new BoardRenderer('test-board-pieces');

  renderer.render([], [
    { id: 'valid', type: 'R', pos: 'a0' },
    { id: 'bad-file', type: 'R', pos: 'z9' },
    { id: 'bad-rank', type: 'R', pos: 'a10' },
  ]);
  RenderScheduler.flush();
  const pieces = piecesContainer.querySelectorAll('.piece');
  expect(pieces.length).toBe(1);
  expect(isValidBoardPos('a0')).toBe(true);
  expect(isValidBoardPos('z9')).toBe(false);
  expect(isValidBoardPos('a10')).toBe(false);
  expect(pieces[0].style.left).not.toContain('NaN');
});
