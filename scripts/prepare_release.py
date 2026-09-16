#!/usr/bin/env python3
"""Prepare a Harbor dataset overlay without modifying upstream task content."""

from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import tomllib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
UPSTREAM_COMMIT = "9ab14d039f2475b158634d37ef91c3d8378a13ca"


def task_hashes(root: Path) -> dict[str, str]:
    return {
        path.relative_to(root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
        for path in sorted((root / "tasks").rglob("*"))
        if path.is_file()
        and "__pycache__" not in path.parts
        and path.suffix != ".pyc"
        and path.name != ".DS_Store"
    }


def prepare(
    output: Path,
    image: str,
    version: str,
    *,
    harbor_commit: str,
    allow_dirty: bool = False,
) -> dict:
    if not re.fullmatch(r"[0-9a-f]{40}", harbor_commit):
        raise ValueError("Harbor adapter must use an immutable 40-character commit SHA")
    if not re.fullmatch(r"[a-z0-9][a-z0-9./_-]*@sha256:[0-9a-f]{64}", image):
        raise ValueError(
            "Runtime image must use an immutable repository@sha256:<64 hex> reference"
        )
    if not re.fullmatch(r"\d+\.\d+\.\d+", version):
        raise ValueError("Dataset version must have the form X.Y.Z")
    if output.exists():
        raise ValueError(f"Output already exists: {output}")
    commit = subprocess.check_output(
        ["git", "rev-parse", "HEAD"], cwd=ROOT, text=True
    ).strip()
    dirty = bool(
        subprocess.check_output(
            ["git", "status", "--porcelain"], cwd=ROOT, text=True
        ).strip()
    )
    if dirty and not allow_dirty:
        raise ValueError(
            "Commit the reviewed source before preparing a release (or use --allow-dirty for local validation)"
        )
    if subprocess.run(
        ["git", "diff", "--quiet", UPSTREAM_COMMIT, "--", "tasks"], cwd=ROOT
    ).returncode:
        raise ValueError("Task source differs from the pinned upstream commit")
    if subprocess.check_output(
        ["git", "ls-files", "--others", "--exclude-standard", "--", "tasks"],
        cwd=ROOT,
        text=True,
    ).strip():
        raise ValueError("Untracked task inputs must not enter a release")

    tasks = sorted((ROOT / "tasks").iterdir())
    if len(tasks) != 65 or not all(task.is_dir() for task in tasks):
        raise ValueError("Expected the pinned upstream set of 65 tasks")
    for task in tasks:
        config = tomllib.loads((task / "task.toml").read_text())
        if config["task"]["name"] != f"sop-tasks/{task.name}":
            raise ValueError(f"Unexpected task name: {task.name}")
        for relative in (
            "system_prompt.md",
            "instruction.md",
            "tests/rubrics.json",
            "tests/sop_verifier.py",
            "tests/test.sh",
            "environment/initial_external_services",
            "environment/initial_workspace",
        ):
            if not (task / relative).exists():
                raise ValueError(f"Missing task input: {task.name}/{relative}")
        if "docker_image" in config["environment"]:
            raise ValueError(
                f"Task {task.name} is already prepared; start from the source checkout"
            )

    original_hashes = task_hashes(ROOT)
    output.mkdir(parents=True)
    shutil.copytree(
        ROOT / "tasks",
        output / "tasks",
        ignore=shutil.ignore_patterns("__pycache__", "*.pyc", ".DS_Store"),
    )
    for task in tasks:
        target = output / "tasks" / task.name
        config_path = target / "task.toml"
        config_path.write_text(
            config_path.read_text().replace(
                "[environment]\n",
                f"[environment]\ndocker_image = {json.dumps(image)}\n",
                1,
            )
        )
        dockerfile = target / "environment" / "Dockerfile"
        dockerfile.write_text(
            dockerfile.read_text()
            .replace("FROM handbook_base", f"FROM {image}", 1)
            .rstrip()
            + "\n\nCOPY initial_workspace/ /environment/initial_workspace/\nCOPY initial_external_services/ /environment/initial_external_services/\n"
        )
        verifier = target / "tests" / "test.sh"
        # Dependencies are baked in the runtime. Keep all upstream verifier and
        # regression commands, but fail on infrastructure errors and export feedback.
        script = verifier.read_text().replace(
            "#!/bin/bash\n", "#!/bin/bash\nset -euo pipefail\n", 1
        )
        script = re.sub(
            r"^pip install openpyxl pdfplumber (?:pypdf reportlab )?python-docx 2>/dev/null$",
            "python -c 'import openpyxl, pdfplumber, pypdf, reportlab, docx'",
            script,
            flags=re.MULTILINE,
        )
        if "pip install" in script:
            raise ValueError(f"Unrecognized verifier dependency command in {task.name}")
        verifier.write_text(
            script.rstrip() + "\ncp /tests/results.json /logs/verifier/results.json\n"
        )

    registry = [
        {
            "name": "handbook",
            "version": version,
            "description": "HANDBOOK.md: 65 enterprise instruction-following tasks, official OpenHands harness and rubric scoring.",
            "tasks": [
                {"name": task.name, "path": f"tasks/{task.name}"} for task in tasks
            ],
        }
    ]
    (output / "registry.json").write_text(json.dumps(registry, indent=2) + "\n")
    generated_hashes = task_hashes(output)
    changed = [
        path
        for path in original_hashes
        if original_hashes[path] != generated_hashes.get(path)
    ]
    expected_suffixes = ("/task.toml", "/environment/Dockerfile", "/tests/test.sh")
    if (
        any(not path.endswith(expected_suffixes) for path in changed)
        or original_hashes.keys() != generated_hashes.keys()
    ):
        raise RuntimeError("Release preparation changed protected task content")
    manifest = {
        "dataset": "handbook",
        "version": version,
        "task_count": len(tasks),
        "source": {
            "repo": "https://github.com/Osmosis-AI/handbook",
            "commit": commit,
            "dirty": dirty,
        },
        "upstream": {
            "repo": "https://github.com/surge-ai/handbook",
            "commit": UPSTREAM_COMMIT,
        },
        "runtime_image": image,
        "harbor": {
            "repo": "https://github.com/Osmosis-AI/harbor",
            "commit": harbor_commit,
        },
        "agent_import_path": "adapters.handbook.agent:HandbookAgent",
        "upstream_task_sha256": original_hashes,
        "released_task_sha256": generated_hashes,
        "modified_files": changed,
    }
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
    return manifest


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", type=Path, required=True)
    parser.add_argument("--image", required=True)
    parser.add_argument("--version", required=True)
    parser.add_argument("--harbor-commit", required=True)
    parser.add_argument(
        "--allow-dirty",
        action="store_true",
        help="Local validation only; records dirty=true in the manifest",
    )
    args = parser.parse_args()
    manifest = prepare(
        args.output_dir,
        args.image,
        args.version,
        harbor_commit=args.harbor_commit,
        allow_dirty=args.allow_dirty,
    )
    print(f"Prepared {manifest['task_count']} tasks in {args.output_dir}")
