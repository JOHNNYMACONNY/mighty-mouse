"""Build from a sanitized local staging tree.

macOS stores extended attributes as ``._*`` AppleDouble files on some external
volumes. Building directly in such a checkout can make setuptools mistake those
sidecars for Python modules. Staging only release inputs on the local temporary
filesystem keeps standard PEP 517 builds deterministic.
"""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import tempfile

from setuptools import build_meta as _setuptools


_ROOT = Path(__file__).resolve().parent
_RELEASE_INPUTS = (
    "pyproject.toml",
    "MANIFEST.in",
    "build_backend.py",
    "README.md",
    "LICENSE",
    "src",
)


def _ignore(_directory: str, names: list[str]) -> set[str]:
    return {
        name for name in names
        if name.startswith("._") or name == "__pycache__" or name.endswith(".egg-info")
    }


def _stage() -> tempfile.TemporaryDirectory:
    temporary = tempfile.TemporaryDirectory(prefix="mighty-mouse-build-")
    destination = Path(temporary.name)
    for relative in _RELEASE_INPUTS:
        source = _ROOT / relative
        target = destination / relative
        if source.is_dir():
            shutil.copytree(source, target, ignore=_ignore)
        elif source.is_file():
            shutil.copyfile(source, target)
    return temporary


def _staged_call(function, *args, **kwargs):
    wheel_or_sdist_directory = Path(args[0]).resolve() if args else None
    if wheel_or_sdist_directory is not None:
        args = (str(wheel_or_sdist_directory), *args[1:])
    with _stage() as temporary:
        previous = Path.cwd()
        os.chdir(temporary)
        try:
            return function(*args, **kwargs)
        finally:
            os.chdir(previous)


def build_wheel(wheel_directory, config_settings=None, metadata_directory=None):
    return _staged_call(
        _setuptools.build_wheel,
        wheel_directory,
        config_settings,
        metadata_directory,
    )


def build_sdist(sdist_directory, config_settings=None):
    return _staged_call(_setuptools.build_sdist, sdist_directory, config_settings)


def get_requires_for_build_wheel(config_settings=None):
    return _setuptools.get_requires_for_build_wheel(config_settings)


def get_requires_for_build_sdist(config_settings=None):
    return _setuptools.get_requires_for_build_sdist(config_settings)


def prepare_metadata_for_build_wheel(metadata_directory, config_settings=None):
    return _staged_call(
        _setuptools.prepare_metadata_for_build_wheel,
        metadata_directory,
        config_settings,
    )
