#!/usr/bin/env python3
"""
K-Frame Quartz Bridge — Desktop entry point.

Launches the Tkinter GUI on the main thread and runs the asyncio bridge
in a background daemon thread.
"""

import argparse
import asyncio
import configparser
import logging
import os
import shutil
import sys
import threading
from pathlib import Path

from k_frame_quartz_bridge import BridgeConfig, bridge_main
from gui import BridgeGUI


def load_config() -> configparser.ConfigParser:
    """Load config.ini, copying from example if it doesn't exist."""
    config_path = Path(__file__).parent / "config.ini"

    if not config_path.exists():
        example_path = Path(__file__).parent / "config.ini.example"
        if example_path.exists():
            shutil.copy(example_path, config_path)

    config = configparser.ConfigParser()
    config.read(config_path)
    return config


def run_bridge(cfg: BridgeConfig, log_level: str) -> None:
    """Run the bridge in a new asyncio event loop (called from daemon thread)."""
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )
    try:
        asyncio.run(bridge_main(cfg))
    except Exception as exc:
        print(f"Bridge error: {exc}")


def main() -> None:
    parser = argparse.ArgumentParser(description="K-Frame Quartz Bridge")
    parser.add_argument(
        "--console", action="store_true",
        help="Run in console mode without GUI",
    )
    args = parser.parse_args()

    config = load_config()
    log_level = config.get("logging", "level", fallback="INFO")
    config_path = Path(__file__).parent / "config.ini"
    cfg = BridgeConfig.from_ini(config_path)

    if args.console:
        # Console mode — run directly
        logging.basicConfig(
            level=log_level,
            format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        )
        print(f"Starting K-Frame Quartz Bridge (console mode)")
        print(f"  GV: {cfg.gv.host} ({cfg.gv.suite})")
        print(f"  Quartz port: {cfg.router.listen_port}")
        print(f"  Status UI: http://localhost:{cfg.http.listen_port}")
        print()
        try:
            asyncio.run(bridge_main(cfg))
        except KeyboardInterrupt:
            pass
        return

    # GUI mode — bridge in daemon thread, Tkinter on main thread
    print(f"Starting K-Frame Quartz Bridge")
    print(f"  GV: {cfg.gv.host} ({cfg.gv.suite})")
    print(f"  Quartz port: {cfg.router.listen_port}")
    print(f"  Status UI: http://localhost:{cfg.http.listen_port}")

    bridge_thread = threading.Thread(
        target=run_bridge,
        args=(cfg, log_level),
        daemon=True,
    )
    bridge_thread.start()

    gui = BridgeGUI(
        gv_host=cfg.gv.host,
        gv_suite=cfg.gv.suite,
        quartz_port=cfg.router.listen_port,
        http_port=cfg.http.listen_port,
    )
    gui.run()


if __name__ == "__main__":
    main()
