# Task 1: Call an LLM from Code — Implementation Plan

## LLM Provider
- **Provider:** Qwen Code API
- **Model:** qwen3-coder-plus
- **Endpoint:** http://10.93.24.173:8080/v1 (на VM)
- **Auth:** Bearer token из .env.agent.secret

## Agent Architecture
1. Parse CLI argument (question string)
2. Load environment variables from .env.agent.secret
3. Build OpenAI-compatible request to LLM API
4. Send async HTTP request with httpx
5. Parse JSON response, extract "answer" field
6. Output structured JSON to stdout: {"answer": "...", "tool_calls": []}
7. Log debug info to stderr

## Error Handling
- Timeout: 60 seconds max
- Invalid JSON: exit code 1, error to stderr
- Network errors: retry once, then fail gracefully

## Testing Strategy
- 1 regression test: run agent.py as subprocess, validate JSON output
