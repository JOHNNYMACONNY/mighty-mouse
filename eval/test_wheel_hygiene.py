import io
from pathlib import Path
import zipfile

import pytest

try:
    import tomllib
except ModuleNotFoundError:  # Python 3.10
    import tomli as tomllib


def _assert_clean_wheel(path: Path) -> None:
    with zipfile.ZipFile(path) as archive:
        contaminated = [
            name for name in archive.namelist()
            if Path(name).name.startswith("._")
        ]
    assert contaminated == []


@pytest.mark.parametrize("config_path", [Path("pyproject.toml"), Path("mcp/pyproject.toml")])
def test_packaging_excludes_macos_appledouble_files(config_path):
    config = tomllib.loads(config_path.read_text(encoding="utf-8"))
    patterns = config["tool"]["setuptools"]["exclude-package-data"]["*"]
    assert "._*" in patterns
    assert "*/._*" in patterns


def test_wheel_hygiene_check_rejects_contaminated_archive(tmp_path):
    wheel = tmp_path / "fixture.whl"
    with zipfile.ZipFile(wheel, "w") as archive:
        archive.writestr("package/__init__.py", "")
        archive.writestr("package/._module.py", "AppleDouble")
    with pytest.raises(AssertionError):
        _assert_clean_wheel(wheel)


def test_source_distributions_include_their_build_backends():
    assert "include build_backend.py" in Path("MANIFEST.in").read_text().splitlines()
    assert "include build_backend.py" in Path("mcp/MANIFEST.in").read_text().splitlines()
    assert '"build_backend.py"' in Path("build_backend.py").read_text()
    assert '"build_backend.py"' in Path("mcp/build_backend.py").read_text()
    assert '"README.md"' in Path("mcp/build_backend.py").read_text()


@pytest.mark.parametrize("backend_path", [Path("build_backend.py"), Path("mcp/build_backend.py")])
def test_build_backends_support_editable_installs(backend_path):
    source = backend_path.read_text()
    assert "def build_editable(" in source
    assert "def get_requires_for_build_editable(" in source
    assert "def prepare_metadata_for_build_editable(" in source


def test_source_date_epoch_parsing(monkeypatch):
    import importlib.util
    import build_backend

    spec = importlib.util.spec_from_file_location(
        "mcp_build_backend", Path("mcp/build_backend.py")
    )
    mcp_backend = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mcp_backend)

    for mod in (build_backend, mcp_backend):
        monkeypatch.delenv("SOURCE_DATE_EPOCH", raising=False)
        assert mod._parse_source_date_epoch() is None

        monkeypatch.setenv("SOURCE_DATE_EPOCH", "")
        assert mod._parse_source_date_epoch() is None

        monkeypatch.setenv("SOURCE_DATE_EPOCH", "1787434999")
        assert mod._parse_source_date_epoch() == 1787434999

        monkeypatch.setenv("SOURCE_DATE_EPOCH", "invalid")
        with pytest.raises(ValueError, match="Invalid SOURCE_DATE_EPOCH"):
            mod._parse_source_date_epoch()

        monkeypatch.setenv("SOURCE_DATE_EPOCH", "-100")
        with pytest.raises(ValueError, match="Invalid negative"):
            mod._parse_source_date_epoch()


def test_sdist_normalization_is_deterministic(tmp_path):
    import gzip
    import hashlib
    import tarfile
    import build_backend

    archive1 = tmp_path / "pkg1.tar.gz"
    archive2 = tmp_path / "pkg2.tar.gz"

    for path, mod_offset, file_mode, dir_mode in [
        (archive1, 10, 0o600, 0o700),
        (archive2, 50, 0o664, 0o775),
    ]:
        tar_path = tmp_path / f"temp_{mod_offset}.tar"
        with tarfile.open(tar_path, "w") as tar:
            dir_info = tarfile.TarInfo(name="pkg")
            dir_info.type = tarfile.DIRTYPE
            dir_info.mode = dir_mode
            dir_info.mtime = 1000000 + mod_offset
            tar.addfile(dir_info)

            data = b"def hello(): pass\n"
            info = tarfile.TarInfo(name="pkg/hello.py")
            info.size = len(data)
            info.mode = file_mode
            info.mtime = 1000000 + mod_offset
            tar.addfile(info, io.BytesIO(data))
        with open(path, "wb") as f_out:
            with gzip.GzipFile(
                filename="orig.tar", mode="wb", fileobj=f_out, mtime=mod_offset
            ) as gz_out:
                gz_out.write(tar_path.read_bytes())

    epoch = 1787434999
    build_backend._normalize_sdist_archive(archive1, epoch)
    build_backend._normalize_sdist_archive(archive2, epoch)

    h1 = hashlib.sha256(archive1.read_bytes()).hexdigest()
    h2 = hashlib.sha256(archive2.read_bytes()).hexdigest()
    assert h1 == h2

    with gzip.GzipFile(archive1, "rb") as gz_in:
        with tarfile.open(fileobj=gz_in, mode="r:*") as tar_in:
            for m in tar_in.getmembers():
                if m.isdir():
                    assert m.mode == 0o755
                else:
                    assert m.mode == 0o644


def test_cross_umask_build_reproducibility(tmp_path, monkeypatch):
    import hashlib
    import subprocess
    import sys

    monkeypatch.setenv("SOURCE_DATE_EPOCH", "1787434999")

    dist_022 = tmp_path / "dist_022"
    dist_077 = tmp_path / "dist_077"
    dist_022.mkdir()
    dist_077.mkdir()

    subprocess.run(
        f"umask 022 && {sys.executable} -m build --wheel --sdist "
        f"--outdir {dist_022} .",
        shell=True,
        check=True,
        capture_output=True,
    )
    subprocess.run(
        f"umask 077 && {sys.executable} -m build --wheel --sdist "
        f"--outdir {dist_077} .",
        shell=True,
        check=True,
        capture_output=True,
    )

    h_022 = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in dist_022.iterdir()
        if p.is_file()
    }
    h_077 = {
        p.name: hashlib.sha256(p.read_bytes()).hexdigest()
        for p in dist_077.iterdir()
        if p.is_file()
    }
    assert len(h_022) == 2
    assert h_022 == h_077
