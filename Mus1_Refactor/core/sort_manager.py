import re
from typing import List, Callable, Any


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
    """Unified sorting function with optional custom key_func."""
    if not key_func:
        # If no key_func is provided, compare items by converting them to strings
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
