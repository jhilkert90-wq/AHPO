from __future__ import annotations

import json
from datetime import UTC, datetime
from pathlib import Path

from scripts.sync_repo_metadata import classify_changes, next_version, sync_metadata


def _write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def test_next_version_increments_within_month() -> None:
    now = datetime(2026, 9, 27, tzinfo=UTC)
    assert next_version("2026.09.2", now) == "2026.09.3"
    assert next_version("2026.08.5", now) == "2026.09.1"
    assert next_version(None, now) == "2026.09.1"


def test_classify_changes_detects_add_update_remove() -> None:
    changes = classify_changes(
        {"a.py": "old", "b.py": "same"},
        {"b.py": "same", "c.py": "new", "a.py": "newer"},
    )
    assert changes == {
        "added": ["c.py"],
        "updated": ["a.py"],
        "removed": [],
    }


def test_sync_metadata_updates_repo_files(tmp_path: Path) -> None:
    _write(
        tmp_path / "README.md",
        "# Test Repo\n\nRepository version: `0.0.0` (tracked in `/VERSION`, `/CHANGELOG.md`, and `/docs/MEMORY_BANK.md`)\n",
    )
    _write(
        tmp_path / "Adaptive hydraulic pump optimizer v2.md",
        "# Spec\n",
    )
    _write(
        tmp_path / "pyproject.toml",
        '[project]\nname = "ahpo-sim"\nversion = "0.0.0"\n',
    )
    _write(
        tmp_path / "custom_components/adaptive_hydraulic_optimizer/manifest.json",
        '{\n  "domain": "adaptive_hydraulic_optimizer",\n  "name": "Adaptive Hydraulic Pump Optimizer",\n  "version": "0.0.0"\n}\n',
    )
    _write(
        tmp_path / "hacs.json",
        '{\n  "name": "Adaptive Hydraulic Pump Optimizer"\n}\n',
    )
    _write(tmp_path / ".github/workflows/ci.yml", "name: CI\n")
    _write(tmp_path / "scripts/__init__.py", "")
    _write(tmp_path / "scripts/sync_repo_metadata.py", 'print("placeholder")\n')
    _write(tmp_path / "ahpo_sim/__init__.py", "")
    _write(
        tmp_path / "docs/MEMORY_BANK.md",
        "# Memory Bank\n\n- Current repository version: 0.0.0\n- Last synchronized: pending\n",
    )
    _write(tmp_path / "VERSION", "0.0.0\n")
    _write(tmp_path / "CHANGELOG.md", "# Change History\n")

    now = datetime(2026, 9, 27, 14, 0, tzinfo=UTC)
    assert sync_metadata(tmp_path, now=now) is True

    version = (tmp_path / "VERSION").read_text(encoding="utf-8").strip()
    assert version == "2026.09.1"
    assert f'Repository version: `{version}`' in (tmp_path / "README.md").read_text(encoding="utf-8")
    assert f'version = "{version}"' in (tmp_path / "pyproject.toml").read_text(encoding="utf-8")
    assert f'"version": "{version}"' in (
        tmp_path / "custom_components/adaptive_hydraulic_optimizer/manifest.json"
    ).read_text(encoding="utf-8")
    changelog = (tmp_path / "CHANGELOG.md").read_text(encoding="utf-8")
    assert f"## {version} - 2026-09-27" in changelog
    assert "### Added" in changelog
    assert "- `README.md`" in changelog
    assert "- `VERSION`" not in changelog

    state = json.loads((tmp_path / "docs/.repo_sync_state.json").read_text(encoding="utf-8"))
    assert state["version"] == version
    assert sync_metadata(tmp_path, check=True, now=now) is True


def test_sync_metadata_check_fails_after_tracked_change(tmp_path: Path) -> None:
    _write(
        tmp_path / "README.md",
        "# Test Repo\n\nRepository version: `0.0.0` (tracked in `/VERSION`, `/CHANGELOG.md`, and `/docs/MEMORY_BANK.md`)\n",
    )
    _write(tmp_path / "Adaptive hydraulic pump optimizer v2.md", "# Spec\n")
    _write(tmp_path / "pyproject.toml", '[project]\nname = "ahpo-sim"\nversion = "0.0.0"\n')
    _write(
        tmp_path / "custom_components/adaptive_hydraulic_optimizer/manifest.json",
        '{\n  "domain": "adaptive_hydraulic_optimizer",\n  "name": "Adaptive Hydraulic Pump Optimizer",\n  "version": "0.0.0"\n}\n',
    )
    _write(tmp_path / "hacs.json", '{\n  "name": "Adaptive Hydraulic Pump Optimizer"\n}\n')
    _write(tmp_path / ".github/workflows/ci.yml", "name: CI\n")
    _write(tmp_path / "scripts/__init__.py", "")
    _write(tmp_path / "scripts/sync_repo_metadata.py", 'print("placeholder")\n')
    _write(tmp_path / "ahpo_sim/__init__.py", "")
    _write(
        tmp_path / "docs/MEMORY_BANK.md",
        "# Memory Bank\n\n- Current repository version: 0.0.0\n- Last synchronized: pending\n",
    )
    _write(tmp_path / "VERSION", "0.0.0\n")
    _write(tmp_path / "CHANGELOG.md", "# Change History\n")

    now = datetime(2026, 9, 27, 14, 0, tzinfo=UTC)
    assert sync_metadata(tmp_path, now=now) is True

    readme_path = tmp_path / "README.md"
    readme_path.write_text(
        readme_path.read_text(encoding="utf-8") + "\nNew tracked content.\n",
        encoding="utf-8",
    )

    assert sync_metadata(tmp_path, check=True, now=now) is False


