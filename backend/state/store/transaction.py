from backend.state.store.legacy_models import GameState

class StateTransaction:
    """
    [Safety Boundary] Manages atomic state transitions.
    Ensures that complex pipeline operations either fully succeed or roll back.
    """
    def __init__(self, old_state: GameState):
        self.old_state = old_state
        self.new_state = None
        self.committed = False

    def set_new_state(self, new_state: GameState):
        self.new_state = new_state

    def commit(self):
        if self.new_state is None:
            raise Exception("State transaction commit failed: new_state is missing.")
        self.committed = True
        return self.new_state

    def rollback(self):
        """Reverts the transition by returning the original state."""
        self.new_state = self.old_state
        self.committed = False
        return self.old_state
