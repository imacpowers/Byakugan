# app/utils.py
from collections import deque
import statistics

def moving_average(data_deque: deque):
    """Calculates the moving average of data in a deque."""
    # From cong_real.py
    if not data_deque:
        return 0
    return sum(data_deque) / len(data_deque)

# Add any other common utility functions here