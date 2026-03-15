# Agent Architecture

## Overview

This project implements a CLI agent (`agent.py`) that calls an LLM and returns structured JSON answers. This is the foundation for the multi-turn agent with tool support that will be built in Tasks 2-3.

## Architecture

```
User question (CLI arg)
       ↓
   agent.py
       ↓
   LLM API (Qwen Code)
       ↓
   JSON response
       ↓
stdout: {"answer": "...", "tool_calls": []}
```

## Components

### agent.py

The main CLI entry point. Responsibilities:
- Parse command-line arguments
- Load environment configuration
- Call the LLM API
- Return structured JSON output

### Environment Configuration

The agent reads configuration from `.env.agent.secret`:

| Variable | Description |
|----------|-------------|
| `LLM_API_KEY` | API key for authentication |
| `LLM_API_BASE` | LLM endpoint URL (OpenAI-compatible) |
| `LLM_MODEL` | Model name to use |

## LLM Provider

**Provider:** Qwen Code API
**Model:** `qwen3-coder-plus`
**Endpoint:** `http://10.93.24.173:42005/v1`

The Qwen Code API provides an OpenAI-compatible chat completions interface, making integration straightforward using standard HTTP requests.

## Output Format

The agent outputs a single JSON line to stdout:

```json
{"answer": "Representational State Transfer.", "tool_calls": []}
```

| Field | Type | Description |
|-------|------|-------------|
| `answer` | string | The LLM's response to the question |
| `tool_calls` | array | Empty for Task 1, populated in Task 2+ |

## Error Handling

- **Missing API key:** Exits with code 1, error to stderr
- **HTTP errors:** Propagated via `raise_for_status()`
- **Timeout:** 60-second limit enforced by httpx
- **Invalid responses:** Caught and reported to stderr

All debug and error output goes to **stderr**. Only valid JSON goes to **stdout**.

## Usage

```bash
# Run with a question
uv run agent.py "What does REST stand for?"

# Expected output
{"answer": "Representational State Transfer.", "tool_calls": []}
```

## Dependencies

- `httpx` — HTTP client for API calls
- `python-dotenv` — Load environment variables from `.env.agent.secret`

## Testing

Run the regression test:

```bash
pytest tests/test_agent.py
```

The test verifies:
- Agent exits with code 0
- stdout contains valid JSON
- `answer` field is present and non-empty
- `tool_calls` field is present and is a list

## Future Work (Tasks 2-3)

- Add tool support (calculator, API queries, file operations)
- Implement agentic loop for multi-turn interactions
- Add system prompt with domain knowledge
- Support tool call tracking in output
