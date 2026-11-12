#!/usr/bin/env python3
"""Export a runnable source snapshot without credentials, local assets, or Git history."""
from __future__ import annotations

import argparse
from pathlib import Path
import re
import shutil
import subprocess
import zipfile

ROOT = Path(__file__).resolve().parents[1]
FILES = {
    ".env.example", ".gitignore", "README.md", "Makefile",
    "backend/.python-version", "backend/pyproject.toml", "backend/uv.lock",
    "frontend/.gitignore", "frontend/eslint.config.mjs", "frontend/next.config.ts",
    "frontend/package.json", "frontend/package-lock.json", "frontend/tsconfig.json", "frontend/postcss.config.mjs",
    "THIRD_PARTY_NOTICES.md",
    "fixtures/videos/.gitkeep",
    "scripts/package_submission.py", "LICENSE",
}


def public_file(name: str) -> bool:
    path = Path(name)
    if path.is_absolute() or ".." in path.parts or any(part in {"node_modules", "__pycache__", ".venv"} for part in path.parts):
        return False
    # The one supplied exercise example is intentionally distributed. All other
    # videos, recordings, databases and private media remain excluded.
    if name == "frontend/public/demos/squat-example.mp4":
        return True
    if name in FILES:
        return True
    if name.startswith("docs/licenses/") and path.suffix == ".txt":
        return True
    if any(name.startswith(prefix) for prefix in ("backend/app/", "backend/tests/")):
        return path.suffix == ".py"
    if any(name.startswith(prefix) for prefix in ("frontend/app/", "frontend/components/", "frontend/lib/")):
        return path.suffix in {".ts", ".tsx", ".css", ".ico"}
    if name.startswith("frontend/public/"):
        return path.suffix in {".svg", ".png", ".jpg", ".jpeg", ".webp", ".ico"}
    return name.startswith("fixtures/meta/") and path.suffix == ".json"


def local_keys() -> list[bytes]:
    """Compare output against local key values without logging or exporting them."""
    values = []
    environments = [p for p in ROOT.glob(".env*") if p.name != ".env.example"]
    environments += [ROOT / "backend/.env", ROOT / "frontend/.env.local"]
    for env in environments:
        if not env.is_file():
            continue
        for line in env.read_text().splitlines():
            match = re.match(r"\s*(?:export\s+)?([A-Z0-9_]*(?:KEY|TOKEN|SECRET|PASSWORD)(?:_HASH)?)\s*=\s*(.+)", line)
            if match:
                value = match[2].strip().strip("\"'")
                if len(value) >= 16:
                    values.append(value.encode())
            if line.startswith("Coach password: "):
                values.append(line.removeprefix("Coach password: ").encode())
    return values


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist/GhostRep-submission.zip")
    parser.add_argument("--directory", type=Path, help="Also write a clean, unpacked source directory")
    args = parser.parse_args()
    output = args.output.expanduser().resolve()
    if output.exists():
        parser.error("Output exists. Choose a new --output path to preserve the previous snapshot.")
    directory = args.directory.expanduser().resolve() if args.directory else None
    if directory and directory.exists():
        parser.error("Directory exists. Choose a new --directory path to preserve the previous snapshot.")
    # Include modified/new source; an extracted source snapshot also works without Git.
    in_git = (ROOT / ".git").exists() and shutil.which("git") and subprocess.run(
        ["git", "rev-parse", "--is-inside-work-tree"], cwd=ROOT, capture_output=True,
    ).returncode == 0
    if in_git:
        listed = subprocess.check_output(["git", "ls-files", "-c", "-o", "--exclude-standard", "-z"], cwd=ROOT)
        candidates = listed.decode().split("\0")
        # Include the selected setup files even under a local ignore policy.
        candidates.extend(FILES)
    else:
        candidates = list(FILES)
        for prefix in ("backend/app", "backend/tests", "frontend/app", "frontend/components", "frontend/lib", "frontend/public", "fixtures/meta", "docs/licenses"):
            candidates.extend(str(path.relative_to(ROOT)) for path in (ROOT / prefix).rglob("*") if path.is_file())
    names = sorted({name for name in candidates if name and public_file(name)})
    required = {"README.md", ".env.example", "LICENSE", "backend/app/main.py", "backend/uv.lock", "frontend/package-lock.json", "frontend/postcss.config.mjs"}
    if not required.issubset(names) or any(not (ROOT / name).is_file() for name in required):
        parser.error("Required source/setup files are missing.")
    keys = local_keys()
    sources = []
    for name in names:
        path = ROOT / name
        if not path.exists():
            continue
        if path.is_symlink() or not path.resolve().is_relative_to(ROOT.resolve()):
            parser.error(f"Refusing a symlink in the submission: {name}")
        data = path.read_bytes()
        private_key_marker = b"-----BEGIN " + b"PRIVATE KEY-----"
        if any(key in data for key in keys) or private_key_marker in data:
            parser.error(f"Credential material detected in {name}; no archive was written.")
        sources.append((name, path))
    output.parent.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for name, path in sources:
            archive.write(path, f"GhostRep/{name}")
    if directory:
        for name, path in sources:
            target = directory / name
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copyfile(path, target)
    print(f"Created {output} ({len(sources)} source/setup files)")
    if directory:
        print(f"Clean source directory: {directory}")
    print("No Git history, local recordings/data, dependencies, cached models, or internal notes included.")
    print("This snapshot does not remove data already present in the original repository's history.")


if __name__ == "__main__":
    main()
