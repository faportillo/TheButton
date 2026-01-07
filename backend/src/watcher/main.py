"""
Watcher service - Runs the watcher_lambda function periodically.

This service checks for phase transitions when no button presses occur,
allowing the system to automatically reduce entropy and transition phases.
"""
import logging
import signal
import sys
import time
from watcher.watcher_lambda import watcher_lambda
from watcher.config import settings

logger = logging.getLogger(__name__)

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

# Global flag for graceful shutdown
shutdown = False


def signal_handler(sig, frame):
    """Handle shutdown signals gracefully."""
    global shutdown
    logger.info("Received shutdown signal, shutting down gracefully...")
    shutdown = True


def main():
    """Main entry point for the watcher service."""
    # Register signal handlers for graceful shutdown
    signal.signal(signal.SIGINT, signal_handler)
    signal.signal(signal.SIGTERM, signal_handler)

    # Interval in seconds (default: 30 seconds)
    interval = getattr(settings, "watcher_interval_seconds", 30)

    logger.info(f"Watcher service starting (interval: {interval}s)")
    logger.info(f"Environment: {settings.env}")

    try:
        while not shutdown:
            try:
                result = watcher_lambda({}, None)
                logger.debug(f"Watcher execution result: {result}")
            except Exception as e:
                logger.error(f"Error executing watcher_lambda: {e}", exc_info=True)
                # Continue running even if one execution fails

            # Sleep until next execution, checking for shutdown periodically
            for _ in range(interval):
                if shutdown:
                    break
                time.sleep(1)

    except KeyboardInterrupt:
        logger.info("Received keyboard interrupt")
    finally:
        logger.info("Watcher service stopped")


if __name__ == "__main__":
    main()

