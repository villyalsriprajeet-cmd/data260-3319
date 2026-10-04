# Seeded fault injection: decides before each storage call whether it fails, so the same seed gives the same pattern
import random
from retry import TransientError
VERIFY_SEED = 263319
class FaultInjector:
    """Makes a share of storage calls fail on purpose, reproducibly."""
    def __init__(self, rate: float = 0.0, seed: int = VERIFY_SEED, plan: list[bool] | None = None):
        self.rate = rate  # chance that one attempt fails 
        self.rng = random.Random(seed)  # own generator, so nothing else changes the sequence
        self.plan = list(plan or [])  # fixed outcomes for the demo, used before the random ones
        self.history: list[bool] = []  
    def __call__(self) -> None:
        fail = self.plan.pop(0) if self.plan else self.rng.random() < self.rate
        self.history.append(fail)
        if fail:
            raise TransientError("injected failure (simulated lost database connection)")