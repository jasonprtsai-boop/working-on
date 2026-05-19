export function renderRobotStatus(robotState) {
    if (!robotState) return;

    const statusEl = document.getElementById('stat-robot');
    if (statusEl) {
        statusEl.innerText = robotState.busy ? '執行中' : (robotState.connected ? '待命中' : '離線');
        statusEl.className = robotState.connected ? (robotState.busy ? 'status-warning' : 'status-ok') : 'status-error';
    }

    const busyOverlay = document.getElementById('board-busy-overlay');
    if (busyOverlay) {
        if (robotState.busy) busyOverlay.classList.remove('hidden');
        else busyOverlay.classList.add('hidden');
    }
}
