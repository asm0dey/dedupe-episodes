"""Tests for dedupe-episodes."""
from __future__ import annotations

from pathlib import Path

import pytest
from guessit import guessit
from hamcrest import (
    assert_that,
    contains_inanyorder,
    contains_string,
    empty,
    equal_to,
    greater_than,
    has_item,
    has_length,
    is_,
    not_,
)

import main as dedupe
from pyfakefs.fake_filesystem import FakeFilesystem


# --- pyfakefs sanity ------------------------------------------------------

class TestFakeFsActive:
    def test_fs_fixture_is_fake_filesystem(self, fs) -> None:
        assert_that(isinstance(fs, FakeFilesystem), equal_to(True))

    def test_real_fs_paths_invisible_inside_fake(self, tmp_path: Path) -> None:
        """`/etc` exists on every Linux real fs; on pyfakefs it starts empty."""
        assert_that(Path("/etc").exists(), equal_to(False))
        assert_that(Path("/usr/bin/python3").exists(), equal_to(False))

    def test_fake_tmp_dir_does_not_exist_outside_test(self, tmp_path: Path) -> None:
        """tmp_path lives at /fake_tmp — pure fake-fs path, never on real disk."""
        assert_that(str(tmp_path), equal_to("/fake_tmp"))
        assert_that(tmp_path.is_dir(), equal_to(True))


# --- Helpers ---------------------------------------------------------------

def info(name: str) -> dict:
    return guessit(name, {"type": "episode"})


def touch(path: Path, size: int = 0) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"\0" * size)
    return path


def quality_for(name: str, size: int = 0) -> "dedupe.Quality":
    return dedupe.parse_quality(info(name), size)


# --- Quality ---------------------------------------------------------------

class TestQualityFields:
    @pytest.mark.parametrize("name,expected", [
        ("Show - S01E01 - X WEBDL-2160p.mkv", 4),
        ("Show - S01E01 - X WEBDL-1080p.mkv", 3),
        ("Show - S01E01 - X WEBDL-720p.mkv", 2),
        ("Show - S01E01 - X WEBDL-480p.mkv", 1),
        ("Show - S01E01 - X WEBDL-576p.mkv", 1),
    ])
    def test_resolution_rank(self, name: str, expected: int) -> None:
        assert_that(quality_for(name).resolution_rank, equal_to(expected))

    def test_unknown_resolution_is_zero(self) -> None:
        assert_that(dedupe.parse_quality({}, 0).resolution_rank, equal_to(0))

    def test_proper_detected(self) -> None:
        assert_that(quality_for("Show - S01E01 WEBDL-1080p Proper.mkv").proper_rank,
                    equal_to(1))

    def test_repack_detected(self) -> None:
        assert_that(quality_for("Show - S01E01 WEBDL-1080p REPACK.mkv").proper_rank,
                    equal_to(1))

    def test_plain_proper_zero(self) -> None:
        assert_that(quality_for("Show - S01E01 WEBDL-1080p.mkv").proper_rank,
                    equal_to(0))

    def test_size_carried(self) -> None:
        assert_that(quality_for("Show - S01E01 WEBDL-1080p.mkv", size=42).size,
                    equal_to(42))


class TestQualityOrdering:
    """Verify the user's three explicit rules."""

    def test_2160p_beats_1080p(self) -> None:
        assert_that(quality_for("Show - S01E01 WEBDL-2160p.mkv"),
                    is_(greater_than(quality_for("Show - S01E02 WEBDL-1080p.mkv"))))

    def test_1080p_beats_720p(self) -> None:
        assert_that(quality_for("Show - S01E01 WEBDL-1080p.mkv"),
                    is_(greater_than(quality_for("Show - S01E02 WEBDL-720p.mkv"))))

    def test_2160p_proper_beats_2160p_plain(self) -> None:
        assert_that(quality_for("Show - S01E01 WEBDL-2160p Proper.mkv"),
                    is_(greater_than(quality_for("Show - S01E02 WEBDL-2160p.mkv"))))

    def test_2160p_plain_beats_1080p_proper(self) -> None:
        """Resolution outranks proper flag — user's third rule."""
        assert_that(quality_for("Show - S01E01 WEBDL-2160p.mkv"),
                    is_(greater_than(quality_for("Show - S01E02 WEBDL-1080p Proper.mkv"))))

    def test_label_only_fields_excluded_from_ordering(self) -> None:
        """Display fields don't affect comparison — same rank => equal."""
        a = dedupe.Quality(3, 0, 100, resolution_label="1080p", proper_label=None)
        b = dedupe.Quality(3, 0, 100, resolution_label="DIFFERENT", proper_label="ALSO")
        assert_that(a, equal_to(b))


