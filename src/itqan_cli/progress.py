"""Progress line drawn while `itqan install` downloads an asset.

Only drawn in a terminal: piped, redirected or CI output stays plain lines, with no `\\r` frames.
"""

from __future__ import annotations

from collections.abc import Callable
import os
import shutil
import sys
import time

import click

# The bar gets the room the numbers leave, between these widths, or is left out.
_BAR_MAX_WIDTH = 30
_BAR_MIN_WIDTH = 8
# Room kept for the rate ("999.9 KB/s") and ETA ("0:00:00"), so the bar keeps one width all along.
_RATE_WIDTH = 10
_ETA_WIDTH = 7
_SPINNER = "|/-\\"
# Redraw at most this often (seconds); downloads report every 64 KiB chunk.
_REDRAW_INTERVAL = 0.1


def enabled(no_progress: bool = False) -> bool:
    """Whether to draw progress: not with --no-progress, TERM=dumb, or when stdout isn't a terminal."""
    return not no_progress and os.environ.get("TERM") != "dumb" and _stdout_is_terminal()


def _stdout_is_terminal() -> bool:
    return sys.stdout.isatty()


class DownloadProgress:
    """A one-line progress display, redrawn in place, for one download.

    Pass it as `materialize_asset(on_progress=...)`. Call `clear()` once the download
    ends or fails, so the next line prints where the progress line was.
    """

    def __init__(
        self,
        label: str,
        *,
        write: Callable[[str], None] | None = None,
        clock: Callable[[], float] = time.monotonic,
        columns: Callable[[], int] | None = None,
    ) -> None:
        self.label = label
        self._write = write or (lambda text: click.echo(text, nl=False))
        self._clock = clock
        self._columns = columns or (lambda: shutil.get_terminal_size().columns)
        self._started: float | None = None
        self._last_draw: float | None = None
        self._drawn_width = 0
        self._frame = 0

    def __call__(self, done: int, total: int | None) -> None:
        now = self._clock()
        if self._started is None:
            self._started = now
        finished = total is not None and done >= total
        if self._last_draw is not None and now - self._last_draw < _REDRAW_INTERVAL and not finished:
            return
        self._last_draw = now
        self._draw(self.render(done, total, now - self._started))

    def render(self, done: int, total: int | None, elapsed: float) -> str:
        rate = done / elapsed if elapsed > 0 else 0.0
        speed = f"{format_bytes(rate)}/s" if rate else ""
        if total is None:
            self._frame += 1
            return _join(self.label, _SPINNER[self._frame % len(_SPINNER)], format_bytes(done), speed)
        fraction = min(done / total, 1.0) if total else 1.0
        eta = _format_eta((total - done) / rate) if rate and done < total else ""
        numbers = _join(_format_ratio(done, total), f"{int(fraction * 100):3d}%", speed, eta)
        widest = _join(_format_ratio(total, total), "100%", "x" * _RATE_WIDTH, "x" * _ETA_WIDTH)
        # Leave the last column free: some terminals wrap a line that fills the row.
        width = min(self._columns() - 1 - len(_join(self.label, "[]", widest)), _BAR_MAX_WIDTH)
        if width < _BAR_MIN_WIDTH:
            return _join(self.label, numbers)
        filled = int(fraction * width)
        bar = "=" * filled + (">" if filled < width else "") + " " * (width - filled - 1)
        return _join(self.label, f"[{bar}]", numbers)

    def clear(self) -> None:
        if self._drawn_width:
            self._write("\r" + " " * self._drawn_width + "\r")
            self._drawn_width = 0

    def _draw(self, line: str) -> None:
        # A line wider than the terminal wraps, and `\r` then only rewinds its last row.
        line = line[: max(self._columns() - 1, 0)]
        self._write("\r" + line.ljust(self._drawn_width))
        self._drawn_width = len(line)


def _join(*parts: str) -> str:
    return "  ".join(part for part in parts if part)


_UNITS = ("B", "KB", "MB", "GB", "TB")


def _unit(size: float) -> int:
    index = 0
    while size >= 1000 and index < len(_UNITS) - 1:
        size /= 1000
        index += 1
    return index


def format_bytes(size: float) -> str:
    """1234567 -> '1.2 MB' (decimal units, like download managers)."""
    index = _unit(size)
    if index == 0:
        return f"{int(size)} B"
    return f"{size / 1000**index:.1f} {_UNITS[index]}"


def _format_ratio(done: int, total: int) -> str:
    """Both sides in the total's unit: '45.3/120.0 MB'."""
    index = _unit(total)
    if index == 0:
        return f"{done}/{total} B"
    scale = 1000**index
    return f"{done / scale:.1f}/{total / scale:.1f} {_UNITS[index]}"


def _format_eta(seconds: float) -> str:
    seconds = int(seconds)
    return f"{seconds // 3600}:{seconds // 60 % 60:02d}:{seconds % 60:02d}"
