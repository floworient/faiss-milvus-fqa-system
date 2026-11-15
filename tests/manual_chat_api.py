"""Manually verify the running chat API against the configured live model.

This script is intentionally excluded from pytest discovery because it calls a
real model provider and may consume quota.
"""

from __future__ import annotations

import argparse
import sys
from typing import Any

import httpx


def call_chat_api(base_url: str, question: str, timeout: float) -> dict[str, Any]:
    with httpx.Client(base_url=base_url, timeout=timeout, trust_env=False) as client:
        health = client.get("/health")
        health.raise_for_status()

        response = client.post(
            "/api/v1/chat/completions",
            json={
                "question": question,
                "retrieval_mode": "keyword",
                "top_k": 3,
                "candidate_k": 10,
            },
        )
        response.raise_for_status()
        return response.json()


def main() -> int:
    parser = argparse.ArgumentParser(description="Call the local live chat API once.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    parser.add_argument("--question", default="请用一句话回答：你好。")
    parser.add_argument("--timeout", type=float, default=60.0)
    args = parser.parse_args()

    try:
        result = call_chat_api(args.base_url.rstrip("/"), args.question, args.timeout)
    except httpx.HTTPStatusError as error:
        response = error.response
        print(f"API call failed: HTTP {response.status_code}", file=sys.stderr)
        print(response.text, file=sys.stderr)
        return 1
    except httpx.HTTPError as error:
        print(f"API call failed: {error}", file=sys.stderr)
        return 1

    tier = result.get("provider_tier")
    print(f"session_id: {result.get('session_id')}")
    print(f"provider_tier: {tier}")
    print(f"answer: {result.get('answer', '')}")

    if tier not in (1, 2):
        reason = result.get("metadata", {}).get("fallback_reason", "unknown")
        print(
            f"model unavailable or invalid tier; fallback_reason: {reason}",
            file=sys.stderr,
        )
        return 2

    print("live model call succeeded")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
