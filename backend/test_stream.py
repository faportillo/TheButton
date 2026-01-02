#!/usr/bin/env python3
"""
Simple script to test the /v1/states/stream SSE endpoint.

Usage:
    python test_stream.py [--url URL] [--timeout SECONDS]

Example:
    python test_stream.py --url http://localhost:8000
"""

import argparse
import requests
import sys
import json
from datetime import datetime


def stream_states(url: str, timeout: int = 60):
    """Connect to the SSE stream and print events as they arrive."""
    stream_url = f"{url}/v1/states/stream"
    
    print(f"Connecting to {stream_url}...")
    print("Waiting for state updates (press Ctrl+C to stop)...")
    print("Note: Updates will only appear when the reducer processes button presses.")
    print("Make sure the reducer is running: make run-reducer\n")
    
    try:
        response = requests.get(
            stream_url,
            stream=True,
            timeout=timeout,
            headers={"Accept": "text/event-stream"},
        )
        response.raise_for_status()
        
        print("✓ Connected to stream successfully")
        print("Listening for updates...\n")
        
        # Process SSE stream
        buffer = ""
        line_count = 0
        for line in response.iter_lines(decode_unicode=True):
            line_count += 1
            # Print a heartbeat every 30 seconds to show we're still connected
            if line_count % 1000 == 0:
                print(f"[{datetime.now().strftime('%H:%M:%S')}] Still listening... (received {line_count} lines)")
            
            if not line:
                # Empty line indicates end of event
                if buffer:
                    process_event(buffer)
                    buffer = ""
                continue
            
            buffer += line + "\n"
            
    except KeyboardInterrupt:
        print("\n\nStream interrupted by user")
    except requests.exceptions.RequestException as e:
        print(f"\nError connecting to stream: {e}", file=sys.stderr)
        print("\nTroubleshooting:")
        print("1. Is the API running? Check: curl http://localhost:8000/health")
        print("2. Is the reducer running? Check: ps aux | grep reducer")
        print("3. Are Docker services up? Check: make status")
        sys.exit(1)


def process_event(event_text: str):
    """Parse and display an SSE event."""
    event_type = None
    data = None
    
    for line in event_text.strip().split("\n"):
        if line.startswith("event:"):
            event_type = line[6:].strip()
        elif line.startswith("data:"):
            data_str = line[5:].strip()
            try:
                data = json.loads(data_str)
            except json.JSONDecodeError:
                data = data_str
    
    timestamp = datetime.now().strftime("%H:%M:%S.%f")[:-3]
    
    if event_type == "state_update":
        print(f"[{timestamp}] State Update:")
        print(json.dumps(data, indent=2, default=str))
        print("-" * 60)
    elif event_type == "error":
        print(f"[{timestamp}] Error: {data}")
    else:
        # Handle events without explicit event type (defaults to "message")
        if event_type is None and data is not None:
            print(f"[{timestamp}] Message:")
            print(json.dumps(data, indent=2, default=str))
            print("-" * 60)
        else:
            print(f"[{timestamp}] Event ({event_type}): {event_text}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Test the SSE streaming endpoint")
    parser.add_argument(
        "--url",
        default="http://localhost:8000",
        help="Base URL of the API (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=60,
        help="Connection timeout in seconds (default: 60)",
    )
    
    args = parser.parse_args()
    stream_states(args.url, args.timeout)

