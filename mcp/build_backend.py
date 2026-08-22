"""Sanitized PEP 517 backend for external-volume macOS checkouts."""

from __future__ import annotations

import gzip
import io
import os
from pathlib import Path
import shutil
import tarfile
import tempfile

_ROOT = Path(__file__).resolve().parent
_RELEASE_INPUTS = (
    "pyproject.toml",
    "MANIFEST.in",
    "build_backend.py",
    "README.md",
    "src",
)


def _get_setuptools():
    from setuptools import build_meta
    return build_meta


def _parse_source_date_epoch() -> int | None:
    raw = os.environ.get("SOURCE_DATE_EPOCH")
    if raw is None or raw == "":
        return None
    try:
        epoch = int(raw)
    except ValueError:
        raise ValueError(f"Invalid SOURCE_DATE_EPOCH: {raw!r}") from None
    if epoch < 0:
        raise ValueError(f"Invalid negative SOURCE_DATE_EPOCH: {raw!r}")
    return epoch


def _normalize_sdist_archive(archive_path: Path, epoch: int) -> None:
    with gzip.GzipFile(archive_path, "rb") as gz_in:
        with tarfile.open(fileobj=gz_in, mode="r:*") as tar_in:
            members = tar_in.getmembers()
            member_data = []
            for m in members:
                content = tar_in.extractfile(m).read() if m.isfile() else None
                member_data.append((m, content))

    tar_buf = io.BytesIO()
    with tarfile.open(
        fileobj=tar_buf, mode="w", format=tarfile.PAX_FORMAT
    ) as tar_out:
        for m, content in member_data:
            m.mtime = epoch
            m.uid = 0
            m.gid = 0
            m.uname = ""
            m.gname = ""
            m.pax_headers = {}
            if m.isdir():
                m.mode = 0o755
            elif m.issym() or m.islnk():
                m.mode = 0o777
            else:
                m.mode = 0o644
            if content is not None:
                m.size = len(content)
                tar_out.addfile(m, io.BytesIO(content))
            else:
                tar_out.addfile(m)

    tar_bytes = tar_buf.getvalue()
    with open(archive_path, "wb") as f_out:
        with gzip.GzipFile(
            filename="", mode="wb", fileobj=f_out, mtime=epoch
        ) as gz_out:
            gz_out.write(tar_bytes)


def _ignore(_directory: str, names: list[str]) -> set[str]:
    return {
        name for name in names
        if name.startswith("._") or name == "__pycache__" or name.endswith(".egg-info")
    }


def _stage() -> tempfile.TemporaryDirectory:
    temporary = tempfile.TemporaryDirectory(prefix="mighty-mouse-mcp-build-")
    destination = Path(temporary.name)
    for relative in _RELEASE_INPUTS:
        source = _ROOT / relative
        target = destination / relative
        if source.is_dir():
            shutil.copytree(source, target, ignore=_ignore)
        elif source.is_file():
            shutil.copyfile(source, target)
    for root, dirs, files in os.walk(destination):
        for d in dirs:
            os.chmod(Path(root) / d, 0o755)
        for f in files:
            os.chmod(Path(root) / f, 0o644)
    return temporary


def _staged_call(function, *args, **kwargs):
    output_directory = Path(args[0]).resolve() if args else None
    if output_directory is not None:
        args = (str(output_directory), *args[1:])
    previous_umask = os.umask(0o022)
    try:
        with _stage() as temporary:
            previous = Path.cwd()
            os.chdir(temporary)
            try:
                return function(*args, **kwargs)
            finally:
                os.chdir(previous)
    finally:
        os.umask(previous_umask)


def build_wheel(
    wheel_directory, config_settings=None, metadata_directory=None
):
    _parse_source_date_epoch()
    return _staged_call(
        _get_setuptools().build_wheel,
        wheel_directory,
        config_settings,
        metadata_directory,
    )


def build_sdist(sdist_directory, config_settings=None):
    epoch = _parse_source_date_epoch()
    result = _staged_call(
        _get_setuptools().build_sdist, sdist_directory, config_settings
    )
    if epoch is not None:
        archive_path = Path(sdist_directory) / result
        _normalize_sdist_archive(archive_path, epoch)
    return result


def get_requires_for_build_wheel(config_settings=None):
    return _get_setuptools().get_requires_for_build_wheel(config_settings)


def get_requires_for_build_sdist(config_settings=None):
    return _get_setuptools().get_requires_for_build_sdist(config_settings)


def prepare_metadata_for_build_wheel(metadata_directory, config_settings=None):
    return _staged_call(
        _get_setuptools().prepare_metadata_for_build_wheel,
        metadata_directory,
        config_settings,
    )


# Editable installs must reference the live checkout rather than the temporary
# release staging tree, so delegate the PEP 660 hooks directly to setuptools.
def build_editable(wheel_directory, config_settings=None, metadata_directory=None):
    return _get_setuptools().build_editable(
        wheel_directory,
        config_settings,
        metadata_directory,
    )


def get_requires_for_build_editable(config_settings=None):
    return _get_setuptools().get_requires_for_build_editable(config_settings)


def prepare_metadata_for_build_editable(metadata_directory, config_settings=None):
    return _get_setuptools().prepare_metadata_for_build_editable(
        metadata_directory,
        config_settings,
    )
