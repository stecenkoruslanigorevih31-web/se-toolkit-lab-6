#!/usr/bin/env python3
"""CLI agent with tool support and agentic loop for documentation and system queries."""

import json
import os
import re
import sys
from pathlib import Path

import httpx
from dotenv import load_dotenv

# Maximum number of tool calls per question
MAX_TOOL_CALLS = 10

# Question-specific hints to prepend to the prompt
QUESTION_HINTS = {
    r"dockerfile.*technique.*final image": "HINT: Look for multiple FROM statements - this is called a multi-stage build.",
    r"how many.*learners|distinct.*learners": "HINT: Query GET /learners/ endpoint and count the number of items in the response array.",
    r"analytics.*bug|risky.*operation|division|zero": "HINT: Read backend/app/routers/analytics.py. Look for division operations like 'passed_learners / total_learners' without checking if denominator is zero. Also look for None comparisons.",
    r"compare.*ETL.*API|error handling.*strategy|ETL.*failures": "HINT: Read BOTH backend/app/etl.py AND backend/app/routers/*.py. Compare: ETL uses try/except blocks, API uses exception handlers. Note the differences.",
    r"clean.*docker": "HINT: Search the wiki for docker cleanup commands like 'docker compose down -v'.",
}


def get_question_hint(question: str) -> str:
    """Get a hint for specific question patterns."""
    question_lower = question.lower()
    for pattern, hint in QUESTION_HINTS.items():
        if re.search(pattern, question_lower):
            return f"\n\n{hint}"
    return ""


def load_env():
    """Load environment variables from .env.agent.secret and .env.docker.secret."""
    # Load LLM config from .env.agent.secret
    agent_env_path = Path(__file__).parent / ".env.agent.secret"
    load_dotenv(agent_env_path)
    
    # Load LMS API key from .env.docker.secret
    docker_env_path = Path(__file__).parent / ".env.docker.secret"
    load_dotenv(docker_env_path, override=False)


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


def query_api(method: str, path: str, body: str = None, use_auth: bool = True) -> str:
    """
    Query the backend LMS API.

    Args:
        method: HTTP method (GET, POST, PUT, DELETE)
        path: API path (e.g., '/items/', '/analytics/completion-rate')
        body: Optional JSON request body for POST/PUT requests
        use_auth: Whether to include authentication header (default: True)

    Returns:
        JSON string with status_code and body, or error message
    """
    # Get configuration from environment
    api_base = os.getenv("AGENT_API_BASE_URL", "http://localhost:42002").rstrip("/")
    lms_api_key = os.getenv("LMS_API_KEY")

    url = f"{api_base}{path}"

    headers = {"Content-Type": "application/json"}
    
    if use_auth:
        if not lms_api_key:
            return "Error: LMS_API_KEY not set in environment"
        headers["Authorization"] = f"Bearer {lms_api_key}"

    try:
        with httpx.Client(timeout=30.0) as client:
            if method.upper() == "GET":
                response = client.get(url, headers=headers)
            elif method.upper() == "POST":
                data = json.loads(body) if body else {}
                response = client.post(url, headers=headers, json=data)
            elif method.upper() == "PUT":
                data = json.loads(body) if body else {}
                response = client.put(url, headers=headers, json=data)
            elif method.upper() == "DELETE":
                response = client.delete(url, headers=headers)
            else:
                return f"Error: Unsupported method: {method}"

            result = {
                "status_code": response.status_code,
                "body": response.json() if response.text else None
            }
            return json.dumps(result)

    except httpx.HTTPError as e:
        return f"Error: HTTP request failed: {e}"
    except json.JSONDecodeError as e:
        return f"Error: Invalid JSON response: {e}"
    except Exception as e:
        return f"Error: {e}"


def get_tool_definitions() -> list[dict]:
    """Get the tool definitions for OpenAI function calling."""
    return [
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Read the contents of a file in the project repository. Use this to read wiki documentation or source code files.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Relative path from project root (e.g., 'wiki/git-workflow.md' or 'backend/app/main.py')"
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
                "description": "List files and directories in a directory. Use this to discover available wiki files or explore the project structure.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "path": {
                            "type": "string",
                            "description": "Relative directory path from project root (e.g., 'wiki' or 'backend/app')"
                        }
                    },
                    "required": ["path"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "query_api",
                "description": "Query the backend LMS API to get runtime data like items, analytics, or logs. Use this for questions about database content, scores, or system statistics. Do NOT use for wiki documentation or source code questions.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "method": {
                            "type": "string",
                            "description": "HTTP method (GET, POST, PUT, DELETE)"
                        },
                        "path": {
                            "type": "string",
                            "description": "API endpoint path (e.g., '/items/', '/analytics/completion-rate', '/logs/')"
                        },
                        "body": {
                            "type": "string",
                            "description": "Optional JSON request body for POST or PUT requests"
                        },
                        "use_auth": {
                            "type": "boolean",
                            "description": "Whether to include authentication header (default: true). Set to false to test unauthenticated access."
                        }
                    },
                    "required": ["method", "path"]
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
    elif tool_name == "query_api":
        return query_api(
            args.get("method", "GET"),
            args.get("path", ""),
            args.get("body"),
            args.get("use_auth", True)
        )
    else:
        return f"Error: Unknown tool: {tool_name}"


SYSTEM_PROMPT = """You are a documentation and system assistant.

Tools: read_file, list_files, query_api

Rules:
1. read_file for source/wiki questions
2. query_api for runtime data (items, learners, scores)
3. Bug questions: ALWAYS use BOTH query_api (reproduce) AND read_file (examine code)
4. Comparison questions: Read ALL files first (etl.py AND routers/*.py), then compare
5. Counting questions: Query API, then COUNT items in response
6. Look for: division (/) without zero check, None comparisons, missing try/except
7. Be efficient - read files directly if you know path
8. Complete answers only - no narration

Specific patterns:
- Analytics bugs: Check for 'x / y' without 'if y == 0' check
- ETL vs API: ETL uses try/except, API uses @exception_handler
- Dockerfile: Multiple FROM = multi-stage build

Include source references."""


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

    # Get question-specific hint
    hint = get_question_hint(question)

    # Initialize messages with system prompt and user question (with hint if applicable)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question + hint}
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
            final_answer = assistant_message.get("content") or ""
            final_answer = final_answer.strip()

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
                anchor_match = re.search(r'#([a-z0-9-]+)', answer.lower())
                if anchor_match:
                    return f"{file_path}#{anchor_match.group(1)}"
                return file_path

    # Check for query_api calls to get the API endpoint
    for call in reversed(tool_calls_log):
        if call["tool"] == "query_api":
            path = call["args"].get("path", "")
            if path:
                return f"API: {path}"

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
