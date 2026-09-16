import importlib.util
import json
import tomllib
from pathlib import Path

import pytest
from harbor.models.registry import Registry

spec = importlib.util.spec_from_file_location(
    "prepare_release", Path(__file__).parents[2] / "scripts/prepare_release.py"
)
release = importlib.util.module_from_spec(spec)
spec.loader.exec_module(release)


def test_release_preserves_the_official_dataset(tmp_path):
    image = "ghcr.io/osmosis-ai/handbook-runtime@sha256:" + "a" * 64
    output = tmp_path / "dataset"
    manifest = release.prepare(
        output, image, "1.0.0", harbor_commit="b" * 40, allow_dirty=True
    )
    assert manifest["harbor"]["commit"] == "b" * 40
    registry = Registry.from_path(output / "registry.json")
    assert len(registry.datasets[0].tasks) == manifest["task_count"] == 65
    for task in registry.datasets[0].tasks:
        config = tomllib.loads((output / task.path / "task.toml").read_text())
        assert config["environment"]["docker_image"] == image
        assert config["task"]["name"] == f"sop-tasks/{task.name}"
        assert json.loads((output / task.path / "tests/rubrics.json").read_text())
        verifier = (output / task.path / "tests/test.sh").read_text()
        assert "pip install" not in verifier
        assert "cp /tests/results.json /logs/verifier/results.json" in verifier
    assert len(manifest["modified_files"]) == 65 * 3
    with pytest.raises(ValueError, match="already exists"):
        release.prepare(
            output, image, "1.0.0", harbor_commit="b" * 40, allow_dirty=True
        )


def test_release_rejects_mutable_images(tmp_path):
    with pytest.raises(ValueError, match="immutable"):
        release.prepare(
            tmp_path / "dataset",
            "handbook:latest",
            "1.0.0",
            harbor_commit="b" * 40,
            allow_dirty=True,
        )


def test_release_rejects_mutable_adapter_refs(tmp_path):
    with pytest.raises(ValueError, match="immutable.*commit SHA"):
        release.prepare(
            tmp_path / "dataset", "handbook:latest", "1.0.0", harbor_commit="adapters"
        )
