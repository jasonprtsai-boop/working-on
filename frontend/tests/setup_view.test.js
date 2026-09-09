import { readFileSync } from 'node:fs';
import { resolve } from 'node:path';

const setupTemplate = readFileSync(
  resolve(process.cwd(), 'frontend/templates/components/setup_view.html'),
  'utf8'
);

function countText(needle) {
  return setupTemplate.split(needle).length - 1;
}

test('setup initialization panel exposes editable robot endpoint once', () => {
  expect(setupTemplate).toContain('id="setup-init-title"');
  expect(setupTemplate).toContain('id="btn-setup-lab-defaults"');
  expect(setupTemplate).toContain('id="btn-setup-init-test"');
  expect(setupTemplate).toContain('id="setup-init-endpoint"');
  expect(setupTemplate).toContain('id="setup-init-pc-network"');

  [
    'robot.connection.adapter',
    'robot.connection.ip',
    'robot.connection.port',
    'robot.connection.pc_ip',
    'robot.connection.subnet_mask',
    'robot.tmflow_json.wire_format',
  ].forEach((path) => {
    expect(countText(`data-setup-field="${path}"`)).toBe(1);
  });

  expect(countText('id="setup-live-hardware-test"')).toBe(1);
  expect(setupTemplate).toContain('id="setup-live-hardware-test" type="checkbox" data-setup-admin="true"');
  expect(setupTemplate).toContain('勾選實機執行後');
  expect(setupTemplate).toContain('遠離工作範圍');
});

test('setup camera panel exposes vision source switch controls once', () => {
  [
    'vision.source',
    'vision.camera_index',
    'vision.tmflow_json.host',
    'vision.tmflow_json.port',
    'vision.tmflow_json.timeout_sec',
    'vision.tmflow_json.max_message_bytes',
    'vision.tmflow_json.fps_limit',
  ].forEach((path) => {
    expect(countText(`data-setup-field="${path}"`)).toBe(1);
  });

  expect(countText('data-setup-vision-source="opencv"')).toBe(1);
  expect(countText('data-setup-vision-source="tmvision_http"')).toBe(1);
  expect(countText('data-setup-vision-source="tmflow_json"')).toBe(1);
  expect(countText('id="btn-setup-test-vision-source"')).toBe(1);
  expect(setupTemplate).toContain('id="setup-vision-source-status"');
  expect(setupTemplate).toContain('id="setup-vision-source-test-status"');
  expect(setupTemplate).toContain('id="setup-control-channel-status"');
  expect(setupTemplate).toContain('id="setup-vision-channel-status"');
  expect(setupTemplate).toContain('id="setup-vision-frame-age"');
  expect(setupTemplate).toContain('id="setup-vision-reconnects"');
});

test('setup view separates essential settings from live data', () => {
  expect(setupTemplate).toContain('data-setup-tab="essential"');
  expect(setupTemplate).toContain('data-setup-pane-target="essential"');
  expect(setupTemplate).toContain('data-setup-pane-target="live"');
  expect(setupTemplate).toContain('現場設定');
  expect(setupTemplate).toContain('工程模式');
  expect(setupTemplate).toContain('class="setup-section setup-section-essential"');
  expect(setupTemplate).toContain('class="setup-section setup-section-secondary"');
  expect(setupTemplate).toContain('class="setup-live-detail setup-channel-diagnostics"');
});

test('setup hardware tests keep common actions visible and advanced actions collapsed', () => {
  expect(setupTemplate).toContain('setup-field-tests-panel');
  expect(setupTemplate).toContain('class="setup-advanced-tests"');
  expect(setupTemplate).toContain('<summary>進階硬體測試</summary>');

  ['connect', 'status', 'safe_z', 'one_move'].forEach((action) => {
    expect(setupTemplate).toContain(`data-setup-test="${action}"`);
  });

  ['write_pose', 'corner_a0', 'corner_i9', 'grab_z', 'gripper_open', 'dead_zone'].forEach((action) => {
    expect(setupTemplate).toContain(`data-setup-test="${action}"`);
  });
});
