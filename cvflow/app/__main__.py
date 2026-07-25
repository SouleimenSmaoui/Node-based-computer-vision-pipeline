"""``python -m cvflow.app`` entry point."""

from __future__ import annotations

from cvflow.app import run_app


def main() -> int:
    return run_app()


if __name__ == "__main__":
    raise SystemExit(main())
