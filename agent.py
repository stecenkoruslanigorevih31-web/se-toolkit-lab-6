#!/usr/bin/env python3
"""CLI agent that calls an LLM and returns structured JSON answer."""

import json
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv


def load_env():
    """Load environment variables from .env.agent.secret."""
    env_path = Path(__file__).parent / ".env.agent.secret"
    load_dotenv(env_path)


def call_llm(question: str) -> dict:
    """Call the LLM API and return structured answer."""
    api_key = os.getenv("LLM_API_KEY")
    api_base = os.getenv("LLM_API_BASE", "http://localhost:8080/v1").rstrip("/")
    model = os.getenv("LLM_MODEL", "qwen3-coder-plus")

    if not api_key:
        raise RuntimeError("LLM_API_KEY not set in environment")

    url = f"{api_base}/chat/completions"

    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {api_key}"
    }

    payload = {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a helpful assistant. Answer concisely."},
            {"role": "user", "content": question}
        ],
        "temperature": 0.1,
    }

    with httpx.Client(timeout=60.0) as client:
        response = client.post(url, headers=headers, json=payload)
        response.raise_for_status()
        data = response.json()

        # Extract answer from OpenAI-compatible format
        answer = data["choices"][0]["message"]["content"].strip()

        return {
            "answer": answer,
            "tool_calls": []  # Empty array for Task 1
        }


def main():
    """Entry point: parse args, call LLM, output JSON."""
    if len(sys.argv) < 2:
        print("Usage: uv run agent.py \"<question>\"", file=sys.stderr)
        sys.exit(1)

    question = sys.argv[1]

    try:
        load_env()
        result = call_llm(question)

        # Only valid JSON to stdout
        print(json.dumps(result, ensure_ascii=False))
        sys.exit(0)

    except Exception as e:
        # All errors to stderr
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
