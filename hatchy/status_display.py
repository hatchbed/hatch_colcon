"""Live per-package status overlay for `hatchy build` and `hatchy test`.

Owns the `StatusDisplay` class (which consumes lines of colcon output and
maintains a scrolling overlay of in-flight packages plus a summary line) and
the `_run_with_status` driver loop that pumps a colcon subprocess into the
display.  Two thin public wrappers — `run_build_with_status` and
`run_test_with_status` — configure the display for each command.

Stderr highlighting is delegated to the `highlighters` module.
"""

import locale
import os
import queue
import re
import select
import shutil
import signal
import subprocess
import sys
import termios
import threading
import time
import tty
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Tuple

from .common import (
    clr, supports_ansi, _strip_ansi, _fmt_duration,
    _GREEN, _YELLOW, _RED, _BOLD_RED, _BOLD_GREEN,
    _CYAN, _BRIGHT_BLUE, _BRIGHT_MAGENTA, _DIM, _BOLD,
)
from .highlighters import highlight_stderr

# ---- tunables ----------------------------------------------------------------
# Cap on left-padding for completed-package names so very long names don't blow
# out the terminal width.
_MAX_NAME_WIDTH = 40
# Tail of the colcon stdout.log read on each render to extract progress.
_TAIL_READ_BYTES = 32768
# Sleep between overlay renders.  Lower = smoother spinner, higher CPU.
_RENDER_INTERVAL_S = 0.1
# Minimum interval between renice calls on the colcon process tree.
_RENICE_INTERVAL_S = 1.0
# Window after a SIGWINCH during which we re-check overlay position on VTE.
_VTE_REPOSITION_WINDOW_S = 2.0

# VTE-based terminals (Tilix, GNOME Terminal) reflow content on resize regardless
# of DECAWM, causing the overlay to drift above the terminal bottom.  Detect via
# the env-var that VTE always exports so we know when to apply the CPR fix.
_IS_VTE = bool(os.environ.get('VTE_VERSION'))

_SPIN_FRAMES = ('⠴', '⠦', '⠖', '⠲') \
    if 'utf' in locale.getpreferredencoding(False).lower() \
    else ('/', '-', '\\', '|')

# CTest stderr boilerplate lines that indicate failures but carry no actionable
# details.  Their presence is used to flip a pending [ OK ] to [ FAIL ]; the
# lines themselves are suppressed from the displayed stderr block.
_CTEST_BOILERPLATE = (
    'Errors while running CTest',
    'Output from these tests are in:',
    '--rerun-failed --output-on-failure',
)

# Lines that mark a colcon-level boundary outside any per-package output.  Used
# to confirm a deferred stderr-block close (bare `---`) is really a delimiter
# rather than incidental content.
_COLCON_BOUNDARY_RE = re.compile(
    r'^(?:Starting\s+>>>|Finished\s+<<<|Failed\s+<<<|Aborted\s+<<<|Summary:|\[\s*OK\s*\]|WARNING:)'
)


def _is_ctest_boilerplate(line: str) -> bool:
    stripped = line.strip()
    return any(p in stripped for p in _CTEST_BOILERPLATE)


def _is_colcon_boundary(line: str) -> bool:
    return bool(_COLCON_BOUNDARY_RE.match(line))


def _read_tail(path: str, nbytes: int = _TAIL_READ_BYTES) -> str:
    try:
        with open(path, 'rb') as f:
            f.seek(0, 2)
            size = f.tell()
            f.seek(max(0, size - nbytes))
            return f.read().decode('utf-8', errors='replace')
    except OSError:
        return ''


def _truncate_desc(desc: str, max_len: int) -> str:
    """Truncate a build description to max_len visible characters.

    For descriptions with a path component (e.g. 'Building CXX object src/foo.cc.o'),
    keeps the action prefix and truncates the beginning of the path so the filename
    is always visible: 'Building CXX object .../foo.cc.o'.
    Falls back to truncating from the start for non-path descriptions.
    """
    if len(desc) <= max_len or max_len <= 3:
        return desc

    words = desc.split(' ')
    for i, word in enumerate(words):
        if i > 0 and '/' in word:
            action = ' '.join(words[:i])
            path = desc[len(action) + 1:]
            remaining = max_len - len(action) - 4  # 4 for ' ...'
            if remaining > 4:
                return f"{action} ...{path[-remaining:]}"
            break

    return '...' + desc[-(max_len - 3):]


