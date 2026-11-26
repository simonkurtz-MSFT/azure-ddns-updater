# Contributing to Azure Dynamic DNS Updater

Thank you for your interest in contributing to this repo! If you come across bugs or see opportunity for improvement, please submit an issue in this repo first.

## Development tools

Use Python 3.15 to match the container; CI continues to test Python 3.11 through
3.15. Install development dependencies in a project-local virtual environment,
not globally. All CLI checks use Python; Node.js and npm are not required.

From the repository root in PowerShell:

```powershell
py -3.15 -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-dev.txt
```

On Linux/macOS, use `python3 -m venv .venv` and `source .venv/bin/activate` instead.
Select that environment with **Python: Select Interpreter** in VS Code. If an
existing environment refers to an uninstalled interpreter, recreate it deliberately
before installing packages.

### Formatting and linting

- [Ruff](ruff.toml) is the sole Python formatter and linter. The configuration keeps
  the Python 3.11 compatibility floor, 88-character lines and double quotes, with
  a small correctness/import-order baseline rather than APIM's broader Pylint rule
  families. Source and tests are both checked.
- [mdformat](.mdformat.toml) owns Markdown formatting, with the GFM plugin for
  aligned tables. It preserves prose wrapping and validates rendering equivalence;
  fenced code is not reformatted.
- [PyMarkdown](.pymarkdown.json) checks Markdown structure. Long lines and the
  heading-free disclaimer remain allowed; duplicate headings are allowed under
  different parents only.
- The [Markdown checker](scripts/check_markdown.py) runs both tools and rejects
  trailing spaces, including in fenced code (which PyMarkdown skips). Use a visible
  backslash for an intentional Markdown hard break. It discovers tracked and
  non-ignored new Markdown through Git, excluding local dependencies.
- [EditorConfig](.editorconfig) owns whitespace and indentation (two spaces, except
  four for Python). JSON/JSONC uses VS Code's built-in formatter, and YAML uses its
  optional YAML extension. These editor formatters are not CLI/CI formatting gates.
- [.gitattributes](.gitattributes) normalizes tracked text to LF. Generated files
  and dependencies are excluded from formatter/linter discovery.

Run the read-only checks before submitting a change:

```powershell
python -m ruff check .
python -m ruff format --check .
python scripts\check_markdown.py
python -m unittest discover -s tests -v
git diff --check
```

Apply formatting and review safe lint fixes locally:

```powershell
python -m ruff check --fix .
python -m ruff format .
python -m mdformat README.md CONTRIBUTING.md DISCLAIMER.md
```

All Python and Markdown tools are pinned in [requirements-dev.txt](requirements-dev.txt).
Dependabot checks them weekly with the existing eight-day update cooldown.
Runtime dependencies and the
container toolchain are unchanged; development tools stay out of the image.

### VS Code

Install the selected [recommended extensions](.vscode/extensions.json) if desired;
recommendations do not install or pin extensions. The [workspace settings](.vscode/settings.json)
select Ruff for Python and mdformat for Markdown. The mdformat extension uses the
selected Python interpreter and its installed packages. Python fixes/import
organization run on explicit saves. Markdown lint diagnostics come from the
Python checker in CLI/CI, not a second save-time formatter.
The editor uses the existing unittest suite, not pytest.

Save-time cleanup is a convenience, not a substitute for CLI/CI checks. Install
the development requirements in the selected interpreter before using mdformat
in the editor.

## Contributors

The below list contains all contributors to date and should serve as a record of recognition for their efforts.

| Name            | GitHub                                                | LinkedIn                                             |
| :-------------- | :---------------------------------------------------- | :--------------------------------------------------- |
| Simon Kurtz     | [simonkurtz-MSFT](https://github.com/simonkurtz-MSFT) | [simonkurtz](https://www.linkedin.com/in/simonkurtz) |
| Renan Fernandes | [renanfernandes](https://github.com/renanfernandes)   | [renanm](https://www.linkedin.com/in/renanm/)        |
