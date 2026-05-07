from pathlib import Path

import pytest

from dbt_scribe.cli import BootstrapError, _bootstrap


def _make_dbt_project(root: Path) -> Path:
    """Create a minimal valid dbt project structure."""
    (root / "dbt_project.yml").write_text("name: test\n")
    (root / "target").mkdir()
    (root / "target" / "manifest.json").write_text("{}\n")
    (root / "dbt-scribe.yml").write_text("version: 1\n")
    return root


# ── happy path ───────────────────────────────────────────────────────────────


def test_bootstrap_passes_when_all_files_present(tmp_path):
    _make_dbt_project(tmp_path)
    _bootstrap(cwd=tmp_path)  # must not raise


# ── missing file cases ───────────────────────────────────────────────────────


def test_bootstrap_fails_missing_dbt_project_yml(tmp_path):
    _make_dbt_project(tmp_path)
    (tmp_path / "dbt_project.yml").unlink()
    with pytest.raises(BootstrapError, match="dbt_project.yml"):
        _bootstrap(cwd=tmp_path)


def test_bootstrap_fails_missing_manifest(tmp_path):
    _make_dbt_project(tmp_path)
    (tmp_path / "target" / "manifest.json").unlink()
    with pytest.raises(BootstrapError, match="manifest.json"):
        _bootstrap(cwd=tmp_path)


def test_bootstrap_fails_missing_scribe_config(tmp_path):
    _make_dbt_project(tmp_path)
    (tmp_path / "dbt-scribe.yml").unlink()
    with pytest.raises(BootstrapError, match="dbt-scribe.yml"):
        _bootstrap(cwd=tmp_path)


def test_bootstrap_fails_all_missing(tmp_path):
    with pytest.raises(BootstrapError) as exc_info:
        _bootstrap(cwd=tmp_path)
    msg = str(exc_info.value)
    assert "dbt_project.yml" in msg
    assert "manifest.json" in msg
    assert "dbt-scribe.yml" in msg


# ── error message quality ────────────────────────────────────────────────────


def test_bootstrap_error_includes_hint_for_manifest(tmp_path):
    _make_dbt_project(tmp_path)
    (tmp_path / "target" / "manifest.json").unlink()
    with pytest.raises(BootstrapError, match="dbt compile"):
        _bootstrap(cwd=tmp_path)


def test_bootstrap_error_includes_hint_for_config(tmp_path):
    _make_dbt_project(tmp_path)
    (tmp_path / "dbt-scribe.yml").unlink()
    with pytest.raises(BootstrapError, match="dbt-scribe init"):
        _bootstrap(cwd=tmp_path)
