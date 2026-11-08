def longest_even_subarray(nums: list[int]) -> int:
    best = 0
    cur = 0
    for x in nums:
        if x % 2 == 0:
            cur += 1
            if cur > best:
                best = cur
        else:
            cur = 0
    return best
