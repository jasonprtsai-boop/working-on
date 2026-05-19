/**
 * subscriptions.js - [State Layer] Reactive subscription management.
 */

const subscribers = {
    board: [],
    engine: [],
    robot: [],
    vision: [],
    sync: [],
    ui: [],
    events: [], // For the event timeline
    notation: []
};

export const Subscriptions = {
    subscribe(domain, callback) {
        if (subscribers[domain]) {
            subscribers[domain].push(callback);
            return () => {
                const idx = subscribers[domain].indexOf(callback);
                if (idx >= 0) subscribers[domain].splice(idx, 1);
            };
        } else {
            console.warn(`Attempted to subscribe to unknown domain: ${domain}`);
        }
        return () => {};
    },

    notify(domain, data) {
        if (subscribers[domain]) {
            [...subscribers[domain]].forEach(callback => {
                try {
                    callback(data);
                } catch (e) {
                    console.error(`Error in subscriber for domain ${domain}:`, e);
                }
            });
        }
    }
};
