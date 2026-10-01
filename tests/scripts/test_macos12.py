"""Live Monterey compatibility and isolated generation control."""
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]


def test_locked_node_matches_montery_runtime():
    from pm.lock import Lockfile
    lock = Lockfile(ROOT / 'pm/lock.json')
    version = lock.version('node')
    assert 22 <= int(version.split('.')[0]) < 23, 'Monterey must not receive Node 24/26'
    artifact = lock.artifacts('node', 'darwin-x64')[0]
    assert f'node-v{version}-darwin-x64' in artifact['url']
    assert len(artifact['sha256']) == 64


import pytest

@pytest.mark.live_system_guard_bypass
def test_launcher_refuses_inplace_mutation(tmp_path):
    script = ROOT / 'scripts/macos12_runtime.py'
    before = set(tmp_path.iterdir())
    result = subprocess.run([sys.executable, '-B', str(script), '--root', str(tmp_path),
                             'launch', 'update'], capture_output=True, text=True)
    assert result.returncode != 0
    assert 'Use the isolated update command' in result.stderr
    assert set(tmp_path.iterdir()) == before


def test_selection_requires_acceptance_before_switch(tmp_path):
    from scripts.macos12_runtime import select_generation
    root = tmp_path / 'isolated'
    root.mkdir()
    (root / 'selection.json').write_text(json.dumps({'current': 'old', 'previous': None}))
    candidate = root / 'generations/new'
    candidate.mkdir(parents=True)
    before = (root / 'selection.json').read_bytes()
    with pytest.raises(RuntimeError, match='acceptance'):
        select_generation(root, 'new')
    assert (root / 'selection.json').read_bytes() == before


def test_rollback_swaps_only_accepted_generations(tmp_path):
    from scripts.macos12_runtime import select_generation, rollback
    root = tmp_path / 'isolated'
    for name in ('first', 'second'):
        generation = root / 'generations' / name
        (generation / 'venv/bin').mkdir(parents=True)
        (generation / 'venv/bin/python').symlink_to(sys.executable)
        (generation / 'acceptance.json').write_text(json.dumps({'passed': True}))
    select_generation(root, 'first')
    select_generation(root, 'second')
    rollback(root)
    assert json.loads((root / 'selection.json').read_text()) == {'current': 'first', 'previous': 'second'}


def test_update_refuses_unpinned_revision_before_writes(tmp_path):
    from scripts.macos12_runtime import update
    before = set(tmp_path.iterdir())
    with pytest.raises(RuntimeError, match='40-character'):
        update(tmp_path, ROOT, 'main')
    assert set(tmp_path.iterdir()) == before


def test_frozen_runtime_build_does_not_include_developer_dependencies(tmp_path):
    import os
    import shutil
    uv = shutil.which('uv')
    assert uv, 'uv is required for runtime-install acceptance'
    env = dict(os.environ, UV_PROJECT_ENVIRONMENT=str(tmp_path / 'runtime-venv'))
    env.pop('VIRTUAL_ENV', None)
    result = subprocess.run([uv, 'sync', '--frozen', '--dry-run', '--python', sys.executable],
                            cwd=ROOT, env=env, capture_output=True, text=True, timeout=120)
    assert result.returncode == 0, result.stderr
    assert not any(line.strip().startswith('+ pytest==') for line in result.stderr.splitlines()), result.stderr
