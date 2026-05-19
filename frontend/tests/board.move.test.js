import { jest } from '@jest/globals';
import { BoardRenderer } from '../static/js/modules/board/board_renderer.js';
import { installFakeDom, setupContainer } from './test_dom.js';

test('moving piece reuses same DOM element when id is stable', () => {
  installFakeDom();

  const pieces = setupContainer('board-capture-pieces');
  const renderer = new BoardRenderer('board-capture-pieces');
  const oldPieces = [{ id: 'red-rook-1', type: 'R', pos: 'a0' }];
  const newPieces = [{ id: 'red-rook-1', type: 'R', pos: 'a1' }];

  renderer.render([], oldPieces);
  const before = Array.from(pieces.querySelectorAll('.piece'));
  expect(before.length).toBe(1);
  const pieceEl = before[0];

  renderer.render(oldPieces, newPieces);
  const after = pieces.querySelectorAll('.piece');
  expect(after.length).toBe(1);
  expect(after[0]).toBe(pieceEl);
  expect(after[0].style.top).toBe(`${(8 / 9) * 100}%`);
});

test('captured pieces get captured class before removal', () => {
  installFakeDom();

  const pieces = setupContainer('board-pieces');
  const renderer = new BoardRenderer('board-pieces');
  const oldPieces = [
    { id: 'red-rook-1', type: 'R', pos: 'a0' },
    { id: 'red-pawn-1', type: 'P', pos: 'i0' },
  ];
  const newPieces = [{ id: 'red-rook-1', type: 'R', pos: 'a0' }];

  renderer.render([], oldPieces);
  expect(pieces.querySelectorAll('.piece').length).toBe(2);

  jest.useFakeTimers();
  renderer.render(oldPieces, newPieces);
  jest.advanceTimersByTime(16);

  const allPieces = pieces.querySelectorAll('.piece');
  expect(allPieces.length).toBe(2);

  const captured = Array.from(allPieces).find((piece) => piece.classList.contains('captured'));
  expect(captured).toBeTruthy();

  jest.advanceTimersByTime(600);
  expect(pieces.querySelectorAll('.piece').length).toBe(1);
  jest.useRealTimers();
});

test('counter-based backend ids keep stationary same-type pieces stable', () => {
  installFakeDom();

  const pieces = setupContainer('board-stable-pieces');
  const renderer = new BoardRenderer('board-stable-pieces');
  const oldPieces = [
    { id: 'R-1', type: 'R', pos: 'a0' },
    { id: 'R-2', type: 'R', pos: 'i0' },
  ];
  const newPieces = [
    { id: 'R-1', type: 'R', pos: 'a9' },
    { id: 'R-2', type: 'R', pos: 'a0' },
  ];

  renderer.render([], oldPieces);
  const before = Array.from(pieces.querySelectorAll('.piece'));
  const stationary = before.find((piece) => piece.id === 'ui-R-1');
  const moving = before.find((piece) => piece.id === 'ui-R-2');

  renderer.render(oldPieces, newPieces);

  expect(pieces.querySelectorAll('.piece').length).toBe(2);
  expect(stationary.style.top).toBe('100%');
  expect(moving.style.top).toBe('0%');
});
