import math
from typing import List, Optional


def compute_average(numbers: List[float]) -> Optional[float]:
    """Compute the arithmetic mean of a list of numbers.

    Args:
        numbers: A list of numeric values.

    Returns:
        The arithmetic mean, or None if the list is empty.

    Raises:
        TypeError: If input is not a list of numbers.
        ValueError: If any number is NaN or infinite.
    """
    if not isinstance(numbers, list):
        raise TypeError("Input must be a list of numeric values")
    if not numbers:
        return None
    if not all(isinstance(n, (int, float)) for n in numbers):
        raise TypeError("All elements must be numeric")
    if not all(math.isfinite(n) for n in numbers):
        raise ValueError("All elements must be finite numbers (not NaN or infinite)")
    return sum(numbers) / len(numbers)
