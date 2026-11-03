"""Run the published reproduction sequence from `TEST_REPORT.md` §13, timed step by step.

This is the harness behind the table in `AUDIT_REPORT.md`'s appendix. It reads the command list out of the
document rather than retyping it, so the timings describe the sequence a reader would actually run.

    python audit_checks/time_reproduction_sequence.py [--log-dir DIR]

Logs go to a temporary directory by default, so timing the build does not dirty the working tree. Expect about
an hour: the four heaviest steps are passage segmentation, the live re-download of all 65 works, the state coder
and the similarity engine, and step 3 is the only step that needs a network.
"""
import argparse
import re
import subprocess
import sys
import tempfile
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def commands():
    doc = (ROOT / "TEST_REPORT.md").read_bytes().decode("utf-8")
    block = re.search(r"## 13\. Reproduction\r?\n\r?\n```bash\r?\n(.*?)```", doc, re.S).group(1)
    return [line.strip() for line in block.splitlines() if line.strip()]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--log-dir", default=None,
                        help="where to write progress.log and stdout.log (default: a temporary directory)")
    args = parser.parse_args()
    log_dir = Path(args.log_dir) if args.log_dir else Path(tempfile.mkdtemp(prefix="reproduction-timing-"))
    log_dir.mkdir(parents=True, exist_ok=True)

    todo = commands()
    print(f"{len(todo)} commands, first={todo[0]!r}", flush=True)
    with (log_dir / "progress.log").open("w", encoding="utf-8", newline="\n") as progress, \
            (log_dir / "stdout.log").open("w", encoding="utf-8", newline="\n") as output:
        total = 0.0
        failures = []
        for index, command in enumerate(todo, 1):
            started = time.time()
            finished = subprocess.run(command, cwd=str(ROOT), shell=True, capture_output=True,
                                      text=True, encoding="utf-8", errors="replace")
            elapsed = time.time() - started
            total += elapsed
            line = f"{index:2d}  exit={finished.returncode}  {elapsed:7.1f}s  {command}"
            print(line, flush=True)
            progress.write(line + "\n")
            progress.flush()
            output.write(f"\n===== {line}\n{finished.stdout}\n{finished.stderr}\n")
            output.flush()
            if finished.returncode != 0:
                failures.append((index, command, finished.returncode))
        progress.write(f"\nsteps={len(todo)} total_seconds={total:.1f} failures={failures}\n")
    print(f"STEPS={len(todo)} TOTAL={total:.1f}s FAILURES={failures}", flush=True)
    print(f"logs: {log_dir / 'progress.log'}", flush=True)
    return 1 if failures else 0


if __name__ == "__main__":
    sys.exit(main())
