"""Build a local, explicit-allowlist App artifact. Never contacts Databricks."""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import subprocess

# Destination -> source, relative to the repository. No glob or directory copying.
FILES = {
    "app.yaml": "apps/rag_chat/app.yaml",
    "requirements.txt": "apps/rag_chat/requirements.txt",
    "apps/rag_chat/app.py": "apps/rag_chat/app.py",
    **{f"src/analytics_ai/{name}.py": f"src/analytics_ai/{name}.py" for name in (
        "__init__", "rag_clients", "rag_config", "rag_databricks", "rag_documents",
        "rag_endpoint", "rag_generation", "rag_prompt", "rag_service",
    )},
}


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def git_metadata(root: Path) -> dict:
    def git(*args):
        return subprocess.check_output(["git", "--no-optional-locks", "-C", str(root), *args],
                                       text=True, stderr=subprocess.DEVNULL).strip()
    try:
        return {"commit": git("rev-parse", "HEAD"),
                "dirty": bool(git("status", "--porcelain", "--untracked-files=normal"))}
    except (OSError, subprocess.CalledProcessError):
        return {"commit": None, "dirty": None}


def build_release(root: Path, destination: Path) -> dict:
    root = root.resolve()
    # Refuse reuse even for an empty directory or a dangling symlink.
    if destination.exists() or destination.is_symlink():
        raise ValueError("Destination already exists; select a new release directory")
    if any(parent.is_symlink() for parent in destination.absolute().parents):
        # /tmp may itself be a system symlink: callers can resolve its parent first.
        raise ValueError("Destination parents must not be symlinks")
    payload = {}
    entries = []
    for target, source in sorted(FILES.items()):
        path = root / source
        if any(part.is_symlink() for part in [path, *path.parents] if part != root and root in part.parents):
            raise ValueError(f"Symlink not allowed: {source}")
        if not path.is_file() or not path.resolve().is_relative_to(root):
            raise ValueError(f"Missing or unsafe source: {source}")
        data = path.read_bytes()
        payload[target] = data
        entries.append({"path": target, "source": source, "size_bytes": len(data), "sha256": digest(data)})
    manifest = {
        "schema_version": 1,
        "git": git_metadata(root),
        "payload_sha256": digest(json.dumps(entries, sort_keys=True, separators=(",", ":")).encode()),
        "files": entries,
        "note": "Hashes describe actual working-tree bytes, including uncommitted files. release.json does not hash itself.",
    }
    # All sources are validated/read before creating the output. Never overwrite.
    destination.mkdir(parents=True, exist_ok=False)
    for target, data in payload.items():
        path = destination / target
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
    (destination / "release.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return manifest


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=Path("build/rag_chat_app"))
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    manifest = build_release(root, args.output)
    print(json.dumps({"output": str(args.output.resolve()), **manifest}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
