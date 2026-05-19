export const syncState = {
    lastReceivedAt: 0,
    stale: true,
    timeline: {
        vision: { duration: 0 },
        engine: { duration: 0 },
        robot: { duration: 0 }
    }
};

export function updateSyncState(payload) {
    if (payload.lastReceivedAt) {
        syncState.lastReceivedAt = payload.lastReceivedAt;
    }
    if (typeof payload.stale === 'boolean') {
        syncState.stale = payload.stale;
    }
    if (payload.timeline) {
        syncState.timeline = payload.timeline;
    }
}
