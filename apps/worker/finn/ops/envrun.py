"""Run a command with the variables from FINN_ENV_FILE, without a shell parsing the file.

    export FINN_ENV_FILE=~/.secrets/finn.env
    uv run python -m finn.ops.envrun modal deploy -m finn.ops.modal_app

Sourcing an env file in a shell breaks on values with `&` (Neon URLs have them) and can
echo them back; this reads the file as data. Variables already set win.
"""

from __future__ import annotations

import os
import sys

from finn.core.config import load_env_file


def main() -> None:
    if len(sys.argv) < 2:
        raise SystemExit("usage: python -m finn.ops.envrun <command> [args...]")
    env = dict(os.environ)
    path = env.get("FINN_ENV_FILE")
    if path:
        for k, v in load_env_file(path).items():
            env.setdefault(k, v)
    os.execvpe(sys.argv[1], sys.argv[1:], env)


if __name__ == "__main__":
    main()