# CTest stdout.log parser patterns.  Compiled at module load so the hot path
# in _parse_test_progress doesn't recompile per-line.  The per-test patterns
# capture the leading test index as a group rather than hard-coding it, so a
# single compiled regex covers any test number.
_CTEST_RESULT_RE = re.compile(r'^(\d+)/(\d+)\s+Test\s+#\d+:')
_CTEST_START_RE = re.compile(r'^\s*Start\s+(\d+):\s+(.+)$')
_GTEST_RUN_RE = re.compile(r'^(\d+):\s*\[\s*RUN\s*\]\s+(.+)$')
_GTEST_END_RE = re.compile(r'^(\d+):\s*\[\s*(?:OK|FAILED)\s*\]')
_PYUNIT_START_RE = re.compile(r'^(\d+):\s+(\w+)\s+\([^)]+\)\s+\.\.\.')
_PYUNIT_END_RE = re.compile(r'^(\d+):\s+(?:ok|FAIL(?:ED)?|ERROR|Ran\s+\d+)')


def _parse_test_progress(log_path: Optional[str]) -> Optional[Tuple[int, str]]:
    """Return (percent, description) from a CTest stdout.log.

    CTest writes verbose output with each line prefixed by the test index
    (e.g. '1: [ RUN      ] Suite.TestCase') so we can extract the active
    gtest case from the same file without reading any secondary log.
    """
    if not log_path:
        return None
    tail = _strip_ansi(_read_tail(log_path))
    completed = 0
    total = None
    current_test: Optional[str] = None
    current_test_num: Optional[int] = None
    current_case: Optional[str] = None

    for line in tail.splitlines():
        stripped = line.strip()

        # Result: "3/10 Test #3: test_name .......... Passed  0.01 sec"
        m = _CTEST_RESULT_RE.match(stripped)
        if m:
            completed = int(m.group(1))
            total = int(m.group(2))
            current_test = None
            current_test_num = None
            current_case = None
            continue

        # Start: "    Start 4: test_name"  (leading whitespace in CTest output)
        m = _CTEST_START_RE.match(line)
        if m:
            current_test_num = int(m.group(1))
            current_test = m.group(2).strip()
            current_case = None
            continue

        # Per-test verbose output: "4: [ RUN      ] Suite.TestCase"  (gtest)
        # or "4: test_name (module.Class.test_name) ..."  (Python unittest /
        # launch_test).  Only honor patterns whose leading index matches the
        # currently-running test number — other indices are output from
        # already-completed tests still being flushed by ctest.
        if current_test_num is not None:
            m = _GTEST_RUN_RE.match(stripped)
            if m and int(m.group(1)) == current_test_num:
                current_case = m.group(2).strip()
                continue
            m = _GTEST_END_RE.match(stripped)
            if m and int(m.group(1)) == current_test_num:
                current_case = None
                continue
            m = _PYUNIT_START_RE.match(stripped)
            if m and int(m.group(1)) == current_test_num:
                current_case = m.group(2).strip()
                continue
            m = _PYUNIT_END_RE.match(stripped)
            if m and int(m.group(1)) == current_test_num:
                current_case = None

    if total is None and current_test is None:
        return None
    pct = int(100 * completed / total) if total else 0
    if current_test is not None:
        desc = f"{current_test}: {current_case}" if current_case else current_test
    else:
        desc = f"{completed}/{total}" if total else "starting..."
    return pct, desc


