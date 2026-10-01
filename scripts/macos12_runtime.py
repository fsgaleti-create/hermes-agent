#!/usr/bin/env python3
"""Isolated Monterey launcher. Supply a dedicated --root, never the active Hermes home."""
from __future__ import annotations
import argparse
import json
import os
from pathlib import Path
import subprocess
import sys


def isolated_environment(root: Path) -> dict[str, str]:
    env = dict(os.environ)
    for key in list(env):
        if key.startswith('__HERMES_') or key in ('PYTHONHOME', 'PYTHONPATH', 'VIRTUAL_ENV', 'HERMES_PYTHON', 'HERMES_PROFILE'):
            env.pop(key, None)
    env.update(HERMES_HOME=str(root / 'home'), HERMES_RUNTIME_DIR=str(root / 'tools'),
               HERMES_DISABLE_LAZY_INSTALLS='1', PYTHONDONTWRITEBYTECODE='1',
               TMPDIR=str(root / 'scratch'))
    return env


def select_generation(root: Path, name: str) -> None:
    if Path(name).name != name or name in ('.', '..'):
        raise RuntimeError('Invalid generation name')
    candidate = root / 'generations' / name
    receipt = candidate / 'acceptance.json'
    if not receipt.is_file():
        raise RuntimeError('Missing acceptance receipt; selection unchanged')
    accepted = json.loads(receipt.read_text())
    if accepted.get('passed') is not True or not (candidate / 'venv/bin/python').is_file():
        raise RuntimeError('Invalid acceptance receipt or interpreter')
    old = json.loads((root / 'selection.json').read_text()) if (root / 'selection.json').is_file() else {}
    if old.get('current') == name:
        return
    temp = root / 'selection.next.json'
    with temp.open('w') as handle:
        json.dump({'current': name, 'previous': old.get('current')}, handle)
        handle.flush()
        os.fsync(handle.fileno())
    os.replace(temp, root / 'selection.json')


def rollback(root: Path) -> None:
    state = json.loads((root / 'selection.json').read_text())
    if not state.get('previous'):
        raise RuntimeError('No previous accepted generation')
    select_generation(root, state['previous'])


def update(root: Path, source: Path, revision: str) -> None:
    import re
    import uuid
    import platform
    if not re.fullmatch(r'[0-9a-f]{40}', revision):
        raise RuntimeError('Update requires a 40-character commit SHA')
    if platform.system() != 'Darwin' or platform.machine() != 'x86_64':
        raise RuntimeError('This compatibility branch supports Intel macOS only')
    for directory in ('generations', 'home', 'tools', 'scratch', 'logs'):
        (root / directory).mkdir(parents=True, exist_ok=True)
    name = revision[:12] + '-' + uuid.uuid4().hex[:8]
    generation = root / 'generations' / name
    env = isolated_environment(root)
    log_path = root / 'logs' / (name + '.log')
    with log_path.open('w') as log:
        def run(command, *, cwd=root):
            print('+ ' + ' '.join(map(str, command)), file=log, flush=True)
            subprocess.run(list(map(str, command)), cwd=cwd, env=env, stdout=log,
                           stderr=subprocess.STDOUT, check=True, timeout=1200)
        run(['git', 'clone', '--no-checkout', source, generation])
        run(['git', 'checkout', '--detach', revision], cwd=generation)
        run(['git', 'remote', 'set-url', 'origin', 'https://github.com/fsgaleti-create/hermes-agent.git'], cwd=generation)
        pinned = json.loads((generation / 'pm/lock.json').read_text())['packages']['node']
        if pinned['version'] != '22.23.3':
            raise RuntimeError('Candidate lacks reviewed Monterey Node pin')
        bootstrap = Path(sys.base_prefix) / 'bin/python3.14'
        if not bootstrap.is_file():
            raise RuntimeError('Run this controller with an installed Python 3.14 interpreter')
        run([bootstrap, '-B', '-m', 'pm.build_env', '--source', generation, '--out', generation / 'venv',
             '--python', bootstrap], cwd=generation)
        python = generation / 'venv/bin/python'
        run([python, '-B', '-m', 'hermes_cli.main', 'pm', 'install', 'node', 'npm'], cwd=generation)
        probe = ('import sys,ssl,sqlite3,cryptography,pydantic,PIL,pillow_heif; '
                 'from cryptography.hazmat.primitives.asymmetric import ed25519; '
                 'k=ed25519.Ed25519PrivateKey.generate(); k.public_key().verify(k.sign(b"Monterey"),b"Monterey"); '
                 'import run_agent,tui_gateway.server,hermes_cli.web_server; '
                 'import pm,subprocess; from pm.install import installed_package; '
                 'p=installed_package("node"); assert p.version=="22.23.3"; '
                 'subprocess.run([str(p.binary),"--version"],check=True); '
                 'print("acceptance imports/crypto/node OK",sys.version,ssl.OPENSSL_VERSION,sqlite3.sqlite_version)')
        run([python, '-B', '-c', probe], cwd=generation)
        run([python, '-B', '-m', 'hermes_cli.main', '--help'], cwd=generation)
        run([python, '-B', '-m', 'hermes_cli.main', 'serve', '--help'], cwd=generation)
    (generation / 'acceptance.json').write_text(json.dumps({'passed': True, 'sha': revision,
                                                         'log': str(log_path), 'scope': 'CLI/imports/crypto/Node; GUI not validated'}))
    select_generation(root, name)
    print(json.dumps({'generation': name, 'sha': revision, 'log': str(log_path)}))


def launch(root: Path, args: list[str]) -> int:
    if any(arg in ('update', 'pm', 'profile', '-p', '--profile', '--home') or
           arg.startswith(('--profile=', '--home=')) for arg in args):
        raise RuntimeError('Use the isolated update command; PM/profile/home mutation is disabled')
    state = json.loads((root / 'selection.json').read_text())
    generation = root / 'generations' / state['current']
    return subprocess.call([str(generation / 'venv/bin/python'), '-B', '-m', 'hermes_cli.main', *args],
                           cwd=generation, env=isolated_environment(root))


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--root', type=Path, required=True)
    parser.add_argument('--source', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('command', choices=['launch', 'update', 'rollback', 'status'])
    parser.add_argument('args', nargs=argparse.REMAINDER)
    opts = parser.parse_args()
    try:
        root = opts.root.resolve()
        if opts.command == 'launch':
            return launch(root, opts.args)
        if opts.command == 'update':
            if len(opts.args) != 1:
                raise RuntimeError('Update requires a 40-character commit SHA; no blind upstream promotion')
            update(root, opts.source.resolve(), opts.args[0])
        elif opts.command == 'rollback':
            rollback(root)
        else:
            print((root / 'selection.json').read_text())
        return 0
    except (RuntimeError, OSError, ValueError, subprocess.SubprocessError) as exc:
        print(str(exc), file=sys.stderr)
        return 1


if __name__ == '__main__':
    raise SystemExit(main())
