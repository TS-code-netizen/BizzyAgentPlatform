import argparse
import json
from pathlib import Path

from backend.main import app

parser = argparse.ArgumentParser()
parser.add_argument("--output", type=Path, required=True)
args = parser.parse_args()
args.output.parent.mkdir(parents=True, exist_ok=True)
args.output.write_text(json.dumps(app.openapi(), indent=2, sort_keys=True) + "\n")
