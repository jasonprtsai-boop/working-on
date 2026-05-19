import { UIRegistry } from '../ui/ui_registry.js';
import { RenderScheduler } from '../core/render_scheduler.js';

export function renderEngineMetrics(engineState = {}) {
    RenderScheduler.schedule('engine-metrics', () => {
        const score = Number(engineState.score ?? 0);

        const evalFill = UIRegistry.get('evalBar');
        const scoreEl = UIRegistry.get('evalScore');
        if (evalFill && scoreEl) {
            scoreEl.innerText = (score / 100).toFixed(2);
            const percentage = Math.max(0, Math.min(100, 50 + (score / 40)));
            evalFill.style.height = `${percentage}%`;
        }

        const bestMoveEl = UIRegistry.get('bestMove');
        if (bestMoveEl) {
            bestMoveEl.innerText = engineState.best_move || '--';
        }

        renderPrincipalVariations(engineState);

        const thinkingContainer = UIRegistry.get('thinkingContainer');
        if (thinkingContainer) {
            thinkingContainer.classList.toggle('hidden', !engineState.is_thinking);
        }
    });
}

function renderPrincipalVariations(engineState) {
    const pvContainer = document.getElementById('multipv-container');
    if (!pvContainer) return;

    pvContainer.textContent = '';
    const lines = Array.isArray(engineState.multiPv) ? engineState.multiPv : [];
    if (!lines.length) {
        const empty = document.createElement('div');
        empty.className = 'pv-row empty';
        empty.textContent = 'No engine line yet.';
        pvContainer.appendChild(empty);
        return;
    }

    lines.forEach((pv, index) => {
        const pvScore = Number(pv.score ?? 0);
        const scoreDisplay = (pvScore / 100).toFixed(1);
        const winPct = Math.round(50 + 50 * Math.tanh(pvScore / 300));
        const row = document.createElement('div');
        row.className = 'pv-row';
        row.append(
            spanWithText('', String(index + 1)),
            spanWithText('pv-move', pv.move || pv.best_move || '--'),
            spanWithText('pv-score', `${pvScore > 0 ? '+' : ''}${scoreDisplay}`),
            spanWithText('pv-win', `${winPct}%`),
        );
        pvContainer.appendChild(row);
    });
}

function spanWithText(className, text) {
    const span = document.createElement('span');
    if (className) span.className = className;
    span.textContent = String(text ?? '');
    return span;
}
