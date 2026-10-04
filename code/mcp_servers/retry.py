# Timeouts are set on each database call; this file adds a bounded exponential-backoff retry around it
import logging
import time
from dataclasses import dataclass
logger = logging.getLogger("league.retry")

class TransientError(Exception):
    """A failure that may go away if we try again (lost connection, timeout, injected fault)."""
class RetryExhausted(Exception):
    """Every allowed attempt failed."""
    def __init__(self, attempts: int, last_error: Exception):
        super().__init__(f"failed after {attempts} attempts: {last_error}")
        self.attempts = attempts
        self.last_error = last_error
@dataclass(frozen=True)
class RetryPolicy:
    max_attempts: int = 3  # first try plus 2 retries
    base_delay: float = 0.1  # seconds to wait before the first retry
    max_delay: float = 1.0  # the wait never grows past this
    def delay(self, attempt: int) -> float:
        """Wait after a failed attempt: 0.1s, 0.2s, 0.4s ... capped at max_delay."""
        return min(self.max_delay, self.base_delay * 2 ** (attempt - 1))
def retry_call(fn, policy: RetryPolicy, is_retryable, sleep=time.sleep):
    """Run fn; retry only retryable errors; return (result, attempts) or raise RetryExhausted."""
    for attempt in range(1, policy.max_attempts + 1):
        try:
            return fn(), attempt
        except Exception as exc:
            if not is_retryable(exc):
                raise  
            if attempt == policy.max_attempts:
                logger.error("attempt %d/%d failed: %s; giving up", attempt, policy.max_attempts, exc)
                raise RetryExhausted(attempt, exc) from exc
            wait = policy.delay(attempt)
            logger.warning("attempt %d/%d failed: %s; retrying in %.0f ms", attempt, policy.max_attempts, exc, wait * 1000)
            sleep(wait)