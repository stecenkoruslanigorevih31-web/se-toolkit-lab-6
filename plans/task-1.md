# Task 1: Call an LLM from Code — Implementation Plan

## LLM Provider

- **Provider:** Qwen Code API
- **Model:** qwen3-coder-plus
- **Endpoint:** OpenAI-compatible chat completions API
- **Auth:** Bearer token from .env.agent.secret

## Environment Setup

- Copy `.env.agent.example` to `.env.agent.secret`
- Set `LLM_API_KEY`, `LLM_API_BASE`, `LLM_MODEL`
- API key is loaded via `python-dotenv`

## Agent Architecture

### Input/Output Flow

```
User question (CLI arg) → agent.py → LLM API → JSON answer (stdout)
```

### Steps

1. Parse CLI argument (question string) from `sys.argv[1]`
2. Load environment variables from `.env.agent.secret` using `dotenv`
3. Build OpenAI-compatible request to LLM API:
   - Endpoint: `{LLM_API_BASE}/chat/completions`
   - Headers: `Authorization: Bearer {LLM_API_KEY}`, `Content-Type: application/json`
   - Payload: `model`, `messages` (system + user), `temperature`
4. Send HTTP POST request with `httpx` (60s timeout)
5. Parse JSON response, extract answer from `choices[0].message.content`
6. Output structured JSON to stdout: `{"answer": "...", "tool_calls": []}`
7. All debug/error output goes to stderr

### Output Format

```json
{"answer": "Representational State Transfer.", "tool_calls": []}
```

## Error Handling

- **Missing API key:** Raise `RuntimeError`, exit code 1
- **Timeout:** 60 seconds max via `httpx.Client(timeout=60.0)`
- **HTTP errors:** `response.raise_for_status()` propagates error
- **Invalid JSON:** Exception caught, error to stderr, exit code 1
- **Network errors:** Caught, error to stderr, exit code 1
- **No CLI argument:** Print usage to stderr, exit code 1

## Testing Strategy

- 1 regression test in `tests/test_agent.py`:
  - Run `agent.py` as subprocess with a test question
  - Parse stdout as JSON
  - Validate `answer` field exists and is non-empty string
  - Validate `tool_calls` field exists and is a list
  - Exit code is 0

## Dependencies

- `httpx` — HTTP client (already in pyproject.toml)
- `python-dotenv` — load env from file (need to add if missing)
