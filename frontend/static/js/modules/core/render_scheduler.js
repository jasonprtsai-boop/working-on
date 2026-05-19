/**
 * render_scheduler.js - [Core Layer] Manages frame-synchronized rendering.
 * Prevents "render storms" by batching updates into requestAnimationFrame.
 */

export const RenderScheduler = {
    tasks: new Map(),
    isPending: false,

    /**
     * Schedule a render task.
     * @param {string} id - Unique ID for the task (e.g., 'board-render')
     * @param {Function} task - The actual rendering function.
     */
    schedule(id, task) {
        const key = String(id || `task-${this.tasks.size}`);
        this.tasks.set(key, task);

        if (!this.isPending) {
            this.isPending = true;
            requestAnimationFrame(() => this.flush());
        }
    },

    flush() {
        this.tasks.forEach(task => {
            try {
                task();
            } catch (e) {
                console.error("Render Scheduler Error:", e);
            }
        });

        this.tasks.clear();
        this.isPending = false;
    }
};
