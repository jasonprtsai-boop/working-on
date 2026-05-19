from backend.interfaces.engine_interface import EngineInterface
import random


class FakeEngine(EngineInterface):
    def get_move(self, state):
        # Minimal fake move payload compatible with the runtime contract.
        files = ['a','b','c','d','e','f','g','h','i']
        r1 = random.randint(0, 9)
        r2 = max(0, min(9, r1 + random.choice([-1, 1])))
        f = random.choice(files)
        return {'move': f'{f}{r1}{f}{r2}', 'score': 0, 'depth': 1, 'pv': []}
