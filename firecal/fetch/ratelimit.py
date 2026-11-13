"""Token-bucket rate limiter for FIRMS transactions."""

import time


class RateLimiter:
    def __init__(self, budget, window, clock=time.time, sleeper=time.sleep):
        self.budget = budget
        self.window = window
        self.clock = clock
        self.sleeper = sleeper
        self._tokens = budget
        self._last = clock()

    def acquire(self, cost):
        now = self.clock()
        elapsed = now - self._last
        self._tokens = min(self.budget, self._tokens + (elapsed / self.window) * self.budget)
        self._last = now
        if cost > self._tokens:
            wait = (cost - self._tokens) * self.window / self.budget
            self.sleeper(wait)
            self._tokens = 0
            self._last = self.clock()
        else:
            self._tokens -= cost