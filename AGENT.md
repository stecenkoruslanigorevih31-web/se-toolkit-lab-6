# Agent Architecture

## Overview

This project implements a CLI agent (`agent.py`) with tool support and an agentic loop. The agent can navigate the project wiki using `read_file` and `list_files` tools to answer documentation questions with source references.

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
2. Use `read_file` to read relevant documentation
3. Include source references in the format `wiki/filename.md#section-anchor`
4. Only provide final answers after gathering sufficient information

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

The Qwen Code API provides an OpenAI-compatible chat completions interface with function calling support.

## Output Format

The agent outputs a single JSON line to stdout:

```json
{
  "answer": "Edit the conflicting file, choose which changes to keep, then stage and commit.",
  "source": "wiki/git-workflow.md#resolving-merge-conflicts",
  "tool_calls": [
    {
      "tool": "list_files",
      "args": {"path": "wiki"},
      "result": "git-workflow.md\n..."
    },
    {
      "tool": "read_file",
      "args": {"path": "wiki/git-workflow.md"},
      "result": "..."
    }
  ]
}
```

| Field | Type | Description |
|-------|------|-------------|
| `answer` | string | The LLM's response to the question |
| `source` | string | Reference to the wiki section (file path + anchor) |
| `tool_calls` | array | List of all tool calls with args and results |

## Error Handling

- **Missing API key:** Exits with code 1, error to stderr
- **HTTP errors:** Propagated via `raise_for_status()`
- **Timeout:** 60-second limit enforced by httpx
- **Invalid paths:** Returns error message as tool result
- **Max iterations (10):** Stops loop, uses available answer

All debug and error output goes to **stderr**. Only valid JSON goes to **stdout**.

## Usage

```bash
# Run with a question
uv run agent.py "How do you resolve a merge conflict?"

# Expected output
{
  "answer": "...",
  "source": "wiki/git-workflow.md#resolving-merge-conflicts",
  "tool_calls": [...]
}
```

## Dependencies

- `httpx` — HTTP client for API calls
- `python-dotenv` — Load environment variables from `.env.agent.secret`

## Testing

Run the regression tests:

```bash
uv run pytest tests/test_agent.py -v
```

Tests verify:

- Agent exits with code 0
- stdout contains valid JSON
- `answer`, `source`, and `tool_calls` fields are present
- Tool calls are executed correctly

## Tool Call Schema

Tools are defined using OpenAI's function calling format:

```json
{
  "type": "function",
  "function": {
    "name": "read_file",
    "description": "Read the contents of a file...",
    "parameters": {
      "type": "object",
      "properties": {
        "path": {
          "type": "string",
          "description": "Relative path from project root"
        }
      },
      "required": ["path"]
    }
  }
}
```

## Future Work

- Add more tools (calculator, API queries, web search)
- Improve source extraction with better section anchor detection
- Add caching for frequently accessed files
- Support for multi-turn conversations
