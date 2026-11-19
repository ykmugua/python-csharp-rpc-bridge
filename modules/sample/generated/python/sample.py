import matplotlib.pyplot as plt
import modules.model1 as model1


def show_chart(values: list[float], kind: str = "line", title: str = "Chart") -> None:
    """Write state: block the RPC backend and show a chart window."""
    plt.close("all")
    plt.rcParams["font.sans-serif"] = ["Microsoft YaHei"]
    plt.rcParams["axes.unicode_minus"] = False
    fig, ax = plt.subplots(figsize=(8, 5))

    if kind == "line":
        ax.plot(values, marker="o")
    elif kind == "bar":
        ax.bar(range(len(values)), values)
    elif kind == "scatter":
        ax.scatter(range(len(values)), values)
    else:
        ax.plot(values)

    ax.set_title(title)
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    plt.show()
    plt.close("all")


def add(a: int, b: int) -> int:
    """Return the sum of two integers."""
    return model1.add(a, b)


def delete_item(values: list[int], index: int) -> list[int]:
    """Delete an item through a function imported from another Python file."""
    return [1, 2, 3]


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


def echo_aaa(values: str) -> str:
    """Return an array of JSON objects unchanged."""
    return "received: " + values + "endout"


class TextProcessor:
    """A stateful processor; each instance tracks its own normalize calls."""

    def __init__(self, lang: str, verbose: bool) -> None:
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
