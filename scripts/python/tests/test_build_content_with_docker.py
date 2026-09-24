# SPDX-FileCopyrightText: <text>Copyright 2026 Arm Limited and/or its
# affiliates <open-source-office@arm.com></text>
# SPDX-License-Identifier: MIT

from __future__ import annotations

import json
import os
import subprocess
from pathlib import Path

import pytest


REPOSITORY_ROOT = Path(__file__).resolve().parents[3]
HELPER = REPOSITORY_ROOT / "docker/build_content_with_docker.sh"
TOOLS_DOCKERFILE = REPOSITORY_ROOT / "docker/Dockerfile"
CONTENT_DOCKERFILE = REPOSITORY_ROOT / "docker/content.Dockerfile"


def install_fake_docker(tmp_path: Path) -> tuple[Path, Path]:
    bin_directory = tmp_path / "fake bin"
    bin_directory.mkdir()
    calls_path = tmp_path / "docker-calls.jsonl"
    fake_docker = bin_directory / "docker"
    fake_docker.write_text(
        "#!/usr/bin/env python3\n"
        "import json\n"
        "import os\n"
        "import pathlib\n"
        "import sys\n"
        "arguments = sys.argv[1:]\n"
        "record = {'arguments': arguments}\n"
        "if any(arg.endswith('/docker/content.Dockerfile') for arg in arguments):\n"
        "    context = pathlib.Path(arguments[-1])\n"
        "    record['context'] = {\n"
        "        path.name: path.read_text(encoding='utf-8')\n"
        "        for path in sorted(context.iterdir())\n"
        "    }\n"
        "with open(os.environ['DOCKER_CALLS'], 'a', encoding='utf-8') as calls:\n"
        "    calls.write(json.dumps(record) + '\\n')\n",
        encoding="utf-8",
    )
    fake_docker.chmod(0o755)
    return bin_directory, calls_path


