from firecal.fetch.ratelimit import RateLimiter


def test_third_chunk_waits():
    slept = []
    clock_vals = [0.0]

    def clock():
        return clock_vals[0]

    def sleeper(s):
        slept.append(s)
        clock_vals[0] += s

    rl = RateLimiter(20, 10, clock=clock, sleeper=sleeper)
    rl.acquire(10)
    rl.acquire(10)
    rl.acquire(10)
    assert slept, "expected a wait"