/**
 * event_store.js - [State Layer] Persistent event storage for Replay & Time Travel.
 */

export const EventStore = {
    events: [],
    maxEvents: 5000,

    append(event) {
        const storedEvent = {
            ...event,
            receivedAt: Date.now()
        };

        this.events.push(storedEvent);

        // Retention policy
        if (this.events.length > this.maxEvents) {
            this.events.shift();
        }
    },

    getHistory() {
        return this.events;
    },

    clear() {
        this.events = [];
    }
};
