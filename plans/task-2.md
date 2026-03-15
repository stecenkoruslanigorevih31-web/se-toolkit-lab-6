# Task 2: The Documentation Agent — Implementation Plan

## Overview
Extend the Task 1 agent with tool support and an agentic loop. The agent will use `read_file` and `list_files` tools to navigate the project wiki and answer questions with source references.

## Tool Definitions

### `read_file`
- **Purpose:** Read contents of a file from the project repository
- **Parameters:** `path` (string) — relative path from project root
- **Returns:** File contents as string, or error message if file doesn't exist
- **Security:** Validate path doesn't contain `../` traversal; must be within project root

### `list_files`
- **Purpose:** List files and directories at a given path
- **Parameters:** `path` (string) — relative directory path from project root
- **Returns:** Newline-separated listing of entries
- **Security:** Validate path doesn't contain `../` traversal; must be within project root

## Tool Schema (OpenAI Function Calling)

```python
tools = [
    {
        "type": "function",
        "function": {
            "name": "read_file",
            "description": "Read the contents of a file in the project",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative path from project root"}
                },
                "required": ["path"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "list_files",
            "description": "List files in a directory",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Relative directory path from project root"}
                },
                "required": ["path"]
            }
        }
    }
]
```

## Agentic Loop

```
1. Send user question + tool definitions to LLM
2. Parse response:
   - If tool_calls present:
     a. Execute each tool
     b. Append results as tool messages
     c. Send back to LLM
     d. Repeat (max 10 iterations)
   - If no tool_calls (final answer):
     a. Extract answer text
     b. Extract source reference (file path + section anchor)
     c. Output JSON and exit
3. If max iterations reached, use whatever answer is available
```

## Message Format

```python
messages = [
    {"role": "system", "content": SYSTEM_PROMPT},
    {"role": "user", "content": question}
]

# After tool calls:
messages.append({
    "role": "assistant",
    "content": None,
    "tool_calls": [...]
})

messages.append({
    "role": "tool",
    "tool_call_id": "...",
    "content": tool_result
})
```

## System Prompt Strategy

The system prompt will instruct the LLM to:
1. Use `list_files` to discover wiki files when unsure where to look
2. Use `read_file` to read relevant wiki sections
3. Include source references in the format `wiki/filename.md#section-anchor`
4. Only provide final answer after gathering sufficient information

## Path Security

- Resolve all paths using `Path.resolve()` to get absolute paths
- Check that resolved path starts with project root
- Reject any path containing `..` or absolute paths
- Return error message for invalid paths

## Output Format

```json
{
  "answer": "Explanation text here.",
  "source": "wiki/git-workflow.md#resolving-merge-conflicts",
  "tool_calls": [
    {
      "tool": "list_files",
      "args": {"path": "wiki"},
      "result": "file1.md\nfile2.md"
    },
    {
      "tool": "read_file",
      "args": {"path": "wiki/git-workflow.md"},
      "result": "file contents..."
    }
  ]
}
```

## Error Handling

- File not found: Return error message as tool result
- Path traversal attempt: Return security error
- LLM API errors: Exit with code 1, error to stderr
- Max iterations (10): Stop loop, use available answer

## Testing Strategy

1. Test question requiring `read_file`: "How do you resolve a merge conflict?"
   - Expects `read_file` in tool_calls
   - Expects `wiki/git-workflow.md` in source

2. Test question requiring `list_files`: "What files are in the wiki?"
   - Expects `list_files` in tool_calls
   - Expects non-empty tool_calls array
