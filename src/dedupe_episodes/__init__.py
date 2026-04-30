"""Dedupe TV episodes by quality. Keep best, delete worse + sidecars."""
from dedupe_episodes.cli import (
    EpisodeKey,
    Quality,
    VideoFile,
    find_sidecars,
    human_bytes,
    main,
    parse_episode_key,
    parse_quality,
)

__version__ = "0.1.2"
__all__ = [
    "EpisodeKey",
    "Quality",
    "VideoFile",
    "find_sidecars",
    "human_bytes",
    "main",
    "parse_episode_key",
    "parse_quality",
]
