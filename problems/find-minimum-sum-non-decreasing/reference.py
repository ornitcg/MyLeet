def find_minimum_sum(power: list[int]) -> int:
    total = 0
    for i in range(1, len(power)):
        if power[i] < power[i - 1]:
            total += power[i - 1] - power[i]
    return total
