from typing import List, Optional

def compute_average(numbers: List[float]) -> Optional[float]:
    """Compute the arithmetic mean of a list of numbers.

    Args:
        numbers: A list of numeric values.

    Returns:
        The arithmetic mean, or None if the list is empty.

    Raises:
        TypeError: If any element is not a number.
    """
    if not numbers:
        return None
    if not all(isinstance(n, (int, float)) for n in numbers):
        raise TypeError("All elements must be numeric")
    return sum(numbers) / len(numbers)
