import { RenderScheduler } from '../core/render_scheduler.js';

const PIECE_MAP = {
    R: '車', N: '馬', B: '相', A: '仕', K: '帥', C: '炮', P: '兵',
    r: '車', n: '馬', b: '象', a: '士', k: '將', c: '砲', p: '卒',
};

export class BoardRenderer {
    constructor(containerId) {
        this.containerId = containerId;
        this.container = globalThis.document?.getElementById(containerId);
        this.pieceElements = new Map();
        this.renderAliases = new Map();
    }

    render(oldPieces, newPieces) {
        if (!this.container) return;

        RenderScheduler.schedule(`board-${this.containerId}`, () => {
            const cleanOldPieces = (oldPieces || []).filter(isRenderablePiece);
            const cleanNewPieces = (newPieces || []).filter(isRenderablePiece);
            const reconciledPieces = this.reconcilePieces(cleanOldPieces, cleanNewPieces);
            const nextRenderIds = new Set(reconciledPieces.map(p => p.renderId));

            Array.from(this.pieceElements.keys()).forEach((id) => {
                if (!nextRenderIds.has(id)) this.removePiece(id);
            });

            reconciledPieces.forEach((piece) => {
                const el = this.pieceElements.get(piece.renderId);
                if (!el) this.addPiece(piece);
                else this.updatePiece(el, piece);
            });
        });
    }

    reconcilePieces(oldPieces, newPieces) {
        const oldByType = groupByType(oldPieces);
        const nextAliases = new Map();
        const reconciled = [];

        for (const [type, candidates] of groupByType(newPieces)) {
            const availableOld = [...(oldByType.get(type) || [])];
            const assigned = new Set();

            candidates.forEach((piece) => {
                const exactIndex = availableOld.findIndex(old => old.pos === piece.pos && !assigned.has(old));
                if (exactIndex >= 0) {
                    const old = availableOld[exactIndex];
                    assigned.add(old);
                    reconciled.push(this.withRenderId(piece, old));
                }
            });

            candidates.forEach((piece) => {
                const sourceId = String(piece.id || `${piece.type}-${piece.pos}`);
                if (reconciled.some(item => item.sourceId === sourceId)) return;

                let best = null;
                let bestDistance = Number.POSITIVE_INFINITY;
                availableOld.forEach((old) => {
                    if (assigned.has(old)) return;
                    const distance = positionDistance(old.pos, piece.pos);
                    if (distance < bestDistance) {
                        bestDistance = distance;
                        best = old;
                    }
                });

                if (best) assigned.add(best);
                reconciled.push(this.withRenderId(piece, best));
            });
        }

        reconciled.forEach((piece) => nextAliases.set(piece.sourceId, piece.renderId));
        this.renderAliases = nextAliases;
        return reconciled;
    }

    withRenderId(piece, oldPiece) {
        const sourceId = String(piece.id || `${piece.type}-${piece.pos}`);
        const oldId = oldPiece?.id ? String(oldPiece.id) : null;
        const renderId = oldId
            ? (this.renderAliases.get(oldId) || oldId)
            : (this.renderAliases.get(sourceId) || sourceId);

        return { ...piece, sourceId, renderId };
    }

    addPiece(piece) {
        const el = document.createElement('div');
        el.className = `piece ${piece.type === piece.type.toUpperCase() ? 'red' : 'black'}`;
        const label = document.createElement('span');
        label.textContent = PIECE_MAP[piece.type] || piece.type;
        el.appendChild(label);
        el.id = `ui-${piece.renderId}`;
        this.container.appendChild(el);
        this.pieceElements.set(piece.renderId, el);
        this.updatePosition(el, piece.pos, true);
    }

    removePiece(id) {
        const el = this.pieceElements.get(id);
        if (el) {
            el.classList.add('captured');
            setTimeout(() => {
                el.remove();
                this.pieceElements.delete(id);
            }, 500);
        }
    }

    updatePiece(el, piece) {
        el.className = `piece ${piece.type === piece.type.toUpperCase() ? 'red' : 'black'}`;
        const span = el.querySelector?.('span');
        const label = PIECE_MAP[piece.type] || piece.type;
        if (span && span.textContent !== label) span.textContent = label;
        this.updatePosition(el, piece.pos, false);
    }

    updatePosition(el, pos, immediate) {
        if (!isValidBoardPos(pos)) return;
        const col = pos.charCodeAt(0) - 97;
        const row = 9 - parseInt(pos[1], 10);
        el.style.transition = immediate ? 'none' : 'all 0.4s cubic-bezier(0.2, 0, 0, 1)';
        el.style.left = `${(col / 8) * 100}%`;
        el.style.top = `${(row / 9) * 100}%`;
    }
}

export function isValidBoardPos(pos) {
    return /^[a-i][0-9]$/.test(String(pos || ''));
}

function isRenderablePiece(piece) {
    return Boolean(piece) && typeof piece.type === 'string' && piece.type && isValidBoardPos(piece.pos);
}

function groupByType(pieces) {
    const groups = new Map();
    pieces.forEach((piece) => {
        const type = String(piece.type || '');
        if (!groups.has(type)) groups.set(type, []);
        groups.get(type).push(piece);
    });
    return groups;
}

function positionDistance(a, b) {
    if (!isValidBoardPos(a) || !isValidBoardPos(b)) return Number.POSITIVE_INFINITY;
    const ax = a.charCodeAt(0) - 97;
    const ay = Number(a.slice(1));
    const bx = b.charCodeAt(0) - 97;
    const by = Number(b.slice(1));
    if (![ax, ay, bx, by].every(Number.isFinite)) return Number.POSITIVE_INFINITY;
    return Math.abs(ax - bx) + Math.abs(ay - by);
}