class TestQualityTiedWith:
    def test_same_resolution_same_proper_is_tied(self) -> None:
        a = quality_for("Show - S01E01 WEBDL-1080p.mkv", size=10)
        b = quality_for("Show - S01E02 HDTV-1080p.mkv", size=999)
        assert_that(a.tied_with(b), equal_to(True))

    def test_different_resolution_not_tied(self) -> None:
        a = quality_for("Show - S01E01 WEBDL-2160p.mkv")
        b = quality_for("Show - S01E02 WEBDL-1080p.mkv")
        assert_that(a.tied_with(b), equal_to(False))

    def test_proper_vs_plain_not_tied(self) -> None:
        a = quality_for("Show - S01E01 WEBDL-1080p Proper.mkv")
        b = quality_for("Show - S01E02 WEBDL-1080p.mkv")
        assert_that(a.tied_with(b), equal_to(False))


class TestQualityLabel:
    def test_plain(self) -> None:
        assert_that(quality_for("Show - S01E01 WEBDL-1080p.mkv").label,
                    equal_to("1080p"))

    def test_proper(self) -> None:
        label = quality_for("Show - S01E01 WEBDL-1080p Proper.mkv").label
        assert_that(label.lower(), contains_string("1080p"))
        assert_that(label.lower(), contains_string("proper"))


# --- EpisodeKey ------------------------------------------------------------

class TestEpisodeKey:
    def test_basic_episode_parses(self, tmp_path: Path) -> None:
        name = "Brilliant Minds - S02E04 - Lady Liberty WEBDL-1080p.mkv"
        f = touch(tmp_path / name)
        key = dedupe.parse_episode_key(f, info(name))
        assert_that(key, is_(not_(equal_to(None))))
        assert_that(key.season, equal_to(2))
        assert_that(key.episode, equal_to((4,)))

    def test_year_in_title_parses(self, tmp_path: Path) -> None:
        name = "CIA (2026) - S01E07 - Elimination Game WEBDL-1080p Proper.mkv"
        f = touch(tmp_path / name)
        key = dedupe.parse_episode_key(f, info(name))
        assert_that(key.season, equal_to(1))
        assert_that(key.episode, equal_to((7,)))

    def test_multi_episode_stored_as_tuple(self, tmp_path: Path) -> None:
        name = "Show - S01E01E02 - Two Parter WEBDL-1080p.mkv"
        f = touch(tmp_path / name)
        key = dedupe.parse_episode_key(f, info(name))
        assert_that(key.episode, equal_to((1, 2)))

    def test_single_episode_normalised_to_tuple(self, tmp_path: Path) -> None:
        """Regression: single-ep must be `(n,)`, not bare int — keeps sort safe."""
        name = "Show - S01E03 WEBDL-1080p.mkv"
        f = touch(tmp_path / name)
        key = dedupe.parse_episode_key(f, info(name))
        assert_that(isinstance(key.episode, tuple), equal_to(True))
        assert_that(key.episode, has_length(1))

    def test_missing_episode_returns_none(self, tmp_path: Path) -> None:
        name = "Random File.mkv"
        f = touch(tmp_path / name)
        assert_that(dedupe.parse_episode_key(f, info(name)), equal_to(None))

    def test_two_files_same_episode_get_same_key(self, tmp_path: Path) -> None:
        a_name = "Show - S01E01 - X WEBDL-1080p.mkv"
        b_name = "Show - S01E01 - X WEBDL-2160p.mkv"
        a = touch(tmp_path / a_name)
        b = touch(tmp_path / b_name)
        assert_that(dedupe.parse_episode_key(a, info(a_name)),
                    equal_to(dedupe.parse_episode_key(b, info(b_name))))

    def test_format_short_single(self) -> None:
        key = dedupe.EpisodeKey(title="x", parent="/", season=2, episode=(4,))
        assert_that(key.format_short(), equal_to("S02E04"))

    def test_format_short_multi(self) -> None:
        key = dedupe.EpisodeKey(title="x", parent="/", season=1, episode=(1, 2))
        assert_that(key.format_short(), equal_to("S01E01-E02"))

    def test_keys_sortable_with_mixed_episode_arities(self) -> None:
        """Single and multi episodes must compare without TypeError."""
        a = dedupe.EpisodeKey("show", "/parent", 1, (1, 2))
        b = dedupe.EpisodeKey("show", "/parent", 1, (3,))
        sorted([a, b])  # must not raise


