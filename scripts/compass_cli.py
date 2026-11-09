"""
░█████╗░░█████╗░███╗░░░███╗██████╗░░█████╗░░██████╗░██████╗░░░░░░░█████╗░██╗░░░░░██╗
██╔══██╗██╔══██╗████╗░████║██╔══██╗██╔══██╗██╔════╝██╔════╝░░░░░░██╔══██╗██║░░░░░██║
██║░░╚═╝██║░░██║██╔████╔██║██████╔╝███████║╚█████╗░╚█████╗░█████╗██║░░╚═╝██║░░░░░██║
██║░░██╗██║░░██║██║╚██╔╝██║██╔═══╝░██╔══██║░╚═══██╗░╚═══██╗╚════╝██║░░██╗██║░░░░░██║
╚█████╔╝╚█████╔╝██║░╚═╝░██║██║░░░░░██║░░██║██████╔╝██████╔╝░░░░░░╚█████╔╝███████╗██║
░╚════╝░░╚════╝░╚═╝░░░░░╚═╝╚═╝░░░░░╚═╝░░╚═╝╚═════╝░╚═════╝░░░░░░░░╚════╝░╚══════╝╚═╝
"""

from __future__ import annotations

import sys
from pathlib import Path

ROOT_DIR = Path(__file__).resolve().parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from utils.cli_utils import CompassCliRunner  # noqa: E402


class CompassCliEntrypoint(CompassCliRunner):
    """Concrete CLI entrypoint runner writing formatted output to stdout/stderr."""

    def run_from_sys_argv(self, argv: list[str] | None = None) -> int:
        """Execute the CLI with command-line arguments and print output."""
        code, output = self.execute_cli(argv)
        stream = sys.stderr if code != 0 else sys.stdout
        if output:
            print(output, file=stream)
        return code


if __name__ == "__main__":
    cli = CompassCliEntrypoint()
    raise SystemExit(cli.run_from_sys_argv())