def test_sync_metadata_ignores_pycache_artifacts(tmp_path: Path) -> None:
    _write(
        tmp_path / "README.md",
        "# Test Repo\n\nRepository version: `0.0.0` (tracked in `/VERSION`, `/CHANGELOG.md`, and `/docs/MEMORY_BANK.md`)\n",
    )
    _write(tmp_path / "Adaptive hydraulic pump optimizer v2.md", "# Spec\n")
    _write(tmp_path / "pyproject.toml", '[project]\nname = "ahpo-sim"\nversion = "0.0.0"\n')
    _write(
        tmp_path / "custom_components/adaptive_hydraulic_optimizer/manifest.json",
        '{\n  "domain": "adaptive_hydraulic_optimizer",\n  "name": "Adaptive Hydraulic Pump Optimizer",\n  "version": "0.0.0"\n}\n',
    )
    _write(tmp_path / "hacs.json", '{\n  "name": "Adaptive Hydraulic Pump Optimizer"\n}\n')
    _write(tmp_path / ".github/workflows/ci.yml", "name: CI\n")
    _write(tmp_path / "scripts/__init__.py", "")
    _write(tmp_path / "scripts/sync_repo_metadata.py", 'print("placeholder")\n')
    _write(tmp_path / "ahpo_sim/__init__.py", "")
    _write(
        tmp_path / "docs/MEMORY_BANK.md",
        "# Memory Bank\n\n- Current repository version: 0.0.0\n- Last synchronized: pending\n",
    )
    _write(tmp_path / "VERSION", "0.0.0\n")
    _write(tmp_path / "CHANGELOG.md", "# Change History\n")

    now = datetime(2026, 9, 27, 14, 0, tzinfo=UTC)
    assert sync_metadata(tmp_path, now=now) is True

    _write(tmp_path / "scripts/__pycache__/sync_repo_metadata.cpython-312.pyc", "bytecode")
    _write(tmp_path / "ahpo_sim/__pycache__/module.cpython-312.pyc", "bytecode")
    _write(tmp_path / "scripts/helper.pyo", "bytecode")

    assert sync_metadata(tmp_path, check=True, now=now) is True


def test_sync_metadata_filters_generated_paths_from_previous_state(tmp_path: Path) -> None:
    _write(
        tmp_path / "README.md",
        "# Test Repo\n\nRepository version: `0.0.0` (tracked in `/VERSION`, `/CHANGELOG.md`, and `/docs/MEMORY_BANK.md`)\n",
    )
    _write(tmp_path / "Adaptive hydraulic pump optimizer v2.md", "# Spec\n")
    _write(tmp_path / "pyproject.toml", '[project]\nname = "ahpo-sim"\nversion = "0.0.0"\n')
    _write(
        tmp_path / "custom_components/adaptive_hydraulic_optimizer/manifest.json",
        '{\n  "domain": "adaptive_hydraulic_optimizer",\n  "name": "Adaptive Hydraulic Pump Optimizer",\n  "version": "0.0.0"\n}\n',
    )
    _write(tmp_path / "hacs.json", '{\n  "name": "Adaptive Hydraulic Pump Optimizer"\n}\n')
    _write(tmp_path / ".github/workflows/ci.yml", "name: CI\n")
    _write(tmp_path / "scripts/__init__.py", "")
    _write(tmp_path / "scripts/sync_repo_metadata.py", 'print("placeholder")\n')
    _write(tmp_path / "ahpo_sim/__init__.py", "")
    _write(
        tmp_path / "docs/MEMORY_BANK.md",
        "# Memory Bank\n\n- Current repository version: 0.0.0\n- Last synchronized: pending\n",
    )
    _write(tmp_path / "VERSION", "0.0.0\n")
    _write(tmp_path / "CHANGELOG.md", "# Change History\n")

    now = datetime(2026, 9, 27, 14, 0, tzinfo=UTC)
    assert sync_metadata(tmp_path, now=now) is True

    state_path = tmp_path / "docs/.repo_sync_state.json"
    state = json.loads(state_path.read_text(encoding="utf-8"))
    state["file_hashes"]["CHANGELOG.md"] = "old"
    state["file_hashes"]["VERSION"] = "old"
    state["file_hashes"]["docs/MEMORY_BANK.md"] = "old"
    state_path.write_text(json.dumps(state), encoding="utf-8")

    _write(tmp_path / "scripts/sync_repo_metadata.py", 'print("changed")\n')
    assert sync_metadata(tmp_path, now=now) is True

    changelog = (tmp_path / "CHANGELOG.md").read_text(encoding="utf-8")
    assert "### Removed" not in changelog.split("## 2026.09.2 - 2026-09-27", 1)[1].split("##", 1)[0]
