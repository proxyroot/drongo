"""Command-line interface: ``drongo``."""

from __future__ import annotations

import argparse

import drongo


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="drongo",
        description="Mock Google Cloud Platform services in your tests.",
    )
    parser.add_argument(
        "--version", action="version", version=f"drongo {drongo.__version__}"
    )
    sub = parser.add_subparsers(dest="command")

    server = sub.add_parser("server", help="Run the standalone mock server.")
    server.add_argument("--host", default="localhost", help="Bind host.")
    server.add_argument("--port", "-p", type=int, default=5000, help="Bind port.")

    sub.add_parser("services", help="List the GCP services drongo can mock.")

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.command == "server":
        from drongo.server import run

        run(host=args.host, port=args.port)
        return 0

    if args.command == "services":
        import drongo.services  # noqa: F401  (register services)
        from drongo.core.registry import iter_services

        for service in iter_services():
            print(service.name)
        return 0

    parser.print_help()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
