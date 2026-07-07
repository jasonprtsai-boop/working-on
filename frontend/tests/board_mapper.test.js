import { boardMapper, isValidUciSquare } from '../static/js/modules/board/board_mapper.js';

test('grid coordinates map to stable board percentages', () => {
  expect(boardMapper.gridToPercent(0, 0)).toEqual({ x: 0, y: 0 });
  expect(boardMapper.gridToPercent(9, 8)).toEqual({ x: 100, y: 100 });

  const middle = boardMapper.gridToPercent(4.5, 4);
  expect(middle.x).toBe(50);
  expect(middle.y).toBe(50);
  expect(boardMapper.gridToPercent(10, 0)).toBeNull();
});

test('UCCI squares convert to and from UI grid coordinates', () => {
  expect(boardMapper.uciToGrid('a0')).toEqual({ row: 9, col: 0 });
  expect(boardMapper.uciToGrid('i9')).toEqual({ row: 0, col: 8 });
  expect(boardMapper.gridToUci(9, 0)).toBe('a0');
  expect(boardMapper.gridToUci(0, 8)).toBe('i9');
  expect(boardMapper.gridToUci(1.5, 2)).toBeNull();
  expect(isValidUciSquare('a0')).toBe(true);
  expect(isValidUciSquare('a10')).toBe(false);
});

test('UCCI moves convert into from/to grid endpoints', () => {
  expect(boardMapper.moveToGrid('b2b5')).toEqual({
    from: { row: 7, col: 1 },
    to: { row: 4, col: 1 },
  });
  expect(boardMapper.moveToGrid('zzzz')).toBeNull();
});
