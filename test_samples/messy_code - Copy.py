def process_numbers(numbers):
    if not isinstance(numbers, list) or not all(isinstance(number, int) for number in numbers):
        raise TypeError("Input must be a list of integers")

    result = []
    for number in numbers:
        if number > 0:
            if number % 2 == 0:
                result.append(number * 2)
            else:
                result.append(number * 3)
        else:
            if number == 0:
                result.append(0)
            else:
                result.append(number)
    return result
