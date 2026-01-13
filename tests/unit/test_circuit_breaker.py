from mailq.infrastructure.circuitbreaker import InvalidJSONCircuitBreaker


def test_circuit_breaker_trips_at_threshold():
    breaker = InvalidJSONCircuitBreaker(window=10, threshold=0.2)
    # record 2 invalid, 8 valid -> 0.2
    for _ in range(2):
        breaker.record(False)
    for _ in range(8):
        breaker.record(True)
    assert breaker.invalid_rate() == 0.2
    assert breaker.is_tripped()
