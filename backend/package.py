"""Create a backend-only handoff archive, excluding private configuration and runtime data."""
import hashlib
from pathlib import Path
import tarfile

root = Path(__file__).parent
output = root / 'dist'
output.mkdir(exist_ok=True)
archive = output / 'secondvision-backend.tar.gz'
excluded = {'.data', '.venv', '__pycache__', 'dist', '.git'}
files = [path for path in root.rglob('*') if path.is_file() and not path.is_symlink()
         and not any(part in excluded for part in path.relative_to(root).parts)
         and (not path.name.startswith('.env') or path.name == '.env.example')
         and path.name != 'access.txt']
with tarfile.open(archive, 'w:gz') as bundle:
    for path in sorted(files):
        bundle.add(path, arcname='backend/' + path.relative_to(root).as_posix(), recursive=False)
digest = hashlib.sha256(archive.read_bytes()).hexdigest()
(output / 'secondvision-backend.sha256').write_text(digest + '  secondvision-backend.tar.gz\n')
print(str(archive))
print(str(len(files)) + ' source files; private configuration and runtime data excluded.')
