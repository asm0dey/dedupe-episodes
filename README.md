# dedupe-episodes

Scan a TV show library, detect duplicate episodes at different qualities,
keep the best, delete the rest (and their sidecar `.nfo` / `-thumb.jpg` /
`.srt` files).

## Quality ranking

1. **Resolution**: 2160p > 1080p > 720p > 480p
2. **Same resolution**: PROPER / REPACK beats plain
3. **Tied** (same resolution AND same proper flag): WARN + skip — manual review

Resolution always outranks proper. So a `2160p` plain release beats a
`1080p Proper`, but a `1080p Proper` beats a plain `1080p`.

## Usage

```bash
uv run main.py /path/to/shows           # dry-run (default — prints plan, deletes nothing)
uv run main.py /path/to/shows --delete  # actually delete losers + their sidecars
uv run main.py /path/to/shows --ext mkv --ext mp4   # restrict scanned extensions
```

Episodes are grouped by `(parent directory, season, episode)`, parsed via
[`guessit`](https://pypi.org/project/guessit/). Sidecars are siblings whose
filename starts with the video stem followed by `.`, `-`, or `_`.

## Install

```bash
git clone <this-repo>
cd dedupe-episodes
uv sync
```

## Tests

```bash
uv run pytest
```

53 tests, all run on an in-memory fake filesystem via
[`pyfakefs`](https://pypi.org/project/pyfakefs/) — no real disk I/O,
no host pollution.
