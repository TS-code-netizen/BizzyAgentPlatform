import hashlib
import json
import tarfile
from pathlib import Path

root = Path(__file__).resolve().parents[1]
manifest = json.loads((root / "docker/data-manifest.json").read_text())
archive_path = root / "docker/bizzydata-demo.tar.gz"
if manifest["source"] != (root / "docker/BIZZY_DATA_REF").read_text().strip():
    raise RuntimeError("Dataset provenance mismatch.")
if hashlib.sha256(archive_path.read_bytes()).hexdigest() != manifest["archive_sha256"]:
    raise RuntimeError("Dataset archive checksum mismatch.")
with tarfile.open(archive_path) as archive:
    if sorted(archive.getnames()) != sorted(manifest["files"]):
        raise RuntimeError("Unexpected dataset archive members.")
    for member in archive.getmembers():
        if not member.isfile() or Path(member.name).name != member.name:
            raise RuntimeError("Unsafe archive member.")
        if hashlib.sha256(archive.extractfile(member).read()).hexdigest() != manifest["files"][member.name]:
            raise RuntimeError(f"Dataset checksum mismatch: {member.name}")
print("Dataset archive and member checksums verified.")
