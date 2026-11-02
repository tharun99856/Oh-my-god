#!/usr/bin/env python3
"""Static checks for the TeX paper, beside a real LaTeX toolchain.

`paper/main.tex` is compiled here -- MiKTeX 25.12, `pdflatex`, twice -- and
`tests/test_tex_typesetting.py` re-runs that compile and fails the suite if the log
reports an overfull box, an undefined reference or a failed exit. What this tool does
is the complementary half: the structural properties a static read establishes, so
that a reader without a TeX distribution can still check the file's geometry, and so
that a defect is named at the line that caused it rather than in a log 900 lines later.

Checks:
- environment nesting: every `\\begin{X}` has a matching `\\end{X}`, in order, and nothing is left open
- table geometry: each row supplies the cell count its enclosing column specification declares, counting
  unescaped `&` outside inline math and skipping `\\multicolumn`, `\\cline` and `\\booktabs` rules
- label hygiene: every `\\ref`/`\\eqref` target has a `\\label`; every `\\cite` key has a `\\bibitem`; no
  `\\bibitem` goes uncited
- escape hygiene: no `#` outside a command parameter, no unescaped `$` (math is delimited with `\\( \\)` and
  `\\begin{equation}`), and every `_` that is not `\\_` must sit inside math
- line-break discipline: the preamble must redefine `\\_` to carry a breakpoint. Typewriter text does not
  hyphenate, so without it an artifact name such as `results/ontology_passage_pairs.jsonl.gz` is one box
  that cannot wrap, and a fixed-width table column overflows into its neighbour. 49 such boxes were measured
  in the first compiled edition of this paper; the macro is what removed them, and this check keeps it from
  being deleted by accident.
- brace balance over the whole file, comments excluded

Discipline: a clean run is proof of structure, never of content. This tool cannot check that a number in the
prose matches the artifact it cites, or that a sentence is accurate. Compilation and page geometry are the
test's job, not this file's, and neither is a substitute for reading the paper.

`--self-test` answers the obvious objection to an unverified verifier: it injects each defect class into an
in-memory copy of the paper, one at a time, and requires the matching check to fire. A validator that has
never been shown to fail is decoration.

Usage:
    python tools/validate_tex.py [paper/main.tex]
    python tools/validate_tex.py --self-test
Exit 0 when every check passes, 1 with a line-numbered report otherwise.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

TABLE_ENVS = ("tabular", "tabularx", "longtable", "tabu", "array")
SKIP_ROW_MARKERS = ("\\multicolumn", "\\cline", "\\rowcolor")
RULE_RE = re.compile(r"\\(top|mid|bottom)rule")
DISPLAY_ENV_RE = re.compile(r"\\(begin|end)\{(equation|align|gather|multline)\*?\}")
BREAKPOINT_RE = re.compile(r"\\DeclareRobustCommand\{\\_\}\{[^}]*(?:allowbreak|discretionary)[^}]*\}")


def strip_comment(line: str) -> str:
    """The part of a line LaTeX sees. A `%` opens a comment unless escaped; a whole-line comment is nothing."""
    if line.lstrip().startswith("%"):
        return ""
    out, i = [], 0
    while i < len(line):
        if line[i] == "%":
            if i and line[i - 1] == "\\":
                out.append("@")  # escaped percent: literal text, marked so later scans ignore it
            else:
                break
        else:
            out.append(line[i])
        i += 1
    return "".join(out)


def cell_count(row: str) -> int:
    """Unescaped `&` outside inline math -- the number of cell boundaries on the row."""
    n, i, depth = 0, 0, 0
    while i < len(row):
        ch = row[i]
        if ch == "\\":
            i += 2
            continue
        if ch == "$":
            depth ^= 1
        elif ch == "&" and depth == 0:
            n += 1
        i += 1
    return n


def first_group(text: str):
    """The brace-balanced contents of the first `{...}` in `text`, or None."""
    start = text.find("{")
    if start < 0:
        return None
    depth = 0
    for i in range(start, len(text)):
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start + 1:i]
    return None


def column_count(spec: str) -> int:
    """How many columns a tabular column specification declares.

    Strips `@{...}`/`!{...}` separators, width groups and column-formatting commands, then counts the
    remaining single-letter column types (`l`, `c`, `r`, `p`, `m`, `b`, and this file's `L`).
    """
    spec = re.sub(r"@{[^{}]*}", "", spec)
    spec = re.sub(r"!{[^{}]*}", "", spec)
    spec = re.sub(r">{[^{}]*}", "", spec)
    spec = re.sub(r"\{[^{}]*\}", "", spec)          # width groups such as {3.0cm}
    spec = re.sub(r"\\[A-Za-z]+\*?(\[[^\]]*\])?(\{[^{}]*\})?", "", spec)
    return len(re.findall(r"[A-Za-z]", spec))


def display_math_lines(lines):
    """Line numbers lying inside a displayed equation, for the underscore check."""
    inside, open_at = set(), None
    for num, line in enumerate(lines, 1):
        for m in DISPLAY_ENV_RE.finditer(line):
            if m.group(1) == "begin":
                open_at = num
            elif open_at is not None:
                inside.update(range(open_at, num + 1))
                open_at = None
        if open_at is not None:
            inside.add(num)
    return inside


def inline_math_spans(line: str):
    """Character spans of `\\( ... \\)` and `$ ... $` on one line."""
    spans = [m.span() for m in re.finditer(r"\\\(.+?\\\)", line)]
    spans += [m.span() for m in re.finditer(r"\$[^$]*\$", line)]
    return spans


def in_span(spans, pos) -> bool:
    return any(lo <= pos <= hi for lo, hi in spans)


def check_text(text: str):
    """Return (lines, rows geometry-checked, labels, bibitems, problems)."""
    raw = text.splitlines()
    lines = [strip_comment(l) for l in raw]
    joined = "\n".join(lines)
    problems = []

    stack, spec_stack, current_cols = [], [], None
    rows_checked = 0
    for num, line in enumerate(lines, 1):
        for begin in re.finditer(r"\\begin\{([^}]*)\}", line):
            env = begin.group(1)
            stack.append((env, num))
            if env in TABLE_ENVS:
                spec = first_group(line[begin.end():])
                cols = column_count(spec) if spec else None
                current_cols = cols
                spec_stack.append(cols)
        for end in re.finditer(r"\\end\{([^}]*)\}", line):
            env = end.group(1)
            if not stack:
                problems.append((num, f"\\end{{{env}}} with no \\begin"))
                continue
            top, opened = stack.pop()
            if top != env:
                problems.append((num, f"\\begin{{{top}}} at line {opened} closed by \\end{{{env}}}"))
            if env in TABLE_ENVS and spec_stack:
                spec_stack.pop()
                current_cols = spec_stack[-1] if spec_stack else None
        if not line.strip() or not line.rstrip().endswith("\\\\") or not current_cols:
            continue
        if any(marker in line for marker in SKIP_ROW_MARKERS) or RULE_RE.search(line):
            continue
        got = cell_count(line)
        if got != current_cols - 1:
            problems.append((num, f"table row has {got + 1} cells, column spec declares {current_cols}"))
        else:
            rows_checked += 1
    for env, num in stack:
        problems.append((num, f"unclosed environment {env}"))

    balance = 0
    for line in lines:
        i = 0
        while i < len(line):
            if line[i] == "\\" and i + 1 < len(line):
                i += 2
                continue
            if line[i] == "{":
                balance += 1
            elif line[i] == "}":
                balance -= 1
            i += 1
    if balance:
        problems.append((0, f"brace balance is {balance}, not 0"))

    displayed = display_math_lines(lines)
    for num, line in enumerate(lines, 1):
        spans = inline_math_spans(line)
        for m in re.finditer(r"(?<!\\)_", line):
            if in_span(spans, m.start()) or num in displayed:
                continue
            problems.append((num, f"unescaped _ outside math: {raw[num - 1].strip()[:70]}"))
        for m in re.finditer(r"(?<!\\)#", line):
            if "\\newcommand" in line or "\\newcolumntype" in line or "\\renewcommand" in line:
                continue
            problems.append((num, f"unescaped #: {raw[num - 1].strip()[:70]}"))
        if re.search(r"(?<!\\)\$", line):
            problems.append((num, "unescaped $ (this file delimits math with \\( \\) and \\begin{equation})"))

    if not BREAKPOINT_RE.search(joined):
        problems.append((0, "no breakpoint on \\_ : typewriter artifact names cannot wrap and overflow "
                            "their table column"))

    labels = {m.group(1) for m in re.finditer(r"\\label\{([^}]*)\}", joined)}
    refs = {m.group(1) for m in re.finditer(r"\\(?:ref|eqref)\{([^}]*)\}", joined)}
    for target in sorted(refs - labels):
        problems.append((0, f"\\ref target with no \\label: {target}"))
    used_keys = set()
    for m in re.finditer(r"\\cite[tp]?\{([^}]*)\}", joined):
        used_keys.update(k.strip() for k in m.group(1).split(","))
    bib_keys = {m.group(1) for m in re.finditer(r"\\bibitem(?:\[[^\]]*\])?\{([^}]*)\}", joined)}
    for key in sorted(used_keys - bib_keys):
        problems.append((0, f"\\cite key with no \\bibitem: {key}"))
    for key in sorted(bib_keys - used_keys):
        problems.append((0, f"\\bibitem never cited: {key}"))

    return len(raw), rows_checked, len(labels), len(bib_keys), problems


# Each entry is (defect class, text to find, text to replace it with, substring the report must contain).
MUTATIONS = (
    ("table geometry", r"Version pair & Class relation & \(S_{\mathrm{seq}}\) & \(S_{\mathrm{motif}}\) (dom.)"
                       r" & \(S_{\mathrm{causal}}\) & \(S_{\mathrm{role}}\) \\",
     r"Version pair & Class relation & X \\", "table row has"),
    ("unclosed environment", r"\begin{document}", r"\begin{document} \begin{equation}", "unclosed environment"),
    ("mismatched \\end", r"\end{document}", r"\end{documentx}", "closed by"),
    ("brace balance", r"\section{Introduction}", r"\section{Introduction", "brace balance"),
    ("dangling reference", r"\ref{tab:packet}", r"\ref{tab:packett}", "no \\label"),
    ("citation key", r"\bibitem[George(2003)]{george2003}", r"\bibitem[George(2003)]{george2003b}",
     "never cited"),
    ("unescaped _", "MinHash banding", "MinHash_x banding", "unescaped _"),
    ("unescaped #", "MinHash banding", "MinHash#banding", "unescaped #"),
    ("unescaped $", "MinHash banding", "MinHash $5 banding", "unescaped $"),
    ("underscore breakpoint", r"\DeclareRobustCommand{\_}{\textunderscore\allowbreak}",
     r"\DeclareRobustCommand{\_}{\textunderscore}", "no breakpoint on"),
)

GUARANTEE = ("guarantee given: structure only -- not that the prose matches the artifacts it cites. "
             "Compilation and overfull-box geometry are checked by tests/test_tex_typesetting.py, "
             "which skips where no LaTeX engine is installed.")


def self_test(text: str) -> int:
    """Inject each defect in isolation and require the matching check to fire."""
    failures = []
    for name, old, new, expect in MUTATIONS:
        if old not in text:
            print(f"  {name:22} SKIPPED -- anchor not present in the paper: {old[:50]!r}")
            failures.append(name)
            continue
        *_, problems = check_text(text.replace(old, new, 1))
        hits = [msg for _, msg in problems if expect in msg]
        if hits:
            print(f"  {name:22} fires  -> {hits[0][:78]}")
        else:
            print(f"  {name:22} DOES NOT FIRE (expected {expect!r})")
            failures.append(name)
    base_total, base_rows, base_labels, base_bibs, base_problems = check_text(text)
    print(f"clean copy: {base_total} lines, {base_rows} rows geometry-checked, {base_labels} labels, "
          f"{base_bibs} bibliography entries, {len(base_problems)} problem(s)")
    if base_problems or failures:
        print("self-test: failed")
        return 1
    print(f"self-test: passed -- all {len(MUTATIONS)} defect classes detected, none on the clean copy")
    return 0


def main() -> int:
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    path = Path(args[0]) if args else ROOT / "paper/main.tex"
    if not path.exists():
        print(f"status: failed -- paper file not found: {path}")
        return 1
    text = path.read_text(encoding="utf-8")
    if "--self-test" in sys.argv:
        print(f"self-test on a copy of {path.name}: each injected defect must be reported")
        return self_test(text)
    total, rows, labels, bibitems, problems = check_text(text)
    print(f"validated {path.name} under {ROOT.name}: {total} lines, {rows} table rows geometry-checked, "
          f"{labels} labels, {bibitems} bibliography entries")
    if problems:
        print(f"status: failed ({len(problems)} problem(s))")
        for num, msg in sorted(problems):
            print(f"  line {num}: {msg}" if num else f"  file: {msg}")
    else:
        print("status: passed -- environments, table geometry, escapes, breakpoint macro, label and "
              "citation cross-checks all clean")
    print(GUARANTEE)
    return 1 if problems else 0


if __name__ == "__main__":
    sys.exit(main())
