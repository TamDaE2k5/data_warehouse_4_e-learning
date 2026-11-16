"""Compatibility notice for the superseded, source-mutating v2 verifier."""

import sys


def main():
    print(
        "The v2 verification entry point is retired. Run `python scripts/verify.py` "
        "from the repository root instead. The current verifier creates an isolated "
        "Docker project and records evidence without changing your main dataset.",
        file=sys.stderr,
    )
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
