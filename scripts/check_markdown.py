"""Check owned Markdown formatting, lint rules, and all trailing whitespace."""

import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def whitespace_errors(text: str) -> list[str]:
    """Check literal whitespace, including code blocks that linters skip."""
    errors = [
        f"{number}: trailing whitespace"
        for number, line in enumerate(text.splitlines(), start=1)
        if line.endswith((" ", "\t"))
    ]
    if text and not text.endswith("\n"):
        errors.append(f"{len(text.splitlines())}: missing final newline")
    return errors


def main() -> int:
    """Check tracked and non-ignored new Markdown with the selected interpreter."""
    result = subprocess.run(
        [
            "git",
            "ls-files",
            "-z",
            "--cached",
            "--others",
            "--exclude-standard",
            "--",
            "*.md",
        ],
        cwd=ROOT,
        stdout=subprocess.PIPE,
        text=True,
        encoding="utf-8",
        check=True,
    )
    files = [name for name in result.stdout.split("\0") if name]
    if not files:
        print("No owned Markdown files found.", file=sys.stderr)
        return 1

    failed = False
    for name in files:
        for error in whitespace_errors((ROOT / name).read_text(encoding="utf-8")):
            print(f"{name}:{error}", file=sys.stderr)
            failed = True

    for arguments in (
        ["mdformat", "--check", *files],
        ["pymarkdown", "--config", ".pymarkdown.json", "scan", *files],
    ):
        checked = subprocess.run(
            [sys.executable, "-m", *arguments], cwd=ROOT, check=False
        )
        failed |= checked.returncode != 0

    if failed:
        return 1
    print(f"Markdown checks passed for {len(files)} files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
