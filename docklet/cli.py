"""Argparse CLI — the user-facing entry point for docklet.

Ties together container, registry, and image modules behind a familiar
docker-like command interface. Requires root privileges to run.
"""

from __future__ import annotations

import argparse
import importlib
import os
import sys
import types
from typing import Any

from docklet import image, registry

# container.py is built concurrently on another branch and may not exist yet.
# Use importlib so mypy doesn't statically resolve the missing attribute.
container: types.ModuleType = importlib.import_module("docklet.container")


def _parse_image_tag(image_str: str) -> tuple[str, str]:
    """Split an IMAGE[:TAG] string into (image, tag), defaulting tag to 'latest'."""
    if ":" in image_str:
        name, tag = image_str.rsplit(":", 1)
        if not tag:
            tag = "latest"
        return name, tag
    return image_str, "latest"


def _format_size(size_bytes: int) -> str:
    """Format a byte count as a human-readable size string."""
    if size_bytes >= 1_073_741_824:
        return f"{size_bytes / 1_073_741_824:.1f}GB"
    if size_bytes >= 1_048_576:
        return f"{size_bytes / 1_048_576:.1f}MB"
    if size_bytes >= 1024:
        return f"{size_bytes / 1024:.1f}KB"
    return f"{size_bytes}B"


def _cmd_pull(args: argparse.Namespace) -> None:
    """Handle the 'pull' subcommand."""
    name, tag = _parse_image_tag(args.image)
    registry.pull_image(name, tag)
    print(f"Successfully pulled {name}:{tag}")


def _cmd_run(args: argparse.Namespace) -> None:
    """Handle the 'run' subcommand."""
    name, tag = _parse_image_tag(args.image)
    command: list[str] = args.cmd if args.cmd else ["/bin/sh"]
    cpu_limit: int | None = args.cpu
    mem_limit: str | None = args.memory
    container_id: str = container.run(
        name, tag, command, mem_limit=mem_limit, cpu_limit=cpu_limit
    )
    print(container_id)


def _cmd_exec(args: argparse.Namespace) -> None:
    """Handle the 'exec' subcommand."""
    container.exec_in(args.container_id, args.cmd)


def _cmd_ps(args: argparse.Namespace) -> None:
    """Handle the 'ps' subcommand."""
    containers: list[dict[str, Any]] = container.list_containers()
    header = f"{'CONTAINER ID':<16}{'IMAGE':<24}{'COMMAND':<20}{'STATUS':<12}{'IP':<16}"
    print(header)
    for c in containers:
        row = (
            f"{c.get('id', ''):<16}"
            f"{c.get('image', ''):<24}"
            f"{c.get('command', ''):<20}"
            f"{c.get('status', ''):<12}"
            f"{c.get('ip', ''):<16}"
        )
        print(row)


def _cmd_images(args: argparse.Namespace) -> None:
    """Handle the 'images' subcommand."""
    images: list[dict[str, Any]] = image.list_images()
    header = f"{'REPOSITORY':<24}{'TAG':<16}{'SIZE':<12}"
    print(header)
    for img in images:
        size_str = _format_size(img.get("size", 0))
        row = f"{img.get('name', ''):<24}{img.get('tag', ''):<16}{size_str:<12}"
        print(row)


def _cmd_rm(args: argparse.Namespace) -> None:
    """Handle the 'rm' subcommand."""
    container.remove(args.container_id)
    print(f"Removed container {args.container_id}")


def _build_parser() -> argparse.ArgumentParser:
    """Build and return the argument parser with all subcommands."""
    parser = argparse.ArgumentParser(
        prog="docklet",
        description="A minimalist container runtime",
    )

    subparsers = parser.add_subparsers(dest="subcommand")

    # pull
    pull_parser = subparsers.add_parser("pull", help="Pull an image from Docker Hub")
    pull_parser.add_argument("image", help="Image name (IMAGE[:TAG])")

    # run
    run_parser = subparsers.add_parser("run", help="Create and start a container")
    run_parser.add_argument(
        "-m", "--memory", default=None, help="Memory limit (e.g., 512m)"
    )
    run_parser.add_argument(
        "-c", "--cpu", type=int, default=None, help="CPU limit (percentage)"
    )
    run_parser.add_argument("image", help="Image name (IMAGE[:TAG])")
    run_parser.add_argument(
        "cmd", nargs=argparse.REMAINDER, help="Command to execute (default: /bin/sh)"
    )

    # exec
    exec_parser = subparsers.add_parser(
        "exec", help="Execute a command in a running container"
    )
    exec_parser.add_argument("container_id", help="Container ID")
    exec_parser.add_argument("cmd", nargs=argparse.REMAINDER, help="Command to execute")

    # ps
    subparsers.add_parser("ps", help="List containers")

    # images
    subparsers.add_parser("images", help="List locally pulled images")

    # rm
    rm_parser = subparsers.add_parser("rm", help="Remove a container")
    rm_parser.add_argument("container_id", help="Container ID")

    return parser


def main(argv: list[str] | None = None) -> None:
    """Entry point for the docklet CLI."""
    if os.geteuid() != 0:
        sys.stderr.write("docklet must be run as root\n")
        sys.exit(1)

    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.subcommand is None:
        parser.print_usage(sys.stderr)
        sys.exit(1)

    handlers: dict[str, Any] = {
        "pull": _cmd_pull,
        "run": _cmd_run,
        "exec": _cmd_exec,
        "ps": _cmd_ps,
        "images": _cmd_images,
        "rm": _cmd_rm,
    }

    try:
        handler = handlers[args.subcommand]
        handler(args)
    except KeyboardInterrupt:
        sys.exit(130)
