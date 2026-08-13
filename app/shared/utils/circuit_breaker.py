import time
from enum import Enum
from typing import Callable, Any, Coroutine
from functools import wraps
from app.infrastructure.logging.logger import get_logger

log = get_logger(__name__)


class CircuitState(Enum):
    CLOSED = "CLOSED"
    OPEN = "OPEN"
    HALF_OPEN = "HALF_OPEN"


class CircuitBreakerError(Exception):
    """Raised when attempting to execute a call while the circuit is OPEN."""
    pass


class CircuitBreaker:
    """
    Stateful circuit breaker pattern to prevent cascading failures
    when an external service (like an LLM provider) goes down or times out repeatedly.
    """
    def __init__(self, failure_threshold: int = 5, recovery_timeout: float = 60.0):
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.failures = 0
        self.state = CircuitState.CLOSED
        self.last_failure_time = 0.0

    def record_failure(self, error: Exception) -> None:
        self.failures += 1
        self.last_failure_time = time.time()
        log.warning("Circuit breaker recorded failure", error=str(error), failures=self.failures)
        if self.state == CircuitState.HALF_OPEN or self.failures >= self.failure_threshold:
            if self.state != CircuitState.OPEN:
                self.state = CircuitState.OPEN
                log.error("Circuit breaker OPENED. External service is down.", failures=self.failures)

    def record_success(self) -> None:
        if self.state == CircuitState.HALF_OPEN:
            log.info("Circuit breaker CLOSED (recovered). External service is back.")
        self.failures = 0
        self.state = CircuitState.CLOSED

    def check_state(self) -> None:
        if self.state == CircuitState.OPEN:
            if time.time() - self.last_failure_time >= self.recovery_timeout:
                self.state = CircuitState.HALF_OPEN
                log.info("Circuit breaker HALF_OPEN (testing recovery)")
            else:
                raise CircuitBreakerError("Circuit breaker is OPEN. Calls are blocked.")


# Global instance for LLM calls
llm_circuit_breaker = CircuitBreaker(failure_threshold=5, recovery_timeout=15.0)
