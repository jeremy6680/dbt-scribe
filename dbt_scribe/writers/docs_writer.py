from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

from dbt_scribe.analyzer import EnrichedModel, Layer
from dbt_scribe.config import ScribeConfig
from dbt_scribe.generators.docs_generator import DocsResult


@dataclass(frozen=True)
class WriterResult:
    path: Path
    changed: bool
    content: str | None = None


def write_docs_block(
    model: EnrichedModel,
    docs_result: DocsResult,
    config: ScribeConfig,
    dry_run: bool,
) -> WriterResult:
    path = _docs_path(model, config.model_root)
    block_name = model.name
    existing_content = path.read_text() if path.exists() else ""

    if _has_docs_block(existing_content, block_name):
        return WriterResult(path=path.resolve(), changed=False, content=existing_content)

    block = _format_docs_block(block_name, docs_result.docs_block_content)
    new_content = _append_block(existing_content, block)
    if not dry_run:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(new_content)
    return WriterResult(path=path.resolve(), changed=True, content=new_content)


def _docs_path(model: EnrichedModel, model_root: str = "models") -> Path:
    model_path = Path(model_root) / model.path
    if model.layer is Layer.STAGING and len(model.fqn) >= 3:
        filename = f"_{model.fqn[2]}__docs.md"
    elif model.layer is Layer.INTERMEDIATE and len(model.fqn) >= 3:
        filename = f"_int_{model.fqn[2]}__docs.md"
    elif len(model.fqn) >= 3:
        filename = f"_{model.fqn[2]}__docs.md"
    else:
        filename = f"_{model.name}__docs.md"
    return model_path.parent / filename


def _has_docs_block(content: str, block_name: str) -> bool:
    pattern = rf"{{%\s*docs\s+{re.escape(block_name)}\s*%}}"
    return re.search(pattern, content) is not None


def _format_docs_block(block_name: str, content: str) -> str:
    return f"{{% docs {block_name} %}}\n{content.rstrip()}\n{{% enddocs %}}\n"


def _append_block(existing_content: str, block: str) -> str:
    if not existing_content:
        return block
    return f"{existing_content.rstrip()}\n\n{block}"
