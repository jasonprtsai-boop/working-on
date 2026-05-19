/**
 * board_mapper.js - [UI Utils] Translates grid coordinates to pixel/percent values.
 */
export const boardMapper = {
    gridToPercent(row, col) {
        // Red is at bottom for 'red' side
        return {
            x: (col * 11.11), // 9 cols
            y: (row * 10.0)    // 10 rows
        };
    },

    uciToGrid(uci) {
        if (!uci) return null;
        const col = uci.charCodeAt(0) - 97; // 'a'
        const row = 9 - parseInt(uci.substring(1));
        return { row, col };
    }
};
