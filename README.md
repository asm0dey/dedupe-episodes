# dedupe-episodes

[![PyPI version](https://img.shields.io/pypi/v/dedupe-episodes.svg)](https://pypi.org/project/dedupe-episodes/)
[![Python versions](https://img.shields.io/pypi/pyversions/dedupe-episodes.svg)](https://pypi.org/project/dedupe-episodes/)
[![License](https://img.shields.io/pypi/l/dedupe-episodes.svg)](https://github.com/asm0dey/dedupe-episodes/blob/main/LICENSE)
[![CI](https://github.com/asm0dey/dedupe-episodes/actions/workflows/ci.yml/badge.svg)](https://github.com/asm0dey/dedupe-episodes/actions/workflows/ci.yml)

Scan a TV show library, detect duplicate episodes at different qualities,
keep the best, delete the rest (and their sidecar `.nfo` / `-thumb.jpg` /
`.srt` files).

## Quality ranking

1. **Resolution**: 2160p > 1080p > 720p > 480p
2. **Same resolution**: PROPER / REPACK beats plain
3. **Tied** (same resolution AND same proper flag): WARN + skip — manual review

Resolution always outranks proper. So a `2160p` plain release beats a
`1080p Proper`, but a `1080p Proper` beats a plain `1080p`.

## Install

CLI app — recommended way is to install it isolated from your system Python:

```bash
# isolated install with uv (recommended)
uv tool install dedupe-episodes

# isolated install with pipx
pipx install dedupe-episodes

# run once without installing
uvx dedupe-episodes /path/to/shows
pipx run dedupe-episodes /path/to/shows

# or plain pip (into current env)
pip install dedupe-episodes
```

### Standalone binary (no Python required)

Each release ships pre-built binaries on
[GitHub Releases](https://github.com/asm0dey/dedupe-episodes/releases/latest):

| Platform | Asset |
|----------|-------|
| Linux x86_64 | `dedupe-episodes-linux-x86_64` |
| macOS Apple Silicon | `dedupe-episodes-macos-arm64` |
| Windows x86_64 | `dedupe-episodes-windows-x86_64.exe` |

```bash
# Linux / macOS — download, mark executable, run
curl -LO https://github.com/asm0dey/dedupe-episodes/releases/latest/download/dedupe-episodes-linux-x86_64
chmod +x dedupe-episodes-linux-x86_64
./dedupe-episodes-linux-x86_64 /path/to/shows
```

Binaries are built with [Nuitka](https://nuitka.net) (real C-compiled,
single-file, ~12 MB) — bundle Python interpreter + all deps.

## Usage

```bash
dedupe-episodes /path/to/shows           # dry-run (default — prints plan, deletes nothing)
dedupe-episodes /path/to/shows --delete  # actually delete losers + their sidecars
dedupe-episodes /path/to/shows --ext mkv --ext mp4   # restrict scanned extensions
```

Episodes are grouped by `(parent directory, season, episode)`, parsed via
[`guessit`](https://pypi.org/project/guessit/). Sidecars are siblings whose
filename starts with the video stem followed by `.`, `-`, or `_`.

## Develop locally

```bash
git clone https://github.com/asm0dey/dedupe-episodes
cd dedupe-episodes
uv sync
uv run dedupe-episodes /path/to/shows
```

## Tests

```bash
uv run pytest
```

53 tests, all run on an in-memory fake filesystem via
[`pyfakefs`](https://pypi.org/project/pyfakefs/) — no real disk I/O,
no host pollution.
