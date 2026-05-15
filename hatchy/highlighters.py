"""Syntax-highlighting helpers for colcon stderr blocks.

The public entry point is `highlight_stderr(lines)`, which classifies each line
of an stderr block as gcc / cmake / python and dispatches to the appropriate
per-line highlighter.  Used by the live status display to colorize the stderr
section printed after each package's completion line.
"""

import re
from typing import List, Optional

from .common import (
    clr, supports_ansi,
    _DIM, _GREEN, _YELLOW, _RED, _CYAN, _BOLD, _BOLD_RED, _BRIGHT_BLUE,
)

# Python traceback highlighting is delegated to pygments when available.
_pyg_highlight = _pytb_lexer = _term_fmt = None
try:
    from pygments import highlight as _pyg_highlight
    from pygments.formatters import Terminal256Formatter as _TermFmt
    from pygments.lexers.python import PythonTracebackLexer as _PyTbLexer
    _term_fmt = _TermFmt(style='native')
    _pytb_lexer = _PyTbLexer()
except Exception:
    pass


def _highlight_gcc_line(line: str) -> str:
    """Colorize a single GCC/Clang diagnostic line."""
    # Inclusion chain — dim as noise
    if re.match(r'^(?:In file included from|\s+from\s+/)', line):
        return clr(line, _DIM)

    # Source context with line number: "  123 | code"
    m = re.match(r'^(\s*)(\d+)(\s*\|)(.*)', line)
    if m:
        indent, lineno, bar, rest = m.group(1), m.group(2), m.group(3), m.group(4)
        stripped = rest.strip()
        if stripped and all(c in '^~ ' for c in stripped):
            return clr(indent + lineno, _DIM) + bar + clr(rest, _GREEN)
        return clr(indent, _DIM) + clr(lineno, _BRIGHT_BLUE) + bar + rest

    # Caret-only bar line with no line number: "      |  ^~~~~"
    m = re.match(r'^(\s*\|)(.*)', line)
    if m:
        bar, rest = m.group(1), m.group(2)
        stripped = rest.strip()
        if stripped and all(c in '^~ ' for c in stripped):
            return bar + clr(rest, _GREEN)
        return bar + rest

    # Diagnostic: "/path:NN:MM: (error|warning|note): message"
    m = re.match(r'^(.*?):(\d+:\d+:)(\s*)(error|warning|note)(:.*)$', line, re.IGNORECASE)
    if m:
        path, linecol, sp, sev, rest = m.group(1), m.group(2), m.group(3), m.group(4), m.group(5)
        sev_l = sev.lower()
        if sev_l == 'error':
            return clr(path + ':', _DIM) + clr(linecol, _BRIGHT_BLUE) + sp + clr(sev + rest, _BOLD_RED)
        if sev_l == 'warning':
            return clr(path + ':', _DIM) + clr(linecol, _BRIGHT_BLUE) + sp + clr(sev, _YELLOW) + rest
        return clr(path + ':', _DIM) + clr(linecol, _BRIGHT_BLUE) + sp + clr(sev, _CYAN) + rest  # note

    # Context header: "/path: In function 'X':" etc.
    if re.match(r'^.*?:\s+In ', line):
        return clr(line, _DIM)

    # make/ninja summary lines
    if re.match(r'^g?make(?:\[\d+\])?:', line):
        return clr(line, _RED if ('Error' in line or '***' in line) else _DIM)

    return line


# Patterns used both inside the cmake inline regex and as fullmatch checks
# against the contents of quoted strings.  Sharing one source keeps the
# coloring rules in lockstep when patterns evolve.
_CMAKE_PATH_PATTERN = r'/[^\s,;\'"()]+|[\w.+-]+\.(?:cmake|txt|py|cpp|c|h|hpp)'
_CMAKE_VAR_PATTERN = r'[A-Z][A-Z0-9_]{2,}|[A-Za-z][a-zA-Z0-9]*_[A-Z][A-Z0-9_]+'
_CMAKE_PATH_RE = re.compile(_CMAKE_PATH_PATTERN)
_CMAKE_VAR_RE = re.compile(_CMAKE_VAR_PATTERN)


def _make_cmake_inline_re(pkg_names=None) -> re.Pattern:
    pkg_pattern = ''
    if pkg_names:
        alts = '|'.join(re.escape(n) for n in sorted(pkg_names, key=len, reverse=True))
        pkg_pattern = rf'|(?P<pkg>\b(?:{alts})\b)'
    return re.compile(
        r'(?P<str>"(?:[^"\\]|\\.)*")'
        rf'|(?P<path>{_CMAKE_PATH_PATTERN})'
        rf'|(?P<var>{_CMAKE_VAR_PATTERN})'
        r'|(?P<num>\b\d+(?:\.\d+)*\b)'
        + pkg_pattern
    )


