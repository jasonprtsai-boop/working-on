import collections

class MotionQueue:
    """[Robot Service] Managed queue for pending robotic movements."""
    def __init__(self):
        self.queue = collections.deque()
        self.is_busy = False

    def add_commands(self, commands):
        self.queue.extend(commands)

    def next_command(self):
        if self.queue:
            return self.queue.popleft()
        return None

    def clear(self):
        self.queue.clear()
        self.is_busy = False