# --- Sidecars --------------------------------------------------------------

class TestFindSidecars:
    def test_finds_nfo_and_thumb(self, tmp_path: Path) -> None:
        video = touch(tmp_path / "Show - S01E01 WEBDL-1080p.mkv")
        nfo = touch(tmp_path / "Show - S01E01 WEBDL-1080p.nfo")
        thumb = touch(tmp_path / "Show - S01E01 WEBDL-1080p-thumb.jpg")
        assert_that(dedupe.find_sidecars(video),
                    contains_inanyorder(nfo, thumb))

    def test_skips_unrelated_files(self, tmp_path: Path) -> None:
        video = touch(tmp_path / "Show - S01E01 WEBDL-1080p.mkv")
        touch(tmp_path / "Show - S01E02 WEBDL-1080p.nfo")
        touch(tmp_path / "unrelated.txt")
        assert_that(dedupe.find_sidecars(video), is_(empty()))

    def test_excludes_video_itself(self, tmp_path: Path) -> None:
        video = touch(tmp_path / "Show - S01E01 WEBDL-1080p.mkv")
        assert_that(dedupe.find_sidecars(video), not_(has_item(video)))

    def test_does_not_match_stem_prefix_substring(self, tmp_path: Path) -> None:
        video = touch(tmp_path / "Show - S01E01 WEBDL-1080p.mkv")
        touch(tmp_path / "Show - S01E01 WEBDL-1080p2.nfo")
        assert_that(dedupe.find_sidecars(video), is_(empty()))


# --- human_bytes -----------------------------------------------------------

class TestHumanBytes:
    @pytest.mark.parametrize("n,expected", [
        (0, "0.0 B"),
        (1023, "1023.0 B"),
        (1024, "1.0 KB"),
        (1024 * 1024, "1.0 MB"),
        (1024 ** 3, "1.0 GB"),
    ])
    def test_units(self, n: int, expected: str) -> None:
        assert_that(dedupe.human_bytes(n), equal_to(expected))


# --- End-to-end ------------------------------------------------------------

