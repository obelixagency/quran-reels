"""Local-only private credential handoff. Never used by publishing workflows."""
import json
import os
from pathlib import Path
import sys


def local_only():
    if os.environ.get("CI") or os.environ.get("GITHUB_ACTIONS") or not sys.stdin.isatty():
        raise SystemExit("Account setup requires a private interactive local terminal")
    if len(sys.argv) != 1:
        raise SystemExit("Do not pass credentials as command-line arguments")


def write_credentials(values):
    destination = Path(input("New private output file outside this checkout: ").strip()).expanduser().resolve()
    checkout = Path(__file__).resolve().parent.parent
    if destination == checkout or checkout in destination.parents:
        raise SystemExit("Choose a file outside the checkout")
    # Exclusive create prevents overwrite/symlink following; restrictive permissions from creation.
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w") as output:
        json.dump(values, output)
    print("Credentials saved privately; transfer to the existing GitHub Actions secret names, then delete the file.")
