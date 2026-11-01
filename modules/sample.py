def add(a: int, b: int) -> int:
    """Return the sum of two integers."""
    return a + b


class TextProcessor:
    """A stateful processor; each instance tracks its own normalize calls."""

    def __init__(self, lang: str = "en", verbose: bool = False) -> None:
        self.lang = lang
        self.verbose = verbose
        self.calls = 0

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