class TestEndToEnd:
    def _run(self, monkeypatch, capsys, *args: str) -> str:
        monkeypatch.setattr("sys.argv", ["main.py", *args])
        rc = dedupe.main()
        assert_that(rc, equal_to(0))
        return capsys.readouterr().out

    def test_dry_run_does_not_delete(self, tmp_path: Path, monkeypatch, capsys) -> None:
        a = touch(tmp_path / "Show - S01E01 WEBDL-1080p.mkv", size=10)
        b = touch(tmp_path / "Show - S01E01 WEBDL-2160p.mkv", size=20)
        out = self._run(monkeypatch, capsys, str(tmp_path))
        assert_that(out, contains_string("WOULD DELETE"))
        assert_that(a.exists(), equal_to(True))
        assert_that(b.exists(), equal_to(True))

    def test_delete_removes_loser_and_sidecars(
        self, tmp_path: Path, monkeypatch, capsys
    ) -> None:
        loser = touch(tmp_path / "Show - S01E01 WEBDL-1080p.mkv", size=10)
        loser_nfo = touch(tmp_path / "Show - S01E01 WEBDL-1080p.nfo")
        loser_thumb = touch(tmp_path / "Show - S01E01 WEBDL-1080p-thumb.jpg")
        winner = touch(tmp_path / "Show - S01E01 WEBDL-2160p.mkv", size=20)
        winner_nfo = touch(tmp_path / "Show - S01E01 WEBDL-2160p.nfo")

        out = self._run(monkeypatch, capsys, str(tmp_path), "--delete")

        assert_that(out, contains_string("DELETED"))
        assert_that(loser.exists(), equal_to(False))
        assert_that(loser_nfo.exists(), equal_to(False))
        assert_that(loser_thumb.exists(), equal_to(False))
        assert_that(winner.exists(), equal_to(True))
        assert_that(winner_nfo.exists(), equal_to(True))

    def test_proper_beats_plain_at_same_resolution(
        self, tmp_path: Path, monkeypatch, capsys
    ) -> None:
        plain = touch(tmp_path / "Show - S01E01 WEBDL-1080p.mkv", size=10)
        proper = touch(tmp_path / "Show - S01E01 WEBDL-1080p Proper.mkv", size=10)
        self._run(monkeypatch, capsys, str(tmp_path), "--delete")
        assert_that(plain.exists(), equal_to(False))
        assert_that(proper.exists(), equal_to(True))

    def test_higher_resolution_beats_lower_proper(
        self, tmp_path: Path, monkeypatch, capsys
    ) -> None:
        lower_proper = touch(tmp_path / "Show - S01E07 WEBDL-1080p Proper.mkv", size=10)
        higher = touch(tmp_path / "Show - S01E07 WEBDL-2160p.mkv", size=10)
        self._run(monkeypatch, capsys, str(tmp_path), "--delete")
        assert_that(lower_proper.exists(), equal_to(False))
        assert_that(higher.exists(), equal_to(True))

    def test_tied_quality_skipped_not_deleted(
        self, tmp_path: Path, monkeypatch, capsys
    ) -> None:
        a = touch(tmp_path / "Show - S01E05 WEBDL-1080p.mkv", size=10)
        b = touch(tmp_path / "Show - S01E05 HDTV-1080p.mkv", size=20)
        out = self._run(monkeypatch, capsys, str(tmp_path), "--delete")
        assert_that(out, contains_string("tied quality"))
        assert_that(a.exists(), equal_to(True))
        assert_that(b.exists(), equal_to(True))

    def test_singleton_episode_untouched(
        self, tmp_path: Path, monkeypatch, capsys
    ) -> None:
        only = touch(tmp_path / "Show - S01E03 WEBDL-1080p.mkv", size=10)
        self._run(monkeypatch, capsys, str(tmp_path), "--delete")
        assert_that(only.exists(), equal_to(True))

    def test_groups_by_parent_directory(
        self, tmp_path: Path, monkeypatch, capsys
    ) -> None:
        show_a = tmp_path / "Show A" / "Season 01"
        show_b = tmp_path / "Show B" / "Season 01"
        a = touch(show_a / "Show A - S01E01 WEBDL-1080p.mkv", size=10)
        b = touch(show_b / "Show B - S01E01 WEBDL-2160p.mkv", size=10)
        self._run(monkeypatch, capsys, str(tmp_path), "--delete")
        assert_that(a.exists(), equal_to(True))
        assert_that(b.exists(), equal_to(True))

    def test_unparseable_file_is_skipped(
        self, tmp_path: Path, monkeypatch, capsys
    ) -> None:
        weird = touch(tmp_path / "random_no_episode_info.mkv", size=10)
        out = self._run(monkeypatch, capsys, str(tmp_path), "--delete")
        assert_that(weird.exists(), equal_to(True))
        assert_that(out, contains_string("Skipped"))

    def test_multiple_losers_all_deleted(
        self, tmp_path: Path, monkeypatch, capsys
    ) -> None:
        p720 = touch(tmp_path / "Show - S01E10 WEBDL-720p.mkv", size=10)
        p1080 = touch(tmp_path / "Show - S01E10 WEBDL-1080p.mkv", size=10)
        p2160 = touch(tmp_path / "Show - S01E10 WEBDL-2160p.mkv", size=10)
        self._run(monkeypatch, capsys, str(tmp_path), "--delete")
        assert_that(p720.exists(), equal_to(False))
        assert_that(p1080.exists(), equal_to(False))
        assert_that(p2160.exists(), equal_to(True))

    def test_mixed_single_and_multi_episode_groups_sort_without_crash(
        self, tmp_path: Path, monkeypatch, capsys
    ) -> None:
        """Regression: dict mixing (n,) and (n,m) tuple keys must sort cleanly."""
        touch(tmp_path / "Show - S01E01E02 - Two Parter WEBDL-1080p.mkv", size=10)
        touch(tmp_path / "Show - S01E01E02 - Two Parter WEBDL-2160p.mkv", size=10)
        touch(tmp_path / "Show - S01E03 - Solo WEBDL-1080p.mkv", size=10)
        touch(tmp_path / "Show - S01E03 - Solo WEBDL-2160p.mkv", size=10)
        out = self._run(monkeypatch, capsys, str(tmp_path))
        assert_that(out, contains_string("WOULD DELETE"))

    def test_three_losers_each_with_six_sidecars(
        self, tmp_path: Path, monkeypatch, capsys
    ) -> None:
        """3 losers × 6 sidecars = 18 sidecars; all gone, winner survives."""
        sidecar_suffixes = (
            ".nfo",
            "-thumb.jpg",
            "-fanart.jpg",
            ".en.srt",
            ".ru.srt",
            ".eng.ass",
        )

        def make_set(stem: str, video_size: int) -> tuple[Path, list[Path]]:
            video = touch(tmp_path / f"{stem}.mkv", size=video_size)
            sidecars = [touch(tmp_path / f"{stem}{suf}", size=10) for suf in sidecar_suffixes]
            return video, sidecars

        # Three losers at strictly different quality tiers (no ties).
        loser_480, sc_480 = make_set("Show - S01E01 WEBDL-480p", 100)
        loser_720, sc_720 = make_set("Show - S01E01 WEBDL-720p", 200)
        loser_1080, sc_1080 = make_set("Show - S01E01 WEBDL-1080p", 300)
        # Winner: 1080p Proper beats 1080p plain (proper > plain at same res).
        winner, sc_winner = make_set("Show - S01E01 WEBDL-1080p Proper", 400)

        out = self._run(monkeypatch, capsys, str(tmp_path), "--delete")

        # 1 KEEP line, 3 DELETE lines, 18 sidecar lines.
        keep_lines = [ln for ln in out.splitlines() if ln.startswith("  KEEP")]
        delete_lines = [ln for ln in out.splitlines() if ln.startswith("  DELETE")]
        sidecar_lines = [ln for ln in out.splitlines() if ln.lstrip().startswith("+ ")]
        assert_that(keep_lines, has_length(1))
        assert_that(delete_lines, has_length(3))
        assert_that(sidecar_lines, has_length(18))

        # All loser videos + all 18 loser sidecars gone.
        for gone in (loser_480, loser_720, loser_1080, *sc_480, *sc_720, *sc_1080):
            assert_that(gone.exists(), equal_to(False))

        # Winner + winner's 6 sidecars intact.
        for kept in (winner, *sc_winner):
            assert_that(kept.exists(), equal_to(True))

        # Summary: 3 videos deleted, freed = (100 + 200 + 300) + 18*10 = 780 B.
        assert_that(out, contains_string("DELETED 3"))
        assert_that(out, contains_string("780.0 B"))

    def test_summary_counts_correctly(
        self, tmp_path: Path, monkeypatch, capsys
    ) -> None:
        touch(tmp_path / "Show - S01E01 WEBDL-720p.mkv", size=10)
        touch(tmp_path / "Show - S01E01 WEBDL-1080p.mkv", size=10)
        out = self._run(monkeypatch, capsys, str(tmp_path))
        delete_lines = [ln for ln in out.splitlines() if ln.startswith("  DELETE")]
        assert_that(delete_lines, has_length(1))
