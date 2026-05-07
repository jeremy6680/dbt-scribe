from __future__ import annotations

import shutil
from pathlib import Path

from dbt_scribe.analyzer import build_enriched_model
from dbt_scribe.config import ScribeConfig
from dbt_scribe.generators.docs_generator import DocsResult
from dbt_scribe.parsers.manifest_parser import parse_manifest
from dbt_scribe.writers.docs_writer import write_docs_block

FIXTURE_PROJECT = Path(__file__).parent / "fixtures" / "dbt_project"


def _config() -> ScribeConfig:
    return ScribeConfig.model_construct(
        llm=None,
        docs=ScribeConfig.model_fields["docs"].default,
        tests=ScribeConfig.model_fields["tests"].default,
        coverage=ScribeConfig.model_fields["coverage"].default,
        conventions=ScribeConfig.model_fields["conventions"].default,
        cache=ScribeConfig.model_fields["cache"].default,
        version=1,
    )


def _copy_project(tmp_path: Path) -> Path:
    project = tmp_path / "dbt_project"
    shutil.copytree(FIXTURE_PROJECT, project)
    return project


def _model(project: Path, name: str):
    manifest_node = next(
        node for node in parse_manifest(project / "target" / "manifest.json") if node.name == name
    )
    return build_enriched_model(manifest_node, None, _config())


def test_write_docs_block_creates_missing_file(tmp_path, monkeypatch):
    project = _copy_project(tmp_path)
    monkeypatch.chdir(project)
    model = _model(project, "fixtures")

    result = write_docs_block(
        model,
        DocsResult("Mart description.", "## Grain\nOne row per fixture.", {}),
        _config(),
        dry_run=False,
    )

    target = project / "models" / "marts" / "rugby" / "_rugby__docs.md"
    assert result.changed is True
    assert result.path == target
    assert "{% docs fixtures %}" in target.read_text()
    assert "## Grain" in target.read_text()


def test_write_docs_block_appends_to_existing_file(tmp_path, monkeypatch):
    project = _copy_project(tmp_path)
    monkeypatch.chdir(project)
    model = _model(project, "fixtures")
    target = project / "models" / "marts" / "rugby" / "_rugby__docs.md"
    target.write_text("{% docs existing_block %}\nExisting docs.\n{% enddocs %}\n")

    write_docs_block(
        model,
        DocsResult("Mart description.", "Generated docs.", {}),
        _config(),
        dry_run=False,
    )

    content = target.read_text()
    assert "{% docs existing_block %}" in content
    assert "{% docs fixtures %}" in content
    assert "Generated docs." in content


def test_write_docs_block_does_not_duplicate_existing_block(tmp_path, monkeypatch):
    project = _copy_project(tmp_path)
    monkeypatch.chdir(project)
    model = _model(project, "fixtures")
    target = project / "models" / "marts" / "rugby" / "_rugby__docs.md"
    target.write_text("{% docs fixtures %}\nExisting docs.\n{% enddocs %}\n")

    result = write_docs_block(
        model,
        DocsResult("Mart description.", "Generated docs.", {}),
        _config(),
        dry_run=False,
    )

    assert result.changed is False
    assert target.read_text().count("{% docs fixtures %}") == 1


def test_write_docs_block_dry_run_does_not_write(tmp_path, monkeypatch):
    project = _copy_project(tmp_path)
    monkeypatch.chdir(project)
    model = _model(project, "fixtures")
    target = project / "models" / "marts" / "rugby" / "_rugby__docs.md"

    result = write_docs_block(
        model,
        DocsResult("Mart description.", "Generated docs.", {}),
        _config(),
        dry_run=True,
    )

    assert result.changed is True
    assert target.exists() is False
