"""Sync repository bookkeeping files after code or documentation changes."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

TRACKED_ROOTS = (
    ".github/workflows",
    "Adaptive hydraulic pump optimizer v2.md",
    "README.md",
    "ahpo_sim",
    "custom_components",
    "hacs.json",
    "pyproject.toml",
    "scripts",
)

GENERATED_FILES = {
    "CHANGELOG.md",
    "VERSION",
    "docs/.repo_sync_state.json",
    "docs/MEMORY_BANK.md",
}
IGNORED_TRACKED_PARTS = {"__pycache__"}
IGNORED_TRACKED_SUFFIXES = {".pyc", ".pyo"}

README_VERSION_PATTERN = re.compile(
    r"(^Repository version:\s*`)([^`]+)(`.*$)",
    flags=re.MULTILINE,
)
MEMORY_BANK_VERSION_PATTERN = re.compile(
    r"(^- Current repository version:\s*)(.+)$",
    flags=re.MULTILINE,
)
MEMORY_BANK_SYNC_PATTERN = re.compile(
    r"(^- Last synchronized:\s*)(.+)$",
    flags=re.MULTILINE,
)
PYPROJECT_VERSION_PATTERN = re.compile(
    r'(^version = ")([^"]+)(")$',
    flags=re.MULTILINE,
)
MANIFEST_VERSION_PATTERN = re.compile(
    r'(^  "version": ")([^"]+)(")$',
    flags=re.MULTILINE,
)
VERSION_PATTERN = re.compile(r"^(\d{4})\.(\d{2})\.(\d+)$")


@dataclass(frozen=True)
class SyncPaths:
    root: Path
    version: Path
    changelog: Path
    memory_bank: Path
    state: Path
    readme: Path
    pyproject: Path
    manifest: Path


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="Fail if repo metadata is out of sync.")
    return parser.parse_args()


def build_paths(root: Path) -> SyncPaths:
    return SyncPaths(
        root=root,
        version=root / "VERSION",
        changelog=root / "CHANGELOG.md",
        memory_bank=root / "docs" / "MEMORY_BANK.md",
        state=root / "docs" / ".repo_sync_state.json",
        readme=root / "README.md",
        pyproject=root / "pyproject.toml",
        manifest=root / "custom_components" / "adaptive_hydraulic_optimizer" / "manifest.json",
    )


def tracked_files(root: Path) -> list[Path]:
    paths: list[Path] = []
    for tracked_root in TRACKED_ROOTS:
        absolute = root / tracked_root
        if absolute.is_dir():
            for path in sorted(absolute.rglob("*")):
                if not path.is_file():
                    continue
                rel = path.relative_to(root).as_posix()
                if rel in GENERATED_FILES or any(part in IGNORED_TRACKED_PARTS for part in path.parts):
                    continue
                if path.suffix in IGNORED_TRACKED_SUFFIXES:
                    continue
                paths.append(path)
        elif absolute.is_file():
            rel = absolute.relative_to(root).as_posix()
            if rel not in GENERATED_FILES and absolute.suffix not in IGNORED_TRACKED_SUFFIXES:
                paths.append(absolute)
    return sorted(paths)


def file_hash(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def collect_file_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): file_hash(path)
        for path in tracked_files(root)
    }


def fingerprint_for(file_hashes: dict[str, str]) -> str:
    payload = "".join(f"{path}:{digest}\n" for path, digest in sorted(file_hashes.items()))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def read_state(path: Path) -> dict | None:
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def next_version(previous_version: str | None, now: datetime) -> str:
    prefix = f"{now.year:04d}.{now.month:02d}"
    if previous_version:
        match = VERSION_PATTERN.fullmatch(previous_version)
        if match and f"{match.group(1)}.{match.group(2)}" == prefix:
            return f"{prefix}.{int(match.group(3)) + 1}"
    return f"{prefix}.1"


def classify_changes(previous_hashes: dict[str, str], current_hashes: dict[str, str]) -> dict[str, list[str]]:
    previous_paths = set(previous_hashes)
    current_paths = set(current_hashes)
    added = sorted(current_paths - previous_paths)
    removed = sorted(previous_paths - current_paths)
    updated = sorted(
        path for path in previous_paths & current_paths
        if previous_hashes[path] != current_hashes[path]
    )
    return {"added": added, "updated": updated, "removed": removed}


def render_change_lines(changes: dict[str, list[str]]) -> str:
    lines: list[str] = []
    for label, paths in (
        ("Added", changes["added"]),
        ("Updated", changes["updated"]),
        ("Removed", changes["removed"]),
    ):
        if not paths:
            continue
        lines.append(f"### {label}")
        lines.extend(f"- `{path}`" for path in paths)
        lines.append("")
    if not lines:
        lines = ["### Updated", "- Repository bookkeeping refreshed.", ""]
    return "\n".join(lines).rstrip()


def prepend_changelog_entry(changelog_path: Path, version: str, now: datetime, changes: dict[str, list[str]]) -> str:
    header = "# Change History\n\n"
    entry = (
        f"## {version} - {now.date().isoformat()}\n"
        f"- Repository bookkeeping synchronized after tracked repository changes.\n\n"
        f"{render_change_lines(changes)}\n"
    )
    if changelog_path.exists():
        existing = changelog_path.read_text(encoding="utf-8")
        normalized = existing.lstrip()
        if normalized.startswith("# Change History"):
            body = normalized.split("\n", 1)[1].lstrip() if "\n" in normalized else ""
        else:
            body = normalized
        return header + entry + ("\n\n" + body if body else "")
    return header + entry


def replace_required(pattern: re.Pattern[str], text: str, replacement: str, file_label: str) -> str:
    updated, count = pattern.subn(replacement, text, count=1)
    if count != 1:
        raise ValueError(f"Could not update {file_label}")
    return updated


def render_synced_files(paths: SyncPaths, version: str, synced_at: str, changelog_text: str) -> dict[str, str]:
    readme_text = paths.readme.read_text(encoding="utf-8")
    readme_text = replace_required(
        README_VERSION_PATTERN,
        readme_text,
        rf"\g<1>{version}\g<3>",
        "README.md repository version line",
    )

    memory_bank_text = paths.memory_bank.read_text(encoding="utf-8")
    memory_bank_text = replace_required(
        MEMORY_BANK_VERSION_PATTERN,
        memory_bank_text,
        rf"\g<1>{version}",
        "docs/MEMORY_BANK.md version line",
    )
    memory_bank_text = replace_required(
        MEMORY_BANK_SYNC_PATTERN,
        memory_bank_text,
        rf"\g<1>{synced_at}",
        "docs/MEMORY_BANK.md last synchronized line",
    )

    pyproject_text = replace_required(
        PYPROJECT_VERSION_PATTERN,
        paths.pyproject.read_text(encoding="utf-8"),
        rf'\g<1>{version}\g<3>',
        "pyproject.toml version",
    )
    manifest_text = replace_required(
        MANIFEST_VERSION_PATTERN,
        paths.manifest.read_text(encoding="utf-8"),
        rf'\g<1>{version}\g<3>',
        "manifest.json version",
    )

    return {
        "README.md": readme_text,
        "docs/MEMORY_BANK.md": memory_bank_text,
        "pyproject.toml": pyproject_text,
        "custom_components/adaptive_hydraulic_optimizer/manifest.json": manifest_text,
        "VERSION": f"{version}\n",
        "CHANGELOG.md": changelog_text.rstrip() + "\n",
    }


def projected_file_hashes(current_hashes: dict[str, str], rendered_files: dict[str, str]) -> dict[str, str]:
    projected = dict(current_hashes)
    for relative_path, content in rendered_files.items():
        if relative_path in projected:
            projected[relative_path] = hashlib.sha256(content.encode("utf-8")).hexdigest()
    return projected


def write_files(paths: SyncPaths, rendered_files: dict[str, str], state_payload: dict) -> None:
    for relative_path, content in rendered_files.items():
        path = paths.root / relative_path
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(content, encoding="utf-8")
    paths.state.parent.mkdir(parents=True, exist_ok=True)
    paths.state.write_text(json.dumps(state_payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")


def file_content_matches(root: Path, rendered_files: dict[str, str], expected_state: dict) -> bool:
    for relative_path, expected_content in rendered_files.items():
        actual_path = root / relative_path
        if not actual_path.exists() or actual_path.read_text(encoding="utf-8") != expected_content:
            return False
    state_path = root / "docs" / ".repo_sync_state.json"
    expected_state_text = json.dumps(expected_state, indent=2, sort_keys=True) + "\n"
    return state_path.exists() and state_path.read_text(encoding="utf-8") == expected_state_text


def sync_metadata(root: Path, check: bool = False, now: datetime | None = None) -> bool:
    current_time = now or datetime.now(UTC)
    paths = build_paths(root)
    state = read_state(paths.state) or {}
    previous_hashes = state.get("file_hashes", {})
    current_hashes = collect_file_hashes(root)
    current_fingerprint = fingerprint_for(current_hashes)
    stored_fingerprint = state.get("fingerprint")
    current_version = state.get("version")

    if stored_fingerprint == current_fingerprint and current_version:
        changelog_text = paths.changelog.read_text(encoding="utf-8") if paths.changelog.exists() else "# Change History\n"
        rendered_files = render_synced_files(
            paths,
            current_version,
            state.get("synced_at", current_time.isoformat()),
            changelog_text,
        )
        final_hashes = projected_file_hashes(current_hashes, rendered_files)
        expected_state = {
            "file_hashes": final_hashes,
            "fingerprint": fingerprint_for(final_hashes),
            "synced_at": state.get("synced_at", current_time.isoformat()),
            "version": current_version,
        }
        if check:
            return file_content_matches(root, rendered_files, expected_state)
        if not file_content_matches(root, rendered_files, expected_state):
            write_files(paths, rendered_files, expected_state)
        return True

    new_version = next_version(current_version, current_time)
    changes = classify_changes(previous_hashes, current_hashes)
    changelog_text = prepend_changelog_entry(paths.changelog, new_version, current_time, changes)
    synced_at = current_time.isoformat()
    rendered_files = render_synced_files(paths, new_version, synced_at, changelog_text)
    final_hashes = projected_file_hashes(current_hashes, rendered_files)
    expected_state = {
        "file_hashes": final_hashes,
        "fingerprint": fingerprint_for(final_hashes),
        "synced_at": synced_at,
        "version": new_version,
    }
    if check:
        return False
    write_files(paths, rendered_files, expected_state)
    return True


def main() -> int:
    args = parse_args()
    root = Path(__file__).resolve().parents[1]
    ok = sync_metadata(root=root, check=args.check)
    if ok:
        return 0
    print("Repository metadata is out of sync. Run: python scripts/sync_repo_metadata.py")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
