def backoff_schedule(attempts: int, base: float, factor: float,
                     cap: float, max_elapsed: float) -> list[float]:
    # Validate inputs
    if not isinstance(attempts, int) or attempts < 0:
        raise ValueError("attempts must be a non-negative integer")
    if base < 0 or factor < 0 or cap < 0 or max_elapsed < 0:
        raise ValueError("base, factor, cap, and max_elapsed must be non-negative numbers")
    
    if attempts == 0:
        return []
    
    schedule = []
    cumulative = 0.0
    
    for i in range(attempts):
        # Calculate delay for attempt i
        delay = base * (factor ** i)
        # Clamp to cap
        delay = min(delay, cap)
        
        # Check if adding this delay would exceed max_elapsed
        if cumulative + delay > max_elapsed:
            # Truncate to remaining budget
            remaining = max_elapsed - cumulative
            if remaining > 0:
                schedule.append(round(remaining, 3))
            break
        
        schedule.append(round(delay, 3))
        cumulative += delay
    
    return schedule
