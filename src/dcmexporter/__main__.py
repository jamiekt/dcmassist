"""Entry point for the dcmexporter CLI."""

from __future__ import annotations

from dcmexporter.cli import cli


def main() -> None:
    cli()


if __name__ == "__main__":
    main()
