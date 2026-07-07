/**
 * Canonical UI board coordinate helpers.
 *
 * Grid coordinates use row 0 at the top and col 0 at file "a".
 * UCCI coordinates use file/rank such as "a0".
 */
const FILES = 'abcdefghi';

export const boardMapper = {
    gridToPercent(row, col) {
        const r = Number(row);
        const c = Number(col);
        if (!Number.isFinite(r) || !Number.isFinite(c) || r < 0 || r > 9 || c < 0 || c > 8) {
            return null;
        }
        return {
            x: (c / 8) * 100,
            y: (r / 9) * 100,
        };
    },

    uciToGrid(uci) {
        if (!isValidUciSquare(uci)) return null;
        const col = FILES.indexOf(String(uci)[0]);
        const row = 9 - Number(String(uci).slice(1));
        return { row, col };
    },

    gridToUci(row, col) {
        const r = Number(row);
        const c = Number(col);
        if (!Number.isInteger(r) || !Number.isInteger(c) || r < 0 || r > 9 || c < 0 || c > 8) {
            return null;
        }
        return `${FILES[c]}${9 - r}`;
    },

    moveToGrid(move) {
        const text = String(move || '');
        if (!/^[a-i][0-9][a-i][0-9]$/.test(text)) return null;
        return {
            from: this.uciToGrid(text.slice(0, 2)),
            to: this.uciToGrid(text.slice(2, 4)),
        };
    },
};

export function isValidUciSquare(uci) {
    return /^[a-i][0-9]$/.test(String(uci || ''));
}
