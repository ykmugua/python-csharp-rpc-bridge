from shared.deletion import remove_at


def add(a: int, b: int) -> int:
    """Return the sum of two integers."""
    return a + b


def delete_item(values: list[int], index: int) -> list[int]:
    """Delete an item through a function imported from another Python file."""
    return remove_at(values, index)


def echo_floats(values: list[float]) -> list[float]:
    """Return a float array unchanged."""
    return values


def echo_strings(values: list[str]) -> list[str]:
    """Return a string array unchanged."""
    return values


def echo_bools(values: list[bool]) -> list[bool]:
    """Return a boolean array unchanged."""
    return values


def echo_records(values: list[dict[str, int]]) -> list[dict[str, int]]:
    """Return an array of JSON objects unchanged."""
    return values


class TextProcessor:
    """A stateful processor; each instance tracks its own normalize calls."""

    def __init__(self, lang: str = "en", verbose: bool = False) -> None:
        self.lang: str = lang
        self.verbose: bool = verbose
        self.calls: int = 0

    def normalize(self, text: str) -> str:
        """Write state by incrementing calls, then normalize whitespace."""
        self.calls += 1
        result = " ".join(text.strip().split())
        if self.verbose:
            result = f"[{self.lang}] {result}"
        return result

    def get_calls(self) -> int:
        """Read state by returning the number of normalize calls."""
        return self.calls
