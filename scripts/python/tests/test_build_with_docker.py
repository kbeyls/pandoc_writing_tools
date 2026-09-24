# SPDX-FileCopyrightText: <text>Copyright 2026 Arm Limited and/or its
# affiliates <open-source-office@arm.com></text>
# SPDX-License-Identifier: MIT

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
BUILD_WRAPPER = REPOSITORY_ROOT / "examples/feature-demo/build_with_docker.sh"
DOCKERFILE = REPOSITORY_ROOT / "docker/Dockerfile"


def run_wrapper_with_fake_docker(tmp_path: Path, *arguments: str) -> list[list[str]]:
    bin_directory = tmp_path / "bin"
    bin_directory.mkdir()
    calls_path = tmp_path / "docker-calls.jsonl"
    fake_docker = bin_directory / "docker"
    fake_docker.write_text(
        "#!/usr/bin/env python3\n"
        "import json\n"
        "import os\n"
        "import sys\n"
        "with open(os.environ['DOCKER_CALLS'], 'a', encoding='utf-8') as calls:\n"
        "    calls.write(json.dumps(sys.argv[1:]) + '\\n')\n",
        encoding="utf-8",
    )
    fake_docker.chmod(0o755)

    environment = os.environ.copy()
    environment["PATH"] = f"{bin_directory}{os.pathsep}{environment['PATH']}"
    environment["DOCKER_CALLS"] = str(calls_path)

    subprocess.run(
        [str(BUILD_WRAPPER), *arguments],
        cwd=REPOSITORY_ROOT,
        env=environment,
        check=True,
    )

    return [json.loads(line) for line in calls_path.read_text().splitlines()]


def test_wrapper_builds_from_repository_root_and_forwards_default_target(tmp_path):
    calls = run_wrapper_with_fake_docker(tmp_path)

    assert calls[0] == [
        "build",
        "-f",
        str(DOCKERFILE),
        "-t",
        "pandoc_writing_tools_build",
        str(REPOSITORY_ROOT),
    ]

    run_arguments = calls[1]
    assert run_arguments[:2] == ["run", "--rm"]
    assert any(argument.startswith("--user=") for argument in run_arguments)
    assert [
        "--mount",
        f"type=bind,source={REPOSITORY_ROOT},target=/src",
    ] == run_arguments[3:5]
    assert run_arguments[-4:] == [
        "pandoc_writing_tools_build",
        "-C",
        "examples/feature-demo",
        "all",
    ]
    assert not any("/tmp/uv-cache" in argument for argument in run_arguments)


def test_wrapper_forwards_explicit_make_arguments(tmp_path):
    calls = run_wrapper_with_fake_docker(tmp_path, "html", "VERBOSE=1")

    assert calls[1][-5:] == [
        "pandoc_writing_tools_build",
        "-C",
        "examples/feature-demo",
        "html",
        "VERBOSE=1",
    ]


def test_dockerfile_bakes_locked_dependencies_before_copying_entrypoint():
    dockerfile = DOCKERFILE.read_text(encoding="utf-8")

    dependency_copy = dockerfile.index("COPY pyproject.toml uv.lock ./")
    dependency_sync = dockerfile.index("uv sync --locked --no-install-project")
    entrypoint_copy = dockerfile.index("COPY docker/entrypoint.sh /entrypoint.sh")

    assert dependency_copy < dependency_sync < entrypoint_copy
    assert "UV_PROJECT_ENVIRONMENT=/opt/pandoc_writing_tools_venv" in dockerfile
    assert "UV_PYTHON=/usr/bin/python3" in dockerfile
    assert "UV_PYTHON_DOWNLOADS=never" in dockerfile
    assert "--mount=type=cache,target=/root/.cache/uv" in dockerfile
    assert "UV_CACHE_DIR=/root/.cache/uv" in dockerfile
    assert "ENV UV_NO_SYNC=1" in dockerfile


def test_root_dockerignore_excludes_local_and_generated_state():
    ignored_paths = (REPOSITORY_ROOT / ".dockerignore").read_text().splitlines()

    assert ".git" in ignored_paths
    assert ".venv" in ignored_paths
    assert ".uv-cache" in ignored_paths
    assert ".pytest_cache" in ignored_paths
    assert ".pytest-tmp" in ignored_paths
    assert "examples/feature-demo/build" in ignored_paths
