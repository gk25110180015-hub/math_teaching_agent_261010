"""Resolve copied snapshots without rewriting historical records or their hashes."""
from pathlib import Path, PurePosixPath, PureWindowsPath

from .util import within


def snapshot_root(workspace: Path, run_id: str, source_key: str) -> Path:
    """An uploaded snapshot must still belong to the recorded run."""
    if not isinstance(source_key, str) or '\\' in source_key or ':' in source_key:
        raise ValueError('Invalid snapshot storage key')
    key = PurePosixPath(source_key)
    if (key.is_absolute() or '..' in key.parts or len(key.parts) < 3
            or key.parts[:2] != ('inputs', run_id)):
        raise ValueError('Snapshot does not belong to this run')
    root = within(workspace, source_key)
    if not root.is_relative_to(within(workspace, 'inputs/' + run_id)):
        raise ValueError('Snapshot escapes its recorded run')
    return root


def checkpoint_pdf(workspace: Path, source: Path, recorded_path: str) -> Path:
    """Keep the exact recorded section suffix, then verify bytes at the new root."""
    expected = (source.parent.parent / 'build' / 'lecture.pdf').resolve()
    suffix = expected.relative_to(workspace.resolve()).parts
    if not isinstance(recorded_path, str):
        raise ValueError('Invalid recorded PDF path')
    recorded = PureWindowsPath(recorded_path) if '\\' in recorded_path or PureWindowsPath(recorded_path).drive else PurePosixPath(recorded_path)
    if not recorded.is_absolute() or '..' in recorded.parts:
        raise ValueError('Recorded PDF path is not an absolute normalized path')
    tail = recorded.parts[-len(suffix):]
    if isinstance(recorded, PureWindowsPath):
        tail, suffix = tuple(p.casefold() for p in tail), tuple(p.casefold() for p in suffix)
    if tail != suffix:
        raise ValueError('Recorded PDF belongs to a different run or section')
    return expected
