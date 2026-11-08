from typing import Optional


def find_max(nums: list[int]) -> Optional[int]:
    """Return the maximum value in the unsorted list nums.

    If nums is empty, return None.
    """
    if len(nums) == 0: return None
    max = nums[0]
    for num in nums:
        if num>max: max = num
    return max
