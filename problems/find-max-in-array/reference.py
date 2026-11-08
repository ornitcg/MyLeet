from typing import Optional


def find_max(nums: list[int]) -> Optional[int]:
    if not nums:
        return None
    best = nums[0]
    for x in nums[1:]:
        if x > best:
            best = x
    return best