def _parse_progress(log_path: Optional[str]) -> Optional[Tuple[int, str]]:
    """Return (percent, description) from the most recent build progress line."""
    if not log_path:
        return None
    tail = _strip_ansi(_read_tail(log_path))
    for line in reversed(tail.splitlines()):
        line = line.strip()
        # cmake/make: [67%] Building CXX object src/foo.cc.o
        m = re.match(r'^\[\s*(\d+)%\]\s+(.*)', line)
        if m:
            return int(m.group(1)), m.group(2).strip()
        # ninja: [67/100] ...
        m = re.match(r'^\[(\d+)/(\d+)\]\s+(.*)', line)
        if m:
            a, b = int(m.group(1)), int(m.group(2))
            pct = int(100 * a / b) if b else 0
            desc = m.group(3).strip()
            # With VERBOSE=1, ninja shows full compiler commands; extract source file.
            src = re.search(r'(?:^|\s)-c\s+(\S+)', desc)
            if src:
                desc = f"Compiling {os.path.basename(src.group(1))}"
            return pct, desc
    return None


def _infer_phase(last_progress: Optional[Tuple[int, str]]) -> str:
    if last_progress is None:
        return 'cmake'
    dl = last_progress[1].lower()
    if 'install' in dl:
        return 'install'
    if 'link' in dl:
        return 'link'
    return 'build'


@dataclass
class _PkgState:
    name: str
    start: float
    log_path: str
    end: Optional[float] = None
    ok: Optional[bool] = None
    aborted: bool = False
    stderr: List[str] = field(default_factory=list)
    last_progress: Optional[Tuple[int, str]] = None


