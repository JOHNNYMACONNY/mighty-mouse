#!/usr/bin/env python3
from pathlib import Path
import argparse, shutil, sys

ROOT = Path(__file__).resolve().parents[1]
FIXTURES = ROOT / 'fixtures'
RUNS = ROOT / 'runs'


def _ignore(dirpath, names):
    return [name for name in names if name.startswith('._') or name == '.DS_Store']


def _cleanup_metadata(path: Path):
    for extra in list(path.rglob('._*')) + list(path.rglob('.DS_Store')):
        extra.unlink(missing_ok=True)


def main():
    ap = argparse.ArgumentParser(description='Reset an Antigravity benchmark task workspace from pristine fixtures.')
    ap.add_argument('task_id', help='Fixture/task directory name, e.g. task_ag3_001_legacy_migration_trap')
    ap.add_argument('--dest', help='Optional destination directory name under runs/ (defaults to task_id)')
    args = ap.parse_args()

    src = FIXTURES / args.task_id
    if not src.exists():
        print(f'Unknown task fixture: {args.task_id}', file=sys.stderr)
        return 1
    dest = RUNS / (args.dest or args.task_id)
    if dest.exists():
        shutil.rmtree(dest)
    shutil.copytree(src, dest, ignore=_ignore)
    _cleanup_metadata(dest)
    print(dest)
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
