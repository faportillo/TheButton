#!/usr/bin/env python3
"""
Load testing script for TheButton API.

Simulates heavy load by sending multiple concurrent button press requests.
Useful for testing system behavior under stress, rate limiting, and frontend rendering.

Usage:
    # Basic: 100 requests, 10 concurrent
    python -m scripts.load_test --requests 100 --concurrent 10

    # High load: 1000 requests, 50 concurrent, 10 requests/second
    python -m scripts.load_test --requests 1000 --concurrent 50 --rate 10

    # Use PoW bypass (if enabled)
    python -m scripts.load_test --requests 100 --bypass-pow

    # Custom API URL
    python -m scripts.load_test --api-url http://localhost:8080 --requests 100
"""

import asyncio
import argparse
import time
import json
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from datetime import datetime
import httpx
import hashlib


@dataclass
class TestStats:
    """Statistics for load test run."""
    total_requests: int = 0
    successful: int = 0
    failed: int = 0
    rate_limited: int = 0
    errors: int = 0
    response_times: List[float] = field(default_factory=list)
    start_time: Optional[float] = None
    end_time: Optional[float] = None

    @property
    def duration(self) -> float:
        """Total test duration in seconds."""
        if self.start_time and self.end_time:
            return self.end_time - self.start_time
        return 0.0

    @property
    def requests_per_second(self) -> float:
        """Average requests per second."""
        if self.duration > 0:
            return self.total_requests / self.duration
        return 0.0

    @property
    def avg_response_time(self) -> float:
        """Average response time in milliseconds."""
        if self.response_times:
            return sum(self.response_times) / len(self.response_times)
        return 0.0

    @property
    def success_rate(self) -> float:
        """Success rate as percentage."""
        if self.total_requests > 0:
            return (self.successful / self.total_requests) * 100
        return 0.0