class StatusDisplay:
    """
    Live per-package status overlay used by both build and test commands.

    Completed packages are printed once into scroll history. In-progress
    packages are shown in a redrawn overlay: one line per package with
    cmake/ninja progress from the colcon log files, plus a compact summary
    line at the bottom.
    """

    def __init__(self, workspace: str, total: Optional[int] = None,
                 log_subdir: str = 'latest_build',
                 progress_fn=None,
                 show_build_summary: bool = True,
                 pkg_names: Optional[List[str]] = None,
                 phase: Optional[str] = None):
        self._log_base = os.path.join(workspace, 'log', log_subdir)
        self._progress_fn = progress_fn or _parse_progress
        self._show_build_summary = show_build_summary
        self._build_start = time.monotonic()
        self._building: Dict[str, _PkgState] = {}
        self._done: List[_PkgState] = []
        self._stderr_pkg: Optional[str] = None
        self._in_stderr = False
        self._in_summary = False
        self._pending_stderr_close = False
        self._live_lines = 0
        self._live_strs: List[str] = []
        self._live_cols: int = 0
        # Cached terminal size from the most recent render(), reused by
        # reposition_to_bottom so a single render cycle only makes one syscall.
        self._cached_size: Optional[os.terminal_size] = None
        self._winch_time: float = 0.0
        self._prev_winch = None
        self._tty = supports_ansi()
        if self._tty:
            try:
                self._prev_winch = signal.signal(
                    signal.SIGWINCH,
                    lambda s, f: setattr(self, '_winch_time', time.monotonic()))
            except (OSError, ValueError):
                pass
        self._total = total
        self._fixed_phase = phase
        self._status_offset = 0
        self._interrupted = False
        self._pending_state: Optional[_PkgState] = None
        self._ctest_error_pkgs: set = set()
        self._spin_idx: int = 0
        self._name_width = (
            min(max((len(n) for n in pkg_names), default=0), _MAX_NAME_WIDTH)
            if pkg_names else 0
        )

    def process_line(self, raw: str) -> None:
        line = _strip_ansi(raw).rstrip()

        # Resolve a pending stderr-close from the previous bare-`---` line.
        # The block only closes if this line is a colcon boundary; otherwise
        # the `---` was incidental content and we keep collecting.
        if self._pending_stderr_close:
            self._pending_stderr_close = False
            if _is_colcon_boundary(line):
                self._commit_stderr_close()
                # fall through to process the boundary line
            else:
                self._append_stderr_line('---')
                # fall through; _in_stderr is still True so the line continues
                # to be collected as stderr content below

        # Suppress colcon's summary block — we print our own in finalize()
        if self._in_summary:
            return
        if re.match(r'^Summary:', line):
            self._in_summary = True
            return

        # If a completion is buffered, flush it now unless this line is the
        # stderr block header for that same package (which we still need to
        # inspect for CTest errors before committing the result).
        if self._pending_state is not None and not self._in_stderr:
            m_check = re.match(r'^---\s+stderr:\s+(.+?)\s*(?:---\s*)?$', line)
            if not (m_check and m_check.group(1).strip() == self._pending_state.name):
                self._flush_pending()

        # Package started
        m = re.match(r'^Starting\s+>>>\s+(.+)$', line)
        if m:
            pkg = m.group(1).strip()
            self._building[pkg] = _PkgState(
                name=pkg,
                start=time.monotonic(),
                log_path=os.path.join(self._log_base, pkg, 'stdout.log'),
            )
            return

        # Package finished
        for pat, ok, aborted in (
            (r'^Finished\s+<<<\s+(.+?)\s+\[.+\]$', True, False),
            (r'^\[\s*OK\s*\]\s+(.+?)\s+\(.+\)$', True, False),
            (r'^Failed\s+<<<\s+(.+?)\s+\[.+\]$', False, False),
            (r'^Aborted\s+<<<\s+(.+?)\s+\[.+\]$', False, True),
        ):
            m = re.match(pat, line)
            if m:
                pkg = m.group(1).strip()
                state = self._building.pop(pkg, _PkgState(pkg, time.monotonic(), ''))
                state.end = time.monotonic()
                state.ok = ok
                state.aborted = aborted
                self._done.append(state)
                if ok:
                    if pkg in self._ctest_error_pkgs:
                        # CTest already reported errors via a preceding stderr block.
                        state.ok = False
                        self._ctest_error_pkgs.discard(pkg)
                        self._flush_completed(state)
                    else:
                        # Buffer — a following stderr block may contain CTest errors.
                        self._pending_state = state
                else:
                    self._ctest_error_pkgs.discard(pkg)
                    self._flush_completed(state)
                return

        # Stderr block start — strip optional trailing ' ---' from the header
        # (colcon formats it as '--- stderr: PKG ---')
        m = re.match(r'^---\s+stderr:\s+(.+?)\s*(?:---\s*)?$', line)
        if m:
            self._stderr_pkg = m.group(1).strip()
            self._in_stderr = True
            return

        # Stderr block end — defer until the next line confirms it's a real
        # delimiter (i.e. followed by a colcon boundary).  This keeps a bare
        # `---` that appears inside content from prematurely closing the block.
        if line == '---' and self._in_stderr:
            self._pending_stderr_close = True
            return

        # Collect stderr lines
        if self._in_stderr and self._stderr_pkg:
            if _is_ctest_boilerplate(line):
                # Suppress CTest boilerplate; its presence means tests failed.
                # Works whether stderr arrives before or after Finished <<<.
                self._ctest_error_pkgs.add(self._stderr_pkg)
            else:
                self._append_stderr_line(line)
            return

        # Warning lines from colcon/CMake — color yellow
        if line.startswith('WARNING:'):
            self._erase_live()
            print(clr(line, _YELLOW), flush=True)
            return

        # Unknown lines — pass through for forward compatibility
        if line:
            self._erase_live()
            print(line, flush=True)

    def _append_stderr_line(self, line: str) -> None:
        """Append a line to the active stderr block (no-op if no block is open)."""
        if not self._stderr_pkg:
            return
        target = self._building.get(self._stderr_pkg) or next(
            (s for s in self._done if s.name == self._stderr_pkg), None)
        if target is not None:
            target.stderr.append(line)

    def _commit_stderr_close(self) -> None:
        """Close the current stderr block and print its highlighted contents."""
        self._in_stderr = False
        pkg_name = self._stderr_pkg
        self._stderr_pkg = None
        if not pkg_name:
            return
        # If this closes a buffered completion, flush it now (possibly as
        # [ FAIL ] if CTest boilerplate was detected) so the result line
        # appears before the stderr output.
        if self._pending_state is not None and pkg_name == self._pending_state.name:
            self._flush_pending()
        state = self._building.get(pkg_name) or next(
            (s for s in self._done if s.name == pkg_name), None)
        if state and state.stderr:
            is_error = (state.ok is False) or (state.name in self._ctest_error_pkgs)
            color = _RED if is_error else _YELLOW
            self._erase_live()
            print(f"\n{clr(f'--- stderr: {state.name} ---', color)}")
            for ln in highlight_stderr(state.stderr):
                print(f"  {ln}")
            print(clr('---', color))
            state.stderr = []  # clear so finalize() doesn't double-print

    def _build_overlay_lines(self, cols: int, spin: str = ' ') -> List[str]:
        """Build the list of overlay lines without any terminal I/O."""
        lines: List[str] = []

        for pkg, state in sorted(self._building.items()):
            elapsed = _fmt_duration(time.monotonic() - state.start)
            prog = self._progress_fn(state.log_path)
            if prog:
                state.last_progress = prog
            tag = clr(f'[run{spin}]', _CYAN)
            phase_str = self._fixed_phase or _infer_phase(state.last_progress)
            phase = f':{clr(phase_str, _BRIGHT_MAGENTA)}'
            if state.last_progress:
                pct, desc = state.last_progress
                visible_prefix = f"[run{spin}] {pkg}:{phase_str} ({elapsed}) [{pct}%] "
                max_desc = cols - len(visible_prefix) - 1
                desc = _truncate_desc(desc, max_desc)
                lines.append(f"{tag} {pkg}{phase} ({clr(elapsed, _BRIGHT_BLUE)}) [{clr(f'{pct}%', _BRIGHT_MAGENTA)}] {clr(desc, _DIM)}")
            else:
                lines.append(f"{tag} {pkg}{phase} ({clr(elapsed, _BRIGHT_BLUE)})")

        total_elapsed = _fmt_duration(time.monotonic() - self._build_start)
        n_done = len(self._done)
        n_total = self._total if self._total is not None else n_done + len(self._building)

        all_parts = []
        for pkg, state in sorted(self._building.items()):
            elapsed = _fmt_duration(time.monotonic() - state.start)
            if state.last_progress:
                pct, _ = state.last_progress
                all_parts.append(f"[{pkg} {clr(f'{pct}%', _BRIGHT_MAGENTA)} - {clr(elapsed, _BRIGHT_BLUE)}]")
            else:
                all_parts.append(f"[{pkg} - {clr(elapsed, _BRIGHT_BLUE)}]")

        self._status_offset = max(0, min(self._status_offset, max(0, len(all_parts) - 1)))
        offset = self._status_offset
        left_ind = f"{clr('<', _BOLD)} " if offset > 0 else ""
        header = f"[{clr(total_elapsed, _BRIGHT_BLUE)}] [{clr(str(n_done), _BOLD_GREEN)}/{clr(str(n_total), _GREEN)} done] {left_ind}"

        budget = cols - len(_strip_ansi(header)) - 2  # reserve 2 for ' >'
        kept = []
        for part in all_parts[offset:]:
            needed = len(_strip_ansi(part)) + (1 if kept else 0)
            if budget >= needed:
                kept.append(part)
                budget -= needed
            else:
                break

        has_right = (offset + len(kept)) < len(all_parts)
        right_ind = f" {clr('>', _BOLD)}" if has_right else ""
        lines.append(header + " ".join(kept) + right_ind)
        return lines

    @staticmethod
    def _phys_lines(lines: List[str], cols: int) -> int:
        """Physical terminal rows occupied by lines at a given column width."""
        return sum(max(1, (len(_strip_ansi(l)) + cols - 1) // cols) for l in lines)

    def render(self) -> None:
        """Redraw the live overlay."""
        if not self._tty:
            return
        if not self._building:
            self._erase_live()
            return

        self._cached_size = shutil.get_terminal_size((80, 24))
        cols = self._cached_size.columns
        # Advance the spinner only when we're actually about to draw a frame,
        # so the animation doesn't skip while the overlay is hidden.
        self._spin_idx = (self._spin_idx + 1) % len(_SPIN_FRAMES)
        new_lines = self._build_overlay_lines(cols, _SPIN_FRAMES[self._spin_idx])

        buf: List[str] = []
        if self._live_lines > 0:
            # Use min(live_cols, current_cols) so that if the terminal was
            # narrowed since the last render, wrapped lines are counted correctly.
            erase_cols = min(self._live_cols, cols) if self._live_cols else cols
            n_phys = self._phys_lines(self._live_strs, erase_cols)
            buf.append(f'\033[{n_phys}A\033[J')

        for line in new_lines:
            buf.append(f'{line}\n')

        sys.stdout.write(''.join(buf))
        sys.stdout.flush()
        self._live_lines = len(new_lines)
        self._live_strs = new_lines
        self._live_cols = cols

    def reposition_to_bottom(self, cursor_row: int) -> None:
        """If the overlay drifted above the terminal bottom, snap it back.

        After the trailing-newline render, the cursor lands N rows below the
        overlay start (cursor_row = overlay_start + N).  The safe target for
        the overlay start is rows-N-1, which writes N lines ending at rows-2
        with the cursor at rows-1 — consistent with how a normal render behaves
        when the terminal is full and the last newline causes a single scroll.
        """
        if not self._tty or self._live_lines == 0 or self._cached_size is None:
            return
        rows = self._cached_size.lines
        cols = self._cached_size.columns
        N = self._live_lines
        overlay_start = cursor_row - N
        desired_start = max(0, rows - N - 1)
        if overlay_start < 0 or overlay_start >= desired_start:
            return

        new_lines = self._build_overlay_lines(cols, _SPIN_FRAMES[self._spin_idx])

        buf = [
            f'\033[{overlay_start + 1};1H',  # CUP to current overlay start (1-indexed)
            '\033[J',                          # erase from here to end of screen
            f'\033[{desired_start + 1};1H',   # CUP to desired overlay start
        ]
        for line in new_lines:
            buf.append(f'{line}\n')

        sys.stdout.write(''.join(buf))
        sys.stdout.flush()
        self._live_strs = new_lines
        self._live_cols = cols
        # _live_lines stays N; cursor is now at rows-1 (col 0)

    def finalize(self) -> None:
        if self._prev_winch is not None:
            try:
                signal.signal(signal.SIGWINCH, self._prev_winch)
            except (OSError, ValueError):
                pass
            self._prev_winch = None
        # Resolve any unresolved deferred close (input ended right after `---`).
        if self._pending_stderr_close:
            self._pending_stderr_close = False
            self._commit_stderr_close()
        self._flush_pending()
        self._erase_live()

        # Any packages still in-progress at interrupt time become aborted.
        if self._interrupted:
            now = time.monotonic()
            for state in sorted(self._building.values(), key=lambda s: s.name):
                state.end = now
                state.ok = False
                state.aborted = True
                self._done.append(state)
            self._building.clear()

        # Show stderr for any packages whose blocks weren't flushed inline.
        for state in self._done:
            if state.stderr:
                color = _RED if not state.ok else _YELLOW
                print(f"\n{clr(f'--- stderr: {state.name} ---', color)}")
                for ln in highlight_stderr(state.stderr):
                    print(f"  {ln}")
                print(clr('---', color))

        if not self._show_build_summary:
            return

        # Summary
        n_ok = sum(1 for s in self._done if s.ok)
        n_fail = sum(1 for s in self._done if not s.ok and not s.aborted)
        n_abrt = sum(1 for s in self._done if s.aborted)
        total = len(self._done)
        failed_names = [s.name for s in self._done if not s.ok and not s.aborted]
        aborted_names = [s.name for s in self._done if s.aborted]
        warn_names = [s.name for s in self._done if s.ok and s.stderr]

        elapsed = f"({clr(_fmt_duration(time.monotonic() - self._build_start), _BRIGHT_BLUE)})"
        print()
        if self._interrupted:
            n_total = self._total or total
            print(f"{clr('Build interrupted', _YELLOW)}: "
                  f"{n_ok} of {n_total} package{'s' if n_total != 1 else ''} completed. {elapsed}")
            if aborted_names:
                print(f"  {clr('Aborted', _YELLOW)}: {', '.join(aborted_names)}")
            if failed_names:
                print(f"  {clr('Failed', _RED)}: {', '.join(failed_names)}")
        elif n_fail == 0 and n_abrt == 0:
            print(f"{clr('Build complete', _GREEN)}: "
                  f"{total} package{'s' if total != 1 else ''} built successfully. {elapsed}")
        else:
            print(f"{clr('Build failed', _RED)}: "
                  f"{n_ok} of {total} package{'s' if total != 1 else ''} succeeded. {elapsed}")
            if failed_names:
                print(f"  {clr('Failed', _RED)}: {', '.join(failed_names)}")
            if aborted_names:
                print(f"  {clr('Aborted', _YELLOW)}: {', '.join(aborted_names)}")
        if warn_names:
            print(f"  {clr('Warnings', _YELLOW)}: {', '.join(warn_names)}")
        print()

    def scroll_status(self, direction: int) -> None:
        """Shift the status bar view left (-1) or right (+1)."""
        self._status_offset = max(0, self._status_offset + direction)

    def _flush_pending(self) -> None:
        """Flush a buffered completion, applying CTest-detected failure if needed."""
        if self._pending_state is not None:
            if self._pending_state.name in self._ctest_error_pkgs:
                self._pending_state.ok = False
                self._ctest_error_pkgs.discard(self._pending_state.name)
            self._flush_completed(self._pending_state)
            self._pending_state = None

    def _flush_completed(self, state: _PkgState) -> None:
        """Print a completed-package line into scroll history."""
        self._erase_live()
        dur = f"({clr(_fmt_duration((state.end or time.monotonic()) - state.start), _BRIGHT_BLUE)})"
        name = state.name.ljust(self._name_width) if self._name_width else state.name
        if state.ok:
            print(f"{clr('[ ok ]', _GREEN)} {name} {dur}", flush=True)
        elif state.aborted:
            print(f"{clr('[ABRT]', _YELLOW)} {name} {dur}", flush=True)
        else:
            print(f"{clr('[FAIL]', _BOLD_RED)} {name} {dur}", flush=True)

    def _erase_live(self) -> None:
        if not self._tty or self._live_lines == 0:
            return
        cols = min(self._live_cols, shutil.get_terminal_size((80, 24)).columns) \
            if self._live_cols else shutil.get_terminal_size((80, 24)).columns
        n_phys = self._phys_lines(self._live_strs, cols)
        sys.stdout.write(f'\033[{n_phys}A\033[J')
        sys.stdout.flush()
        self._live_lines = 0
        self._live_strs = []
        self._live_cols = 0


class _KeyWatcher:
    """Non-blocking key reader in cbreak mode. Returns 'LEFT', 'RIGHT', or a char."""

    def __enter__(self):
        self._fd = None
        self._saved = None
        self._buf = b''
        if sys.stdin.isatty():
            self._fd = sys.stdin.fileno()
            self._saved = termios.tcgetattr(self._fd)
            tty.setcbreak(self._fd)
        return self

    def __exit__(self, *_):
        if self._saved is not None:
            termios.tcsetattr(self._fd, termios.TCSADRAIN, self._saved)

    def read(self) -> Optional[str]:
        if self._fd is None:
            return None
        # Drain all newly available bytes into the buffer.
        if select.select([self._fd], [], [], 0)[0]:
            self._buf += os.read(self._fd, 32)
        if not self._buf:
            return None
        # Complete arrow-key escape sequence: ESC [ C/D
        if len(self._buf) >= 3 and self._buf[0] == 0x1b and self._buf[1] == ord('['):
            key = {ord('C'): 'RIGHT', ord('D'): 'LEFT'}.get(self._buf[2])
            if key:
                self._buf = self._buf[3:]
                return key
        # Partial escape sequence — wait briefly for the rest.
        if self._buf[0] == 0x1b and len(self._buf) < 3:
            if select.select([self._fd], [], [], 0.05)[0]:
                self._buf += os.read(self._fd, 32)
                if len(self._buf) >= 3 and self._buf[1] == ord('['):
                    key = {ord('C'): 'RIGHT', ord('D'): 'LEFT'}.get(self._buf[2])
                    if key:
                        self._buf = self._buf[3:]
                        return key
            self._buf = self._buf[1:]
            return None
        # Printable ASCII character.
        ch = self._buf[0]
        self._buf = self._buf[1:]
        return chr(ch) if ch >= 32 else None

    def query_cursor_row(self) -> Optional[int]:
        """Send a CPR request and return the 0-based cursor row, or None.

        Any bytes that arrive before/after the CPR response are kept in the
        internal buffer so they are not lost for subsequent read() calls.
        """
        if self._fd is None:
            return None
        sys.stdout.write('\033[6n')
        sys.stdout.flush()
        deadline = time.monotonic() + 0.1
        while time.monotonic() < deadline:
            remaining = max(0.0, deadline - time.monotonic())
            if select.select([self._fd], [], [], remaining)[0]:
                self._buf += os.read(self._fd, 32)
            m = re.search(rb'\033\[(\d+);(\d+)R', self._buf)
            if m:
                row = int(m.group(1)) - 1  # convert to 0-based
                self._buf = self._buf[:m.start()] + self._buf[m.end():]
                return row
        return None


def _run_with_status(process, nice: int, display: StatusDisplay) -> int:
    """Drive a colcon subprocess with the given live display.

    Returns the process exit code (1 on KeyboardInterrupt).
    """
    q: queue.Queue = queue.Queue()

    def _reader():
        try:
            for raw in iter(process.stdout.readline, b''):
                q.put(raw.decode('utf-8', errors='replace').rstrip('\n'))
        finally:
            q.put(None)

    threading.Thread(target=_reader, daemon=True).start()

    last_nice = 0.0
    done = False
    using_ansi = supports_ansi()

    if using_ansi:
        sys.stdout.write('\033[?25l\033[?7l')  # hide cursor, disable line wrap
        sys.stdout.flush()

    try:
        with _KeyWatcher() as keys:
            while not done:
                while True:
                    try:
                        line = q.get_nowait()
                    except queue.Empty:
                        break
                    if line is None:
                        done = True
                        break
                    display.process_line(line)

                key = keys.read()
                if key in ('RIGHT', 'd'):
                    display.scroll_status(1)
                elif key in ('LEFT', 'a'):
                    display.scroll_status(-1)

                if not done:
                    display.render()
                    # On VTE, if a resize recently occurred, query the actual
                    # cursor position and snap the overlay back to the terminal
                    # bottom if it drifted upward due to VTE's reflow behavior.
                    if _IS_VTE and (time.monotonic() - display._winch_time < _VTE_REPOSITION_WINDOW_S):
                        row = keys.query_cursor_row()
                        if row is not None:
                            display.reposition_to_bottom(row)

                now = time.monotonic()
                if now - last_nice >= _RENICE_INTERVAL_S and nice != 0:
                    subprocess.run(
                        f"renice -n {nice} -p "
                        f"$(pgrep -g $(ps -o pgid= -p {process.pid}))",
                        shell=True, executable='/bin/bash',
                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                    last_nice = now

                if not done:
                    time.sleep(_RENDER_INTERVAL_S)
    except KeyboardInterrupt:
        process.terminate()
        try:
            process.wait(timeout=5)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait()
        # Drain any final output the reader thread already queued.
        while True:
            try:
                line = q.get_nowait()
            except queue.Empty:
                break
            if line is None:
                break
            display.process_line(line)
        display._interrupted = True
        display.finalize()
        return 1
    finally:
        if using_ansi:
            sys.stdout.write('\033[?7h\033[?25h')  # re-enable line wrap, show cursor
            sys.stdout.flush()

    process.wait()  # normal exit path
    display.finalize()
    return process.returncode


def run_build_with_status(process, workspace: str, nice: int, total: Optional[int] = None,
                          pkg_names: Optional[List[str]] = None) -> int:
    """Drive a colcon build subprocess with a live per-package status display."""
    display = StatusDisplay(workspace, total=total, pkg_names=pkg_names)
    return _run_with_status(process, nice, display)


def run_test_with_status(process, workspace: str, nice: int, total: Optional[int] = None,
                         pkg_names: Optional[List[str]] = None) -> int:
    """Drive a colcon test subprocess with a live per-package status display.

    Returns the process exit code.  The caller is responsible for running
    print_test_results() afterward to show the per-test breakdown.
    """
    display = StatusDisplay(
        workspace, total=total,
        log_subdir='latest_test',
        progress_fn=_parse_test_progress,
        show_build_summary=False,
        pkg_names=pkg_names,
        phase='test',
    )
    return _run_with_status(process, nice, display)
