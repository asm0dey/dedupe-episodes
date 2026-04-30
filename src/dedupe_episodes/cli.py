#!/usr/bin/env python3
# Nuitka build options (auto-applied when compiling this file with Nuitka).
# nuitka-project: --onefile
# nuitka-project: --include-package=guessit
# nuitka-project: --include-package-data=guessit
# nuitka-project: --include-package=babelfish
# nuitka-project: --include-package-data=babelfish
# nuitka-project: --include-package=rebulk
# nuitka-project: --nofollow-import-to=rebulk.test
# nuitka-project: --nofollow-import-to=guessit.test
"""Dedupe TV episodes by quality. Keep best, delete worse + sidecar files.

Quality ranking:
  1. Resolution: 2160p > 1080p > 720p > 480p
  2. Same resolution: PROPER/REPACK beats plain
  3. Tied (resolution, proper) -> WARN + skip (manual review)

Sidecars (.nfo, -thumb.jpg, .srt, etc.) tied to a deleted video are removed too.

Usage:
  uv run main.py /path/to/shows           # dry-run
  uv run main.py /path/to/shows --delete  # actually delete
"""
from __future__ import annotations

import argparse
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from guessit import guessit
from tqdm import tqdm

VIDEO_EXTS = {".mkv", ".mp4", ".avi", ".m4v", ".ts", ".mov", ".webm", ".wmv"}

RES_RANK = {"2160p": 4, "1080p": 3, "720p": 2, "576p": 1, "480p": 1}


@dataclass(frozen=True, order=True)
class Quality:
    """Sortable quality fingerprint. Higher = better."""
    resolution_rank: int
    proper_rank: int
    size: int
    # Display-only — excluded from ordering/equality.
    resolution_label: str = field(default="?", compare=False)
    proper_label: str | None = field(default=None, compare=False)

    def tied_with(self, other: "Quality") -> bool:
        """True if resolution and proper flag match (size ignored)."""
        return (self.resolution_rank, self.proper_rank) == (
            other.resolution_rank, other.proper_rank,
        )

    @property
    def label(self) -> str:
        if self.proper_label:
            return f"{self.resolution_label} {self.proper_label}"
        return self.resolution_label


@dataclass(frozen=True, order=True)
class EpisodeKey:
    """Hashable, sortable identifier grouping files into one episode slot.

    `episode` is always a tuple — single-episode files become `(n,)` — so
    sorting never compares heterogeneous types.
    """
    title: str
    parent: str
    season: int
    episode: tuple[int, ...]

    def format_short(self) -> str:
        return f"S{self.season:02d}E" + "-E".join(f"{e:02d}" for e in self.episode)


@dataclass
class VideoFile:
    path: Path
    quality: Quality


def parse_quality(info: dict, size: int) -> Quality:
    res_label = info.get("screen_size") or "?"
    other = info.get("other") or []
    if isinstance(other, str):
        other = [other]
    proper_flags = [str(x) for x in other if str(x).lower() in {"proper", "repack"}]
    return Quality(
        resolution_rank=RES_RANK.get(res_label, 0),
        proper_rank=int(bool(proper_flags)),
        size=size,
        resolution_label=res_label,
        proper_label=" ".join(proper_flags) if proper_flags else None,
    )


def parse_episode_key(path: Path, info: dict) -> EpisodeKey | None:
    season = info.get("season")
    episode = info.get("episode")
    if season is None or episode is None:
        return None
    if isinstance(episode, list):
        ep_tuple: tuple[int, ...] = tuple(int(e) for e in episode)
    else:
        ep_tuple = (int(episode),)
    title = info.get("title") or path.parent.name
    return EpisodeKey(
        title=str(title).lower(),
        parent=str(path.parent.resolve()),
        season=int(season),
        episode=ep_tuple,
    )


def find_sidecars(video: Path) -> list[Path]:
    """Sibling files sharing the video's stem (e.g. -thumb.jpg, .nfo, .srt)."""
    stem = video.stem
    out: list[Path] = []
    for sib in video.parent.iterdir():
        if sib == video or not sib.is_file():
            continue
        if not sib.name.startswith(stem):
            continue
        rest = sib.name[len(stem):]
        if rest.startswith((".", "-", "_")):
            out.append(sib)
    return out


