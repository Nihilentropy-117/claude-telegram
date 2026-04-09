"""Entry point for ``python -m claude_telegram``."""

import asyncio
import logging

from claude_telegram.bot import run

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    datefmt="%H:%M:%S",
)


def main() -> None:
    asyncio.run(run())


if __name__ == "__main__":
    main()
