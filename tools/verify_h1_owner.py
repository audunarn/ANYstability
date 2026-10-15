"""Build-only inspection of the pinned public H1 source. No qualification claim."""
from pathlib import Path
import hashlib, json, os, subprocess, sys, tempfile, zipfile

COMMIT = '21d0637bc7f090e03b88f785f75ea1821489db6d'

def run(*args, cwd=None):
    subprocess.run(args, cwd=cwd, check=True, timeout=240)

root = Path(tempfile.mkdtemp(prefix='anystability-h1-'))
source = root / 'owner'
run('git', 'init', str(source))
run('git', '-C', str(source), 'remote', 'add', 'origin', 'https://github.com/audunarn/ANYgeometry.git')
run('git', '-C', str(source), 'fetch', '--depth', '1', 'origin', COMMIT)
run('git', '-C', str(source), 'checkout', '--detach', 'FETCH_HEAD')
assert subprocess.check_output(['git', '-C', str(source), 'rev-parse', 'HEAD'], text=True).strip() == COMMIT
print('H1_RELEVANT_FILES', flush=True)
for p in sorted(source.rglob('*')):
    if p.is_file() and '.git' not in p.parts and any(s in p.name.lower() for s in ('hydrostat', 'generality', 'barge', 'b1_', 'h1_', 'backend')):
        print(p.relative_to(source).as_posix(), flush=True)
run(sys.executable, '-m', 'pip', 'install', 'build')
run(sys.executable, '-m', 'build', '--wheel', '--outdir', str(root / 'wheels'), cwd=source)
wheel, = (root / 'wheels').glob('*.whl')
run(sys.executable, '-m', 'pip', 'install', str(wheel))
with zipfile.ZipFile(wheel) as z:
    members = {n: hashlib.sha256(z.read(n)).hexdigest() for n in sorted(z.namelist()) if n.startswith('anygeometry/') and n.endswith('.py')}
payload = '\n'.join(f'{name} {sha}' for name, sha in sorted(members.items())).encode()
print('H1_OWNER_RECEIPT', json.dumps(dict(commit=COMMIT, wheel=wheel.name, wheel_sha256=hashlib.sha256(wheel.read_bytes()).hexdigest(), python_payload_sha256=hashlib.sha256(payload).hexdigest(), source_files=len(members))), flush=True)
import importlib.metadata
for name, sha in members.items():
    installed = Path(importlib.metadata.distribution('ANYgeometry').locate_file(name))
    assert hashlib.sha256(installed.read_bytes()).hexdigest() == sha, name
print('H1_INSTALLED_SOURCE_EQUIVALENCE_PASS', flush=True)
run(sys.executable, '-I', '-c', 'from anygeometry.hydrostatics import hydrostatics; from anygeometry.shell_volume import closed_shell; print("H1_PUBLIC_API_IMPORT_PASS")', cwd=root)