def _highlight_cmake_body(line: str, inline_re: re.Pattern, pkg_names: set) -> str:
    def _replace(m):
        if m.group('str') is not None:
            inner = m.group('str')[1:-1]
            if inner in pkg_names:
                return clr(m.group('str'), _GREEN)
            if _CMAKE_PATH_RE.fullmatch(inner):
                return clr(m.group('str'), _BOLD)
            if _CMAKE_VAR_RE.fullmatch(inner):
                return clr(m.group('str'), _CYAN)
            return clr(m.group('str'), _YELLOW)
        if m.group('path') is not None:
            return clr(m.group('path'), _BOLD)
        if m.group('var') is not None:
            return clr(m.group('var'), _CYAN)
        if m.group('num') is not None:
            return clr(m.group('num'), _GREEN)
        pkg = m.groupdict().get('pkg')
        if pkg is not None:
            return clr(pkg, _GREEN)
        return m.group(0)
    return inline_re.sub(_replace, line)


def _highlight_cmake_line(line: str, inline_re: re.Pattern, pkg_names: set) -> str:
    m = re.match(r'^(CMake )((?:Deprecation )?(?:Error|Warning))(?: \(dev\))? at (.*?):(\d+) \((.*?)\):\s*$', line)
    if m:
        prefix, sev, path, lineno, cmd = m.group(1), m.group(2), m.group(3), m.group(4), m.group(5)
        sev_color = _BOLD_RED if 'Error' in sev else _YELLOW
        return ('CMake ' + clr(sev, sev_color) +
                ' at ' + clr(path, _BOLD) + ':' + clr(lineno, _BRIGHT_BLUE) +
                f' ({cmd}):')
    m = re.match(r'^(\s*\*\* )(WARNING|ERROR)( \*\*)(.*)', line)
    if m:
        prefix, sev, stars, rest = m.group(1), m.group(2), m.group(3), m.group(4)
        color = _BOLD_RED if sev == 'ERROR' else _YELLOW
        return prefix + clr(sev, color) + stars + _highlight_cmake_body(rest, inline_re, pkg_names)
    if re.match(r'^g?make(?:\[\d+\])?:', line):
        return _highlight_gcc_line(line)
    return _highlight_cmake_body(line, inline_re, pkg_names)


def _highlight_cmake_block(lines: List[str]) -> List[str]:
    pkg_names = set()
    for line in lines:
        m = re.search(r'\bFind(\w+)\.cmake\b', line)
        if m:
            pkg_names.add(m.group(1))
        m = re.search(r'\b(\w+)Config\.cmake\b', line)
        if m:
            pkg_names.add(m.group(1))
    inline_re = _make_cmake_inline_re(pkg_names or None)
    return [_highlight_cmake_line(l, inline_re, pkg_names) for l in lines]


def highlight_stderr(lines: List[str]) -> List[str]:
    """Segment stderr by output type and highlight each segment independently.

    Lines are classified as cmake / python / gcc via anchor patterns; unanchored
    lines inherit the previous classification.  Each contiguous run is then
    dispatched to its dedicated highlighter so a mixed cmake+gcc+python error
    block colors each section appropriately.
    """
    if not supports_ansi():
        return lines

    # Classify each line: definitive anchors set the mode, None inherits.
    forced: List[Optional[str]] = []
    for line in lines:
        stripped = line.strip()
        if re.match(r'^CMake (?:(?:Deprecation )?(?:Error|Warning))', stripped):
            forced.append('cmake')
        elif stripped == 'Traceback (most recent call last):':
            forced.append('python')
        elif (re.match(r'^(?:In file included from|\s+from\s+/)', line) or
              re.match(r'^.*?:\d+:\d+:\s*(?:error|warning|note)', line, re.IGNORECASE) or
              re.match(r'^g?make(?:\[\d+\])?:', line)):
            forced.append('gcc')
        else:
            forced.append(None)

    # Forward pass: propagate mode to unanchored lines.
    types: List[str] = []
    current = 'gcc'
    for t in forced:
        if t is not None:
            current = t
        types.append(current)

    # Group into contiguous segments and highlight each.
    result: List[str] = []
    i = 0
    while i < len(lines):
        seg_type = types[i]
        seg_lines: List[str] = []
        while i < len(lines) and types[i] == seg_type:
            seg_lines.append(lines[i])
            i += 1
        if seg_type == 'cmake':
            result.extend(_highlight_cmake_block(seg_lines))
        elif seg_type == 'python' and _pytb_lexer:
            text = '\n'.join(seg_lines)
            result.extend(_pyg_highlight(text, _pytb_lexer, _term_fmt).rstrip('\n').splitlines())
        else:
            result.extend(_highlight_gcc_line(l) for l in seg_lines)
    return result
