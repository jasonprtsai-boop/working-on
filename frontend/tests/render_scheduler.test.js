import { jest } from '@jest/globals';
import { RenderScheduler } from '../static/js/modules/core/render_scheduler.js';

beforeEach(() => {
  RenderScheduler.tasks.clear();
  RenderScheduler.isPending = false;
});

test('RenderScheduler deduplicates tasks by id before flushing', () => {
  const calls = [];
  const originalRaf = global.requestAnimationFrame;
  global.requestAnimationFrame = jest.fn();

  RenderScheduler.schedule('board-render', () => calls.push('old'));
  RenderScheduler.schedule('board-render', () => calls.push('new'));

  expect(RenderScheduler.tasks.size).toBe(1);
  RenderScheduler.flush();

  expect(calls).toEqual(['new']);
  global.requestAnimationFrame = originalRaf;
});
