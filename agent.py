#!/usr/bin/env python3
"""CLI agent with tool support and agentic loop for documentation queries."""

import json
import os
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

# Maximum number of tool calls per question
MAX_TOOL_CALLS = 10


def load_env():
    """Load environment variables from .env.agent.secret."""
    env_path = Path(__file__).parent / ".env.agent.secret"
    load_dotenv(env_path)


def get_project_root() -> Path:
    """Get the project root directory."""
    return Path(__file__).parent.resolve()


def validate_path(path: str) -> tuple[bool, str]:
    """
    Validate that a path is within the project directory.
    
    Returns:
        Tuple of (is_valid, error_message)
    """
    # Check for path traversal attempts
    if ".." in path:
        return False, "Error: Path traversal not allowed"
    
    # Check for absolute paths
    if os.path.isabs(path):
        return False, "Error: Absolute paths not allowed"
    
    # Resolve the full path
    project_root = get_project_root()
    full_path = (project_root / path).resolve()
    
    # Ensure the resolved path is within project root
    try:
        full_path.relative_to(project_root)
        return True, ""
    except ValueError:
        return False, f"Error: Path must be within project directory"


def read_file(path: str) -> str:
    """
    Read the contents of a file in the project.
    
    Args:
        path: Relative path from project root
        
    Returns:
        File contents or error message
    """
    is_valid, error = validate_path(path)
    if not is_valid:
        return error
    
    project_root = get_project_root()
    full_path = project_root / path
    
    if not full_path.exists():
        return f"Error: File not found: {path}"
    
    if not full_path.is_file():
        return f"Error: Not a file: {path}"
    
    try:
        return full_path.read_text(encoding="utf-8")
    except Exception as e:
        return f"Error reading file: {e}"


def list_files(path: str) -> str:
    """
    List files and directories at a given path.
    
    Args:
        path: Relative directory path from project root
        
    Returns:
        Newline-separated listing or error message
    """
    is_valid, error = validate_path(path)
    if not is_valid:
        return error
    
    project_root = get_project_root()
    full_path = project_root / path
    
    if not full_path.exists():
        return f"Error: Directory not found: {path}"
    
    if not full_path.is_dir():
        return f"Error: Not a directory: {path}"
    
    try:
        entries = sorted([e.name for e in full_path.iterdir()])
        return "\n".join(entries)
    except Exception as e:
        return f"Error listing directory: {e}"


def get_tool_definitions() -> list[dict]:
    """Get the tool definitions for OpenAI function calling."""
    return [
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Read the contents of a file in the project repository. Use this to read wiki documentation.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Relative path from project root (e.g., 'wiki/git-workflow.md')"
                        }
                    },
                    "required": ["path"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "list_files",
                "description": "List files and directories in a directory. Use this to discover available wiki files.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Relative directory path from project root (e.g., 'wiki')"
                        }
                    },
                    "required": ["path"]
                }
            }
        }
    ]


def execute_tool(tool_name: str, args: dict) -> str:
    """
    Execute a tool and return the result.
    
    Args:
        tool_name: Name of the tool to execute
        args: Arguments for the tool
        
    Returns:
        Tool result as string
    """
    if tool_name == "read_file":
        return read_file(args.get("path", ""))
    elif tool_name == "list_files":
        return list_files(args.get("path", ""))
    else:
        return f"Error: Unknown tool: {tool_name}"


SYSTEM_PROMPT = """You are a documentation assistant for a software engineering lab. You have access to tools that let you read files and list directories in the project wiki.

Your task is to answer questions by finding relevant information in the wiki documentation.

Guidelines:
1. Use `list_files` to discover what files are available in the wiki directory
2. Use `read_file` to read the contents of relevant wiki files
3. After gathering information, provide a clear, concise answer
4. Include a source reference in your final answer using the format: wiki/filename.md#section-anchor
5. The section anchor should be the heading that contains the answer (lowercase, spaces replaced with hyphens)
6. Only provide a final answer when you have found sufficient information

Available tools:
- `read_file`: Read contents of a file given its path
- `list_files`: List files in a directory

Always think step by step. First explore what's available, then read relevant files, then provide your answer with source."""


def call_llm_with_tools(question: str) -> dict:
    """
    Call the LLM API with tool support and agentic loop.
    
    Args:
        question: The user's question
        
    Returns:
        Dictionary with answer, source, and tool_calls
    """
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

    # Initialize messages with system prompt and user question
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question}
    ]

    # Track all tool calls for output
    tool_calls_log = []
    
    # Agentic loop
    iteration = 0
    while iteration < MAX_TOOL_CALLS:
        iteration += 1
        
        payload = {
            "model": model,
            "messages": messages,
            "tools": get_tool_definitions(),
            "tool_choice": "auto",
            "temperature": 0.1,
        }

        with httpx.Client(timeout=60.0) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        assistant_message = data["choices"][0]["message"]

        # Check if there are tool calls
        tool_calls = assistant_message.get("tool_calls", [])
        
        if not tool_calls:
            # No tool calls - this is the final answer
            final_answer = assistant_message.get("content", "").strip()
            
            # Try to extract source from the answer
            source = extract_source(final_answer, tool_calls_log)
            
            return {
                "answer": final_answer,
                "source": source,
                "tool_calls": tool_calls_log
            }

        # Add assistant message with tool calls to messages
        messages.append(assistant_message)

        # Execute each tool call
        for tool_call in tool_calls:
            tool_id = tool_call["id"]
            tool_name = tool_call["function"]["name"]
            tool_args = json.loads(tool_call["function"]["arguments"])
            
            # Execute the tool
            result = execute_tool(tool_name, tool_args)
            
            # Log the tool call
            tool_calls_log.append({
                "tool": tool_name,
                "args": tool_args,
                "result": result
            })

            # Add tool result to messages
            messages.append({
                "role": "tool",
                "tool_call_id": tool_id,
                "content": result
            })

    # Max iterations reached
    return {
        "answer": "I reached the maximum number of tool calls (10). Based on the information gathered, I couldn't find a complete answer.",
        "source": extract_source("", tool_calls_log),
        "tool_calls": tool_calls_log
    }


def extract_source(answer: str, tool_calls_log: list) -> str:
    """
    Extract or generate a source reference from tool calls.
    
    Args:
        answer: The final answer text
        tool_calls_log: List of tool calls made
        
    Returns:
        Source reference string
    """
    # Look for read_file calls to get the last file read
    for call in reversed(tool_calls_log):
        if call["tool"] == "read_file":
            file_path = call["args"].get("path", "")
            if file_path:
                # Try to find a section anchor in the answer
                # Common patterns: #section-name, ##section-name
                import re
                anchor_match = re.search(r'#([a-z0-9-]+)', answer.lower())
                if anchor_match:
                    return f"{file_path}#{anchor_match.group(1)}"
                return file_path
    
    return ""


def main():
    """Entry point: parse args, call LLM with tools, output JSON."""
    if len(sys.argv) < 2:
        print("Usage: uv run agent.py \"<question>\"", file=sys.stderr)
        sys.exit(1)

    question = sys.argv[1]

    try:
        load_env()
        result = call_llm_with_tools(question)

        # Only valid JSON to stdout
        print(json.dumps(result, ensure_ascii=False))
        sys.exit(0)

    except Exception as e:
        # All errors to stderr
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