def run_helper(
    tmp_path: Path,
    content_root: Path,
    *make_arguments: str,
    base_dockerfile: str | None = None,
    check: bool = True,
) -> tuple[subprocess.CompletedProcess[str], list[dict[str, object]]]:
    bin_directory, calls_path = install_fake_docker(tmp_path)
    environment = os.environ.copy()
    environment["PATH"] = f"{bin_directory}{os.pathsep}{environment['PATH']}"
    environment["DOCKER_CALLS"] = str(calls_path)

    command = [str(HELPER), "--content-root", str(content_root)]
    if base_dockerfile is not None:
        command.extend(["--base-dockerfile", base_dockerfile])
    command.append("--")
    command.extend(make_arguments)

    result = subprocess.run(
        command,
        cwd=tmp_path,
        env=environment,
        check=check,
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    calls = []
    if calls_path.exists():
        calls = [json.loads(line) for line in calls_path.read_text().splitlines()]
    return result, calls


def assert_tools_build(arguments: list[str]) -> None:
    assert arguments == [
        "build",
        "-f",
        str(TOOLS_DOCKERFILE),
        "-t",
        "pandoc_writing_tools_build",
        str(REPOSITORY_ROOT),
    ]


def assert_runtime_call(
    arguments: list[str],
    content_root: Path,
    expected_image_prefix: str,
    expected_make_arguments: list[str],
) -> str:
    assert arguments[:2] == ["run", "--rm"]
    assert any(argument.startswith("--user=") for argument in arguments)
    assert ["--env", "HOME=/tmp"] == arguments[3:5]
    assert [
        "--mount",
        f"type=bind,source={content_root.resolve()},target=/src",
    ] == arguments[5:7]
    image = arguments[7]
    assert image.startswith(expected_image_prefix)
    assert arguments[8:] == expected_make_arguments
    assert not any("/tmp/uv-cache" in argument for argument in arguments)
    return image


def test_repository_without_python_metadata_runs_tools_image(tmp_path: Path):
    content_root = tmp_path / "content without python"
    content_root.mkdir()

    _, calls = run_helper(tmp_path, content_root)

    assert len(calls) == 2
    assert_tools_build(calls[0]["arguments"])
    image = assert_runtime_call(
        calls[1]["arguments"],
        content_root,
        "pandoc_writing_tools_build",
        ["all"],
    )
    assert image == "pandoc_writing_tools_build"


def test_complete_python_metadata_builds_isolated_content_layer(tmp_path: Path):
    content_root = tmp_path / "content with python"
    content_root.mkdir()
    (content_root / "pyproject.toml").write_text(
        "[project]\nname = 'example'\nversion = '0.1.0'\n",
        encoding="utf-8",
    )
    (content_root / "uv.lock").write_text(
        "version = 1\nrevision = 3\nrequires-python = '>=3.13'\n",
        encoding="utf-8",
    )

    _, calls = run_helper(tmp_path, content_root, "html", "VERBOSE=1")

    assert len(calls) == 3
    assert_tools_build(calls[0]["arguments"])

    content_build = calls[1]
    arguments = content_build["arguments"]
    assert arguments[:3] == [
        "build",
        "--build-arg",
        "BASE_IMAGE=pandoc_writing_tools_build",
    ]
    assert arguments[3:5] == ["-f", str(CONTENT_DOCKERFILE)]
    assert arguments[5] == "-t"
    assert arguments[6].startswith("pandoc_writing_tools_content_")
    assert content_build["context"] == {
        "pyproject.toml": "[project]\nname = 'example'\nversion = '0.1.0'\n",
        "uv.lock": "version = 1\nrevision = 3\nrequires-python = '>=3.13'\n",
    }

    runtime_image = assert_runtime_call(
        calls[2]["arguments"],
        content_root,
        "pandoc_writing_tools_content_",
        ["html", "VERBOSE=1"],
    )
    assert runtime_image == arguments[6]
    assert not Path(arguments[-1]).exists()


@pytest.mark.parametrize(
    ("present_file", "missing_file"),
    [("pyproject.toml", "uv.lock"), ("uv.lock", "pyproject.toml")],
)
def test_incomplete_python_metadata_fails_before_docker(
    tmp_path: Path,
    present_file: str,
    missing_file: str,
):
    content_root = tmp_path / "incomplete content"
    content_root.mkdir()
    (content_root / present_file).write_text("placeholder\n", encoding="utf-8")

    result, calls = run_helper(tmp_path, content_root, check=False)

    assert result.returncode != 0
    assert missing_file in result.stderr
    assert calls == []


def test_custom_base_is_built_before_content_dependencies(tmp_path: Path):
    content_root = tmp_path / "custom content"
    (content_root / "docker").mkdir(parents=True)
    custom_dockerfile = content_root / "docker/Custom.Dockerfile"
    custom_dockerfile.write_text(
        "ARG BASE_IMAGE=pandoc_writing_tools_build\n"
        "FROM ${BASE_IMAGE}\n"
        "RUN touch /opt/custom-marker\n",
        encoding="utf-8",
    )
    (content_root / "pyproject.toml").write_text(
        "[project]\nname = 'custom'\nversion = '0.1.0'\n",
        encoding="utf-8",
    )
    (content_root / "uv.lock").write_text(
        "version = 1\nrevision = 3\nrequires-python = '>=3.13'\n",
        encoding="utf-8",
    )

    _, calls = run_helper(
        tmp_path,
        content_root,
        "pdf",
        base_dockerfile="docker/Custom.Dockerfile",
    )

    assert len(calls) == 4
    assert_tools_build(calls[0]["arguments"])

    custom_arguments = calls[1]["arguments"]
    assert custom_arguments[:3] == [
        "build",
        "--build-arg",
        "BASE_IMAGE=pandoc_writing_tools_build",
    ]
    assert custom_arguments[3:5] == ["-f", str(custom_dockerfile)]
    assert custom_arguments[5] == "-t"
    assert custom_arguments[6].startswith("pandoc_writing_tools_custom_")
    assert custom_arguments[7] == str(content_root.resolve())

    content_arguments = calls[2]["arguments"]
    assert content_arguments[2] == f"BASE_IMAGE={custom_arguments[6]}"
    assert content_arguments[6].startswith("pandoc_writing_tools_content_")

    runtime_image = assert_runtime_call(
        calls[3]["arguments"],
        content_root,
        "pandoc_writing_tools_content_",
        ["pdf"],
    )
    assert runtime_image == content_arguments[6]


def test_custom_base_without_python_metadata_runs_custom_image(tmp_path: Path):
    content_root = tmp_path / "custom only"
    content_root.mkdir()
    custom_dockerfile = content_root / "Dockerfile.custom"
    custom_dockerfile.write_text(
        "ARG BASE_IMAGE=pandoc_writing_tools_build\nFROM ${BASE_IMAGE}\n",
        encoding="utf-8",
    )

    _, calls = run_helper(
        tmp_path,
        content_root,
        base_dockerfile=str(custom_dockerfile),
    )

    assert len(calls) == 3
    custom_image = calls[1]["arguments"][6]
    assert custom_image.startswith("pandoc_writing_tools_custom_")
    runtime_image = assert_runtime_call(
        calls[2]["arguments"],
        content_root,
        "pandoc_writing_tools_custom_",
        ["all"],
    )
    assert runtime_image == custom_image


def test_content_dockerfile_preserves_inherited_entrypoint():
    dockerfile = CONTENT_DOCKERFILE.read_text(encoding="utf-8")

    assert "ARG BASE_IMAGE=pandoc_writing_tools_build" in dockerfile
    assert "FROM ${BASE_IMAGE}" in dockerfile
    assert "COPY pyproject.toml uv.lock ./" in dockerfile
    assert "--mount=type=cache,target=/root/.cache/uv" in dockerfile
    assert "env -u UV_NO_SYNC" in dockerfile
    assert "UV_CACHE_DIR=/root/.cache/uv" in dockerfile
    assert "uv sync --locked --no-install-project --inexact" in dockerfile
    assert "ENTRYPOINT" not in dockerfile
