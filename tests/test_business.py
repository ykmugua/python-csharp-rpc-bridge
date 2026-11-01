from runpy import run_path
from pathlib import Path

sample_module = run_path(str(Path(__file__).parent.parent / "modules" / "sample.py"))
SampleTextProcessor = sample_module["TextProcessor"]
add = sample_module["add"]
fixture = run_path(str(Path(__file__).parent / "fixtures" / "business.py"))


def test_add():
    assert add(2, 3) == 5
    assert add(-5, 5) == 0


def test_sample_text_processor_instances_keep_independent_state():
    french = SampleTextProcessor(lang="fr", verbose=True)
    german = SampleTextProcessor(lang="de", verbose=True)

    assert french.normalize("  hello   world ") == "[fr] hello world"
    assert german.normalize("  hello   world ") == "[de] hello world"
    assert french.get_calls() == 1
    assert german.get_calls() == 1


def test_fixture_summarize_normal_and_empty_boundary():
    summarize = fixture["summarize"]
    assert summarize([1, 2, 3]) == {"count": 3, "sum": 6.0, "mean": 2.0}
    assert summarize([]) == {"count": 0, "sum": 0.0, "mean": 0.0}


def test_fixture_text_processor_normal_and_boundary():
    processor_type = fixture["TextProcessor"]
    processor = processor_type(lang="zh")
    assert processor.get_calls() == 0
    assert processor.normalize("  hi   there ") == "hi there"
    assert processor.get_calls() == 1

    verbose = processor_type(lang="en", verbose=True)
    assert verbose.normalize("") == "[en] "
    assert verbose.get_calls() == 1
