import re
from typing import List, Callable, Any

"""
Unified Sorting Manager

This module provides a single entry point for sorting lists with different modes:
  - 'Natural Order (Numbers as Numbers)'
  - 'Lexicographical Order (Numbers as Characters)'
  - 'Date Added'

All list sorting across the application should use this function. For experiments,
custom sorting options (e.g., 'mouse', 'plugin', 'date') are handled in state_manager.get_sorted_list.
"""

def natural_key(text: str) -> List[Any]:
    """
    Splits the input text into a list of integers and lowercase strings for natural sorting.
    For example, 'item12' becomes ['item', 12, ''].
    """
    return [int(c) if c.isdigit() else c.lower() for c in re.split(r'([0-9]+)', text)]


def sort_items(
    items: List[Any],
    sort_mode: str,
    key_func: Callable[[Any], Any] = None
) -> List[Any]:
    """Unified sorting function with optional custom key_func.
    This function uses the provided global sort mode to determine how to sort the items.
    If no key_func is provided, it attempts to use the item's 'date_added' if available, or 'name' if available,
    falling back to the string representation.
    """
    if not key_func:
        if items and hasattr(items[0], 'date_added'):
            key_func = lambda x: x.date_added
        elif items and hasattr(items[0], 'name'):
            key_func = lambda x: x.name.lower()
        else:
            key_func = lambda x: str(x)

    if sort_mode == "Natural Order (Numbers as Numbers)":
        return sorted(items, key=lambda x: natural_key(str(key_func(x))))
    elif sort_mode == "Lexicographical Order (Numbers as Characters)":
        return sorted(items, key=lambda x: str(key_func(x)).lower())
    elif sort_mode == "Date Added":
        # Sort by the raw value of key_func(x); often a datetime or numeric value
        return sorted(items, key=key_func)
    else:
        # fallback to default sort by key_func
        return sorted(items, key=key_func)
