import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parent


def main() -> None:
    subprocess.run([sys.executable, "aggregator.py"], cwd=ROOT, check=False)
    subprocess.Popen([sys.executable, "viewer.py"], cwd=ROOT)


if __name__ == "__main__":
    main()