class LoadTester:
    """Load testing client for TheButton API."""

    def __init__(
        self,
        api_url: str = "http://localhost:8000",
        bypass_pow: bool = False,
        rate_limit: Optional[float] = None,
    ):
        """
        Initialize load tester.

        Args:
            api_url: Base URL of the API
            bypass_pow: If True, use PoW bypass (requires POW_BYPASS=true on server)
            rate_limit: Maximum requests per second (None = no limit)
        """
        self.api_url = api_url.rstrip("/")
        self.bypass_pow = bypass_pow
        self.rate_limit = rate_limit
        self.stats = TestStats()
        self.semaphore: Optional[asyncio.Semaphore] = None
        self.rate_limiter: Optional[asyncio.Semaphore] = None

    async def solve_pow_challenge(self, challenge: Dict) -> str:
        """
        Solve a PoW challenge by finding a nonce.

        Args:
            challenge: Challenge dict with challenge_id and difficulty

        Returns:
            Nonce string that solves the challenge
        """
        challenge_id = challenge["challenge_id"]
        difficulty = challenge["difficulty"]
        target = "0" * difficulty

        nonce = 0
        while True:
            nonce_str = str(nonce)
            payload = f"{challenge_id}:{nonce_str}".encode()
            hash_result = hashlib.sha256(payload).hexdigest()

            if hash_result.startswith(target):
                return nonce_str

            nonce += 1

            # Yield occasionally to avoid blocking
            if nonce % 1000 == 0:
                await asyncio.sleep(0)

    async def fetch_challenge(self, client: httpx.AsyncClient) -> Dict:
        """Fetch a PoW challenge from the API."""
        response = await client.get(f"{self.api_url}/v1/challenge")
        response.raise_for_status()
        return response.json()

    async def send_button_press(
        self, client: httpx.AsyncClient, challenge: Dict, nonce: str
    ) -> Dict:
        """Send a button press request."""
        body = {
            "challenge_id": challenge["challenge_id"],
            "difficulty": challenge["difficulty"],
            "expires_at": challenge["expires_at"],
            "signature": challenge["signature"],
            "nonce": nonce,
        }

        response = await client.post(
            f"{self.api_url}/v1/events/press",
            json=body,
        )
        data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
        return {
            "status": response.status_code,
            "data": data,
        }

    async def send_press_with_bypass(
        self, client: httpx.AsyncClient
    ) -> Dict:
        """Send a button press with PoW bypass (for testing)."""
        body = {
            "challenge_id": "bypass",
            "difficulty": 0,
            "expires_at": int(time.time()) + 60,
            "signature": "bypass",
            "nonce": "0",
        }

        response = await client.post(
            f"{self.api_url}/v1/events/press",
            json=body,
        )
        data = response.json() if response.headers.get("content-type", "").startswith("application/json") else {}
        return {
            "status": response.status_code,
            "data": data,
        }

    async def rate_limiter_wait(self):
        """Wait if rate limiting is enabled."""
        if self.rate_limiter:
            await self.rate_limiter.acquire()
            # Release after 1 second to allow next request
            asyncio.create_task(self._release_rate_limiter_after_delay())

    async def _release_rate_limiter_after_delay(self):
        """Release rate limiter after 1 second."""
        await asyncio.sleep(1.0 / self.rate_limit if self.rate_limit else 1.0)
        if self.rate_limiter:
            self.rate_limiter.release()

    async def single_request(self, client: httpx.AsyncClient, request_id: int):
        """Execute a single button press request."""
        start_time = time.time()

        try:
            # Rate limiting
            if self.rate_limit:
                await self.rate_limiter_wait()

            # Get challenge and solve (or bypass)
            if self.bypass_pow:
                result = await self.send_press_with_bypass(client)
            else:
                challenge = await self.fetch_challenge(client)
                nonce = await self.solve_pow_challenge(challenge)
                result = await self.send_button_press(client, challenge, nonce)

            response_time = (time.time() - start_time) * 1000  # Convert to ms

            # Update statistics
            self.stats.total_requests += 1
            self.stats.response_times.append(response_time)

            status = result["status"]
            if status == 202:
                self.stats.successful += 1
            elif status == 429:
                self.stats.rate_limited += 1
            else:
                self.stats.failed += 1
                print(f"Request {request_id}: Failed with status {status}")

        except Exception as e:
            self.stats.total_requests += 1
            self.stats.errors += 1
            self.stats.failed += 1
            print(f"Request {request_id}: Error - {e}")

    async def run_test(
        self, total_requests: int, concurrent: int, progress_interval: int = 50
    ):
        """
        Run the load test.

        Args:
            total_requests: Total number of requests to send
            concurrent: Number of concurrent requests
            progress_interval: Print progress every N requests
        """
        self.stats.start_time = time.time()
        self.semaphore = asyncio.Semaphore(concurrent)

        if self.rate_limit:
            # Create semaphore for rate limiting
            self.rate_limiter = asyncio.Semaphore(int(self.rate_limit))

        print(f"\n{'='*60}")
        print(f"Load Test Starting")
        print(f"{'='*60}")
        print(f"API URL: {self.api_url}")
        print(f"Total Requests: {total_requests}")
        print(f"Concurrent: {concurrent}")
        print(f"PoW Bypass: {self.bypass_pow}")
        if self.rate_limit:
            print(f"Rate Limit: {self.rate_limit} req/s")
        print(f"{'='*60}\n")

        async def bounded_request(request_id: int):
            async with self.semaphore:
                async with httpx.AsyncClient(timeout=30.0) as client:
                    await self.single_request(client, request_id)

                # Print progress
                if (request_id + 1) % progress_interval == 0:
                    elapsed = time.time() - self.stats.start_time
                    rps = (request_id + 1) / elapsed if elapsed > 0 else 0
                    print(
                        f"Progress: {request_id + 1}/{total_requests} "
                        f"({rps:.1f} req/s, "
                        f"{self.stats.successful} success, "
                        f"{self.stats.rate_limited} rate limited)"
                    )

        # Create all tasks
        tasks = [bounded_request(i) for i in range(total_requests)]

        # Run all tasks
        await asyncio.gather(*tasks)

        self.stats.end_time = time.time()

    def print_results(self):
        """Print test results."""
        print(f"\n{'='*60}")
        print(f"Load Test Results")
        print(f"{'='*60}")
        print(f"Duration: {self.stats.duration:.2f} seconds")
        print(f"Total Requests: {self.stats.total_requests}")
        print(f"Successful: {self.stats.successful} ({self.stats.success_rate:.1f}%)")
        print(f"Failed: {self.stats.failed}")
        print(f"Rate Limited: {self.stats.rate_limited}")
        print(f"Errors: {self.stats.errors}")
        print(f"Requests/Second: {self.stats.requests_per_second:.2f}")
        print(f"Avg Response Time: {self.stats.avg_response_time:.2f} ms")

        if self.stats.response_times:
            sorted_times = sorted(self.stats.response_times)
            p50 = sorted_times[len(sorted_times) // 2]
            p95 = sorted_times[int(len(sorted_times) * 0.95)]
            p99 = sorted_times[int(len(sorted_times) * 0.99)]
            print(f"Response Time (p50): {p50:.2f} ms")
            print(f"Response Time (p95): {p95:.2f} ms")
            print(f"Response Time (p99): {p99:.2f} ms")

        print(f"{'='*60}\n")


async def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Load test TheButton API with simulated button presses"
    )
    parser.add_argument(
        "--api-url",
        default="http://localhost:8000",
        help="API base URL (default: http://localhost:8000)",
    )
    parser.add_argument(
        "--requests",
        type=int,
        default=100,
        help="Total number of requests to send (default: 100)",
    )
    parser.add_argument(
        "--concurrent",
        type=int,
        default=10,
        help="Number of concurrent requests (default: 10)",
    )
    parser.add_argument(
        "--rate",
        type=float,
        default=None,
        help="Maximum requests per second (default: no limit)",
    )
    parser.add_argument(
        "--bypass-pow",
        action="store_true",
        help="Use PoW bypass (requires POW_BYPASS=true on server)",
    )
    parser.add_argument(
        "--progress-interval",
        type=int,
        default=50,
        help="Print progress every N requests (default: 50)",
    )

    args = parser.parse_args()

    tester = LoadTester(
        api_url=args.api_url,
        bypass_pow=args.bypass_pow,
        rate_limit=args.rate,
    )

    try:
        await tester.run_test(
            total_requests=args.requests,
            concurrent=args.concurrent,
            progress_interval=args.progress_interval,
        )
        tester.print_results()
    except KeyboardInterrupt:
        print("\n\nTest interrupted by user")
        tester.print_results()
    except Exception as e:
        print(f"\n\nTest failed: {e}")
        tester.print_results()
        raise


if __name__ == "__main__":
    asyncio.run(main())

