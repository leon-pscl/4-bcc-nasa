"""Token-bucket rate limiter with an injectable clock."""

import time


class RateLimiter:
    def __init__(self, budget: int, window_s: int, clock=time.time, sleeper=time.sleep):
        self.budget = budget
        self.window_s = window_s
        self.clock = clock
        self.sleeper = sleeper
        self.used = 0
        self.window_start = clock()

    def acquire(self, cost: int) -> None:
        now = self.clock()
        if now - self.window_start >= self.window_s:
            self.window_start = now
            self.used = 0
        if self.used + cost > self.budget:
            wait = self.window_start + self.window_s - now
            if wait > 0:
                self.sleeper(wait)
            self.window_start = self.clock()
            self.used = 0
        self.used += cost