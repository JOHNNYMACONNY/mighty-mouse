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


@pytest.mark.parametrize("backend_path", [Path("build_backend.py"), Path("mcp/build_backend.py")])
def test_build_backends_support_editable_installs(backend_path):
    source = backend_path.read_text()
    assert "def build_editable(" in source
    assert "def get_requires_for_build_editable(" in source
    assert "def prepare_metadata_for_build_editable(" in source
