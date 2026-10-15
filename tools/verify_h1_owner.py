"""Build and test pinned owner/consumer wheels outside source trees.

Development evidence only. No tolerance changes, native fallback or source edits.
"""
from pathlib import Path
import hashlib
import json
import os
import subprocess
import sys
import tempfile
import zipfile

COMMIT = '21d0637bc7f090e03b88f785f75ea1821489db6d'
PAYLOAD = '2c8c0cf0fae861b88f966db9960c15add693fb4e6214befd77e1fec84467b5aa'
consumer = Path(__file__).resolve().parents[1]
root = Path(tempfile.mkdtemp(prefix='anystability-h1-'))
evidence = root / 'evidence'
evidence.mkdir()
count = 0


def run(*args, cwd=None, timeout=240):
    global count
    count += 1
    print('H1_STEP', count, args[:4], flush=True)
    try:
        p = subprocess.run(args, cwd=cwd, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired as exc:
        (evidence / f'{count:02d}.stdout.log').write_bytes(exc.stdout or b'')
        (evidence / f'{count:02d}.stderr.log').write_bytes(exc.stderr or b'')
        print((exc.stdout or b'')[-12000:].decode(errors='replace'), flush=True)
        print((exc.stderr or b'')[-12000:].decode(errors='replace'), flush=True)
        raise SystemExit(f'H1 step {count} timed out; partial evidence retained') from exc
    (evidence / f'{count:02d}.stdout.log').write_bytes(p.stdout)
    (evidence / f'{count:02d}.stderr.log').write_bytes(p.stderr)
    if p.returncode:
        print(p.stdout[-12000:].decode(errors='replace'), flush=True)
        print(p.stderr[-12000:].decode(errors='replace'), flush=True)
        raise SystemExit(p.returncode)
    return p.stdout


source = root / 'owner'
run('git', 'init', str(source))
run('git', '-C', str(source), 'config', 'core.autocrlf', 'false')
run('git', '-C', str(source), 'remote', 'add', 'origin', 'https://github.com/audunarn/ANYgeometry.git')
run('git', '-C', str(source), 'fetch', '--depth', '1', 'origin', COMMIT)
run('git', '-C', str(source), 'checkout', '--detach', 'FETCH_HEAD')
assert run('git', '-C', str(source), 'rev-parse', 'HEAD').decode().strip() == COMMIT
run(sys.executable, '-m', 'pip', 'install', 'build')
run(sys.executable, '-m', 'build', '--wheel', '--outdir', str(root / 'owner-wheels'), cwd=source)
wheel, = (root / 'owner-wheels').glob('*.whl')
run(sys.executable, '-m', 'pip', 'install', str(wheel))
with zipfile.ZipFile(wheel) as z:
    members = {n: hashlib.sha256(z.read(n)).hexdigest() for n in sorted(z.namelist())
               if n.startswith('anygeometry/') and n.endswith('.py')}
    for name, sha in members.items():
        assert hashlib.sha256((source / 'src' / name).read_bytes()).hexdigest() == sha, name
payload = '\n'.join(f'{name} {sha}' for name, sha in sorted(members.items())).encode()
assert hashlib.sha256(payload).hexdigest() == PAYLOAD and len(members) == 134
import importlib.metadata
for name, sha in members.items():
    installed = Path(importlib.metadata.distribution('ANYgeometry').locate_file(name))
    assert hashlib.sha256(installed.read_bytes()).hexdigest() == sha, name
receipt = dict(commit=COMMIT, wheel=wheel.name,
    wheel_sha256=hashlib.sha256(wheel.read_bytes()).hexdigest(),
    python_payload_sha256=PAYLOAD, source_files=len(members),
    source_wheel_installed_equivalence=True, python=sys.version,
    numpy=importlib.metadata.version('numpy'))
print('H1_OWNER_RECEIPT', json.dumps(receipt), flush=True)
(evidence / 'owner-receipt.json').write_text(json.dumps(receipt), encoding='utf-8')
run(sys.executable, '-m', 'build', '--wheel', '--outdir', str(root / 'consumer-wheels'), cwd=consumer)
consumer_wheel, = (root / 'consumer-wheels').glob('*.whl')
run(sys.executable, '-m', 'pip', 'install', '--no-deps', str(consumer_wheel))
run(sys.executable, '-I', '-c', 'from anystability.providers.anygeometry_h1 import verify_installed_owner; print(verify_installed_owner(allow_development=True))', cwd=root)
os.environ['H1_EVIDENCE'] = str(evidence)
output = run(sys.executable, '-I', str(consumer / 'tests/integration/check_h1_owner.py'), cwd=root, timeout=720)
print(output.decode(), flush=True)
print('H1_EVIDENCE_DIRECTORY', str(evidence), flush=True)