def human_bytes(n: float) -> str:
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if n < 1024:
            return f"{n:.1f} {unit}"
        n /= 1024
    return f"{n:.1f} PB"


def main() -> int:
    p = argparse.ArgumentParser(
        description="Dedupe TV episodes by quality.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__,
    )
    p.add_argument("path", type=Path, help="Root directory to scan recursively")
    p.add_argument("--delete", action="store_true",
                   help="Actually delete files (default: dry-run)")
    p.add_argument("--ext", action="append", default=None,
                   help="Override video extensions (repeatable, e.g. --ext mkv --ext mp4)")
    args = p.parse_args()

    if not args.path.is_dir():
        sys.exit(f"Not a directory: {args.path}")

    exts = ({"." + e.lower().lstrip(".") for e in args.ext}
            if args.ext else VIDEO_EXTS)

    groups: dict[EpisodeKey, list[VideoFile]] = defaultdict(list)
    skipped: list[Path] = []
    show_bar = sys.stderr.isatty()

    # Phase 1: walk tree (unknown total — generator).
    candidates: list[Path] = []
    walk_iter = tqdm(
        args.path.rglob("*"),
        desc="Scanning",
        unit=" file",
        disable=not show_bar,
        leave=False,
    )
    for f in walk_iter:
        if f.is_file() and f.suffix.lower() in exts:
            candidates.append(f)

    # Phase 2: parse with guessit (known total — slow regex work).
    parse_iter = tqdm(
        candidates,
        desc="Parsing ",
        unit=" file",
        disable=not show_bar,
        leave=False,
    )
    for f in parse_iter:
        info = guessit(f.name, {"type": "episode"})
        key = parse_episode_key(f, info)
        if key is None:
            skipped.append(f)
            continue
        quality = parse_quality(info, f.stat().st_size)
        groups[key].append(VideoFile(path=f, quality=quality))

    if skipped:
        print(f"Skipped {len(skipped)} unparseable file(s):")
        for f in skipped:
            print(f"  ?  {f}")
        print()

    total_deleted = 0
    total_freed = 0
    tied_groups = 0

    for key in sorted(groups):
        items = groups[key]
        if len(items) < 2:
            continue

        ranked = sorted(items, key=lambda v: v.quality, reverse=True)
        parent_name = Path(key.parent).name
        print(f"[{parent_name}] {key.format_short()}")

        if ranked[0].quality.tied_with(ranked[1].quality):
            tied_groups += 1
            print("  WARN: tied quality, skipping (resolve manually)")
            for v in ranked:
                print(f"    ?  {v.path.name}  [{v.quality.label}, {human_bytes(v.quality.size)}]")
            print()
            continue

        winner = ranked[0]
        print(f"  KEEP    {winner.path.name}  [{winner.quality.label}, {human_bytes(winner.quality.size)}]")
        for loser in ranked[1:]:
            sidecars = find_sidecars(loser.path)
            sidecar_size = sum(s.stat().st_size for s in sidecars)
            print(f"  DELETE  {loser.path.name}  [{loser.quality.label}, {human_bytes(loser.quality.size)}]")
            for s in sidecars:
                print(f"          + {s.name}  [{human_bytes(s.stat().st_size)}]")

            total_deleted += 1
            total_freed += loser.quality.size + sidecar_size

            if args.delete:
                try:
                    loser.path.unlink()
                    for s in sidecars:
                        s.unlink()
                except OSError as e:
                    print(f"  ERROR: {e}", file=sys.stderr)
        print()

    verb = "DELETED" if args.delete else "WOULD DELETE"
    print(f"{verb} {total_deleted} video(s) (+sidecars). Freed: {human_bytes(total_freed)}")
    if tied_groups:
        print(f"Skipped {tied_groups} tied-quality group(s) — review manually.")
    if not args.delete and total_deleted:
        print("Re-run with --delete to actually remove files.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
