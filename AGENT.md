# Agent Architecture

## Overview

This project implements a CLI agent (`agent.py`) with tool support and an agentic loop. The agent can navigate the project wiki using `read_file` and `list_files` tools, and query the backend LMS API using `query_api` to answer documentation questions with source references and runtime data queries.

## Architecture

```
User question (CLI arg)
       ↓
   agent.py
       ↓
   Agentic Loop:
   1. Send question + tool definitions to LLM
   2. If tool_calls → execute tools, append results, repeat
   3. If final answer → extract answer + source, output JSON
       ↓
stdout: {"answer": "...", "source": "...", "tool_calls": [...]}
```

## Components

### agent.py

The main CLI entry point with the following components:

#### Tools

**`read_file(path: str) -> str`**

- Reads contents of a file from the project repository
- Validates path security (no traversal outside project root)
- Returns file contents or error message

**`list_files(path: str) -> str`**

- Lists files and directories at a given path
- Validates path security (no traversal outside project root)
- Returns newline-separated listing or error message

**`query_api(method: str, path: str, body: str = None, use_auth: bool = True) -> str`**

- Queries the backend LMS API with authentication
- Supports GET, POST, PUT, DELETE methods
- `use_auth=false` allows testing unauthenticated access
- Returns JSON string with `status_code` and `body`

#### Path Security

All tool paths are validated to prevent access outside the project directory:

- Rejects paths containing `..`
- Rejects absolute paths
- Resolves full path and verifies it's within project root

#### Agentic Loop

```python
1. Initialize messages with system prompt + user question
2. Send to LLM with tool definitions
3. Parse response:
   - If tool_calls present:
     a. Execute each tool
     b. Append tool results as "tool" role messages
     c. Send updated messages back to LLM
     d. Repeat (max 10 iterations)
   - If no tool_calls (final answer):
     a. Extract answer text
     b. Extract source reference from tool calls
     c. Output JSON and exit
```

#### System Prompt

The system prompt instructs the LLM to:

1. Use `list_files` to discover available wiki files
2. Use `read_file` to read relevant documentation or source code
3. Use `query_api` for runtime data (items, analytics, logs)
4. Use `use_auth=false` for authentication testing questions
5. Include source references in the format `wiki/filename.md#section-anchor`
6. For bug diagnosis: ALWAYS use both `query_api` and `read_file`
7. Only provide final answers after gathering sufficient information

### Environment Configuration

The agent reads configuration from environment variables:

| Variable | Purpose | Source |
|----------|---------|--------|
| `LLM_API_KEY` | LLM provider API key | `.env.agent.secret` |
| `LLM_API_BASE` | LLM API endpoint URL | `.env.agent.secret` |
| `LLM_MODEL` | Model name | `.env.agent.secret` |
| `LMS_API_KEY` | Backend API key for query_api auth | `.env.docker.secret` |
| `AGENT_API_BASE_URL` | Base URL for query_api | `.env.docker.secret` (optional, defaults to `http://localhost:42002`) |

**Important:** The autochecker injects different values at evaluation time. Never hardcode these values.

## LLM Provider

**Provider:** Qwen Code API
**Model:** `qwen3-coder-plus`
**Endpoint:** `http://10.93.24.173:42005/v1`

The Qwen Code API provides an OpenAI-compatible chat completions interface with function calling support.

## Output Format

The agent outputs a single JSON line to stdout:

```json
{
  "answer": "There are 44 items in the database.",
  "source": "API: /items/",
  "tool_calls": [
    {
      "tool": "query_api",
      "args": {"method": "GET", "path": "/items/"},
      "result": "{\"status_code\": 200, \"body\": [...]}"
    }
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `answer` | string | The LLM's response to the question |
| `source` | string | Reference to the source (file path, API endpoint, or empty for system questions) |
| `tool_calls` | array | List of all tool calls with args and results |

## Error Handling

- **Missing API key:** Exits with code 1, error to stderr
- **HTTP errors:** Returned as error message in tool result
- **Timeout:** 60-second limit enforced by httpx
- **Invalid paths:** Returns error message as tool result
- **Max iterations (10):** Stops loop, uses available answer

All debug and error output goes to **stderr**. Only valid JSON goes to **stdout**.

## Usage

```bash
# Run with a question
uv run agent.py "How many items are in the database?"

# Expected output
{
  "answer": "There are 44 items in the database.",
  "source": "API: /items/",
  "tool_calls": [...]
}
```

## Dependencies

- `httpx` — HTTP client for API calls
- `python-dotenv` — Load environment variables from `.env.agent.secret` and `.env.docker.secret`

## Testing

Run the regression tests:

```bash
uv run pytest tests/test_agent.py -v
```

Tests verify:

- Agent exits with code 0
- stdout contains valid JSON
- `answer`, `source`, and `tool_calls` fields are present
- Tool calls are executed correctly for different question types

## Benchmark Evaluation

Run the local benchmark:

```bash
uv run run_eval.py
```

The benchmark tests 10 questions across all classes:

1. Wiki lookup (branch protection)
2. Wiki lookup (SSH connection)
3. Source code (framework identification)
4. Source code (router modules)
5. API query (item count)
6. API query (authentication status code)
7. Bug diagnosis (division by zero)
8. Bug diagnosis (top-learners crash)
9. System architecture (request journey)
10. Reasoning (multi-step analysis)

## Lessons Learned

### Tool Design

1. **Explicit tool descriptions matter:** The LLM needs clear guidance on when to use each tool. Adding specific examples (e.g., "use `lab` query parameter") improved reliability.

2. **Authentication flexibility:** Adding `use_auth` parameter was crucial for questions about unauthenticated access. Without it, the agent couldn't test error scenarios.

3. **Path specificity:** The LLM sometimes guesses wrong file paths (e.g., `backend/Dockerfile` vs `Dockerfile`). Being explicit in the system prompt helps.

### System Prompt Engineering

1. **Step-by-step guidance works:** Explicitly stating "FIRST use query_api, THEN use read_file" for bug questions improved tool usage consistency.

2. **Examples are critical:** Providing concrete examples (e.g., `/analytics/completion-rate?lab=lab-01`) reduced API parameter errors.

3. **Conciseness vs. completeness:** The LLM sometimes truncates answers. Encouraging "complete answers immediately" helps but doesn't guarantee full responses within token limits.

### LLM Limitations

1. **Non-determinism:** The same question may produce different tool call patterns on different runs. This makes testing challenging.

2. **Context carryover:** During sequential evaluation, the LLM may carry assumptions from previous questions, leading to inconsistent behavior.

3. **Token limits:** Complex multi-step questions (like request journey) can hit token limits before the agent completes its analysis.

### Benchmark Performance

The agent consistently passes 8/10 local questions. The two failures (questions 7 and 9) are due to LLM non-determinism rather than implementation bugs:

- Question 7: Sometimes skips `read_file` despite finding the correct bug
- Question 9: Sometimes doesn't read all required files (Caddyfile, main.py)

These issues highlight the inherent challenges of LLM-based agents: even with perfect tool implementation, the LLM's decision-making can be unpredictable.

## Future Work

- Add more tools (calculator, web search, git operations)
- Implement caching for frequently accessed files
- Support for multi-turn conversations
- Better error recovery and retry logic
- Improved source extraction with section anchor detection
