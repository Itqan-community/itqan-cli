"""The progress line `itqan install` draws while downloading."""

import pytest

from itqan_cli import progress
from itqan_cli.progress import DownloadProgress, format_bytes


class _Clock:
    def __init__(self) -> None:
        self.now = 0.0

    def __call__(self) -> float:
        return self.now


def _bar(columns: int = 200) -> tuple[DownloadProgress, list[str], _Clock]:
    written: list[str] = []
    clock = _Clock()
    bar = DownloadProgress("(2/5) quran-hafs [1.2.0]", write=written.append, clock=clock, columns=lambda: columns)
    return bar, written, clock


def test_render_where_total_known_should_show_bytes_percent_rate_and_eta():
    # Arrange
    bar, _, _ = _bar()

    # Act
    line = bar.render(45_300_000, 120_000_000, elapsed=9.0)

    # Assert
    assert line == f"(2/5) quran-hafs [1.2.0]  [{'=' * 11}>{' ' * 18}]  45.3/120.0 MB   37%  5.0 MB/s  0:00:14"


def test_render_where_terminal_is_80_columns_should_shrink_the_bar_and_keep_the_numbers():
    # Arrange
    bar, _, _ = _bar(columns=80)

    # Act
    line = bar.render(45_300_000, 120_000_000, elapsed=9.0)

    # Assert
    assert line == "(2/5) quran-hafs [1.2.0]  [===>    ]  45.3/120.0 MB   37%  5.0 MB/s  0:00:14"


def test_render_should_keep_the_bar_one_width_from_start_to_finish():
    # Arrange
    bar, _, _ = _bar(columns=80)

    # Act
    lines = [
        bar.render(0, 120_000_000, elapsed=0.0),  # no rate or ETA yet
        bar.render(45_300_000, 120_000_000, elapsed=9.0),
        bar.render(120_000_000, 120_000_000, elapsed=24.0),  # no ETA
    ]

    # Assert
    assert {line.index("]  ", len(bar.label) + 2) for line in lines} == {35}


def test_render_where_no_room_for_a_bar_should_leave_it_out():
    # Arrange
    bar, _, _ = _bar(columns=60)
    bar.label = "(12/20) a-very-long-entry-name-for-an-asset [10.20.30]"

    # Act
    line = bar.render(45_300_000, 120_000_000, elapsed=9.0)

    # Assert
    assert line == f"{bar.label}  45.3/120.0 MB   37%  5.0 MB/s  0:00:14"


def test_render_where_total_unknown_should_show_spinner_and_byte_count():
    # Arrange
    bar, _, _ = _bar()

    # Act
    line = bar.render(2_500_000, None, elapsed=1.0)

    # Assert
    assert line == "(2/5) quran-hafs [1.2.0]  /  2.5 MB  2.5 MB/s"
    assert "%" not in line


def test_render_where_download_finished_should_show_a_full_bar_without_eta():
    # Arrange
    bar, _, _ = _bar()

    # Act
    line = bar.render(500, 500, elapsed=1.0)

    # Assert
    assert f"[{'=' * 30}]  500/500 B  100%  500 B/s" in line
    assert line.endswith("B/s")


def test_render_where_server_sends_more_than_its_content_length_should_cap_at_100_percent():
    # Arrange
    bar, _, _ = _bar()

    # Act
    line = bar.render(600, 500, elapsed=1.0)

    # Assert
    assert "100%" in line


def test_call_where_chunks_arrive_quickly_should_redraw_at_most_every_tenth_of_a_second():
    # Arrange
    bar, written, clock = _bar()

    # Act
    bar(0, 1000)
    clock.now = 0.05
    bar(100, 1000)  # too soon: skipped
    clock.now = 0.2
    bar(200, 1000)
    clock.now = 0.21
    bar(1000, 1000)  # the last chunk always draws

    # Assert
    assert len(written) == 3
    assert all(frame.startswith("\r") for frame in written)
    assert " 20%" in written[1]
    assert "100%" in written[2]


def test_call_where_line_wider_than_terminal_should_cut_it_to_fit():
    # Arrange
    bar, written, _ = _bar(columns=30)

    # Act
    bar(0, 1000)

    # Assert
    assert len(written[0]) == 1 + 29


def test_clear_should_blank_the_drawn_line_and_return_to_its_start():
    # Arrange
    bar, written, clock = _bar()
    bar(0, 1000)
    width = len(written[0]) - 1

    # Act
    bar.clear()

    # Assert
    assert written[-1] == "\r" + " " * width + "\r"


def test_clear_where_nothing_was_drawn_should_write_nothing():
    # Arrange
    bar, written, _ = _bar()

    # Act
    bar.clear()

    # Assert
    assert written == []


@pytest.mark.parametrize(
    ("size", "expected"),
    [(0, "0 B"), (999, "999 B"), (1000, "1.0 KB"), (1_234_567, "1.2 MB"), (5_000_000_000, "5.0 GB")],
)
def test_format_bytes(size: int, expected: str):
    assert format_bytes(size) == expected


@pytest.mark.parametrize(
    ("no_progress", "term", "terminal", "expected"),
    [
        (False, "xterm-256color", True, True),
        (False, "xterm-256color", False, False),
        (True, "xterm-256color", True, False),
        (False, "dumb", True, False),
    ],
    ids=["terminal", "piped", "no-progress flag", "dumb terminal"],
)
def test_enabled(monkeypatch, no_progress: bool, term: str, terminal: bool, expected: bool):
    # Arrange
    monkeypatch.setenv("TERM", term)
    monkeypatch.setattr(progress, progress._stdout_is_terminal.__name__, lambda: terminal)

    # Act / Assert
    assert progress.enabled(no_progress) is expected
