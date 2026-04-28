"""CLI entry point for the Hermes NoDeskClaw bridge."""

from __future__ import annotations

import argparse
import asyncio
import logging

from .client import TunnelCallbacks, TunnelClient
from .hermes_channel import HermesChannel


async def _run_bridge() -> None:
    callbacks = TunnelCallbacks(
        on_auth_ok=lambda: logging.getLogger("hermes_nodeskclaw_bridge").info(
            "Hermes bridge authenticated"
        ),
        on_auth_error=lambda reason: logging.getLogger("hermes_nodeskclaw_bridge").error(
            "Hermes bridge auth failed: %s", reason
        ),
        on_close=lambda: logging.getLogger("hermes_nodeskclaw_bridge").warning(
            "Hermes bridge connection closed"
        ),
        on_reconnecting=lambda attempt: logging.getLogger("hermes_nodeskclaw_bridge").info(
            "Hermes bridge reconnecting (attempt #%d)", attempt
        ),
    )
    client = TunnelClient(callbacks=callbacks)
    channel = HermesChannel(client)
    client.on_chat_request = channel.handle_chat_request
    await client.run_forever()


def main() -> None:
    parser = argparse.ArgumentParser(description="Hermes NoDeskClaw tunnel bridge")
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
    )
    args = parser.parse_args()

    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
    )
    asyncio.run(_run_bridge())


if __name__ == "__main__":
    main()
