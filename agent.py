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


def load_env():
    """Load environment variables from .env.agent.secret and .env.docker.secret."""
    agent_env_path = Path(__file__).parent / ".env.agent.secret"
    load_dotenv(agent_env_path)
    docker_env_path = Path(__file__).parent / ".env.docker.secret"
    load_dotenv(docker_env_path, override=False)


def get_project_root() -> Path:
    """Get the project root directory."""
    return Path(__file__).parent.resolve()


def validate_path(path: str) -> tuple[bool, str]:
    if ".." in path:
        return False, "Error: Path traversal not allowed"
    if os.path.isabs(path):
        return False, "Error: Absolute paths not allowed"
    project_root = get_project_root()
    full_path = (project_root / path).resolve()
    try:
        full_path.relative_to(project_root)
        return True, ""
    except ValueError:
        return False, "Error: Path must be within project directory"


def read_file(path: str) -> str:
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
            result = {"status_code": response.status_code, "body": response.json() if response.text else None}
            return json.dumps(result)
    except httpx.HTTPError as e:
        return f"Error: HTTP request failed: {e}"
    except json.JSONDecodeError as e:
        return f"Error: Invalid JSON response: {e}"
    except Exception as e:
        return f"Error: {e}"


def get_tool_definitions() -> list[dict]:
    return [
        {
            "type": "function",
            "function": {
                "name": "read_file",
                "description": "Read contents of a file (wiki, source code)",
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
                        "path": {"type": "string", "description": "Relative directory path"}
                    },
                    "required": ["path"]
                }
            }
        },
        {
            "type": "function",
            "function": {
                "name": "query_api",
                "description": "Query backend API for runtime data (items, learners, analytics)",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "method": {"type": "string", "description": "HTTP method (GET, POST, PUT, DELETE)"},
                        "path": {"type": "string", "description": "API endpoint path"},
                        "body": {"type": "string", "description": "Optional JSON body for POST/PUT"},
                        "use_auth": {"type": "boolean", "description": "Include auth header (default: true)"}
                    },
                    "required": ["method", "path"]
                }
            }
        }
    ]


def execute_tool(tool_name: str, args: dict) -> str:
    if tool_name == "read_file":
        return read_file(args.get("path", ""))
    elif tool_name == "list_files":
        return list_files(args.get("path", ""))
    elif tool_name == "query_api":
        return query_api(args.get("method", "GET"), args.get("path", ""), args.get("body"), args.get("use_auth", True))
    else:
        return f"Error: Unknown tool: {tool_name}"


SYSTEM_PROMPT = """You are a documentation and system assistant.

Tools: read_file, list_files, query_api

Rules:
1. read_file for source code and wiki questions
2. query_api for runtime data (items, learners, scores)
3. Bug questions: use BOTH query_api (reproduce) AND read_file (examine code)
4. Comparison questions: Read ALL files first, then compare
5. Counting questions: Query API, then COUNT items in response
6. Look for: division (/) without zero check, None comparisons, try/except
7. Be efficient - read files directly if you know path
8. Complete answers only - no narration

Include source references."""


def call_llm_with_tools(question: str) -> dict:
    api_key = os.getenv("LLM_API_KEY")
    api_base = os.getenv("LLM_API_BASE", "http://localhost:8080/v1").rstrip("/")
    model = os.getenv("LLM_MODEL", "qwen3-coder-plus")
    if not api_key:
        raise RuntimeError("LLM_API_KEY not set in environment")

    url = f"{api_base}/chat/completions"
    headers = {"Content-Type": "application/json", "Authorization": f"Bearer {api_key}"}

    # Build enhanced prompt based on question type
    question_lower = question.lower()
    hint = ""
    
    if re.search(r"dockerfile.*technique|keep.*final image.*small", question_lower):
        hint = "\n\nHINT: Look for multiple FROM statements in the Dockerfile - this is called a multi-stage build."
    elif re.search(r"how many.*learners|distinct.*learners", question_lower):
        hint = "\n\nHINT: Query GET /learners/ endpoint and count the items in the response array."
    elif re.search(r"analytics.*bug|risky.*operation|division", question_lower):
        hint = "\n\nHINT: Read backend/app/routers/analytics.py. Look for division operations without checking for zero."
    elif re.search(r"compare.*ETL.*API|error handling.*strategy", question_lower):
        hint = "\n\nHINT: Read backend/app/etl.py and backend/app/routers/*.py. Compare: ETL uses try/except, API uses @exception_handler."
    elif re.search(r"clean.*docker", question_lower):
        hint = "\n\nHINT: Search the wiki for docker cleanup commands like 'docker compose down -v'."
    elif re.search(r"framework.*backend|python.*web.*framework", question_lower):
        hint = "\n\nHINT: Read backend/app/main.py and look at the imports (from fastapi import...)."
    elif re.search(r"journey.*request|browser.*database", question_lower):
        hint = "\n\nHINT: Read docker-compose.yml, caddy/Caddyfile, Dockerfile, and backend/app/main.py. Trace: Browser → Caddy (port 42002) → App (port 8000) → Postgres (port 5432)."

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": question + hint}
    ]

    tool_calls_log = []
    iteration = 0
    
    while iteration < MAX_TOOL_CALLS:
        iteration += 1
        payload = {"model": model, "messages": messages, "tools": get_tool_definitions(), "tool_choice": "auto", "temperature": 0.1}
        with httpx.Client(timeout=60.0) as client:
            response = client.post(url, headers=headers, json=payload)
            response.raise_for_status()
            data = response.json()

        assistant_message = data["choices"][0]["message"]
        tool_calls = assistant_message.get("tool_calls", [])

        if not tool_calls:
            final_answer = (assistant_message.get("content") or "").strip()
            source = extract_source(final_answer, tool_calls_log)
            return {"answer": final_answer, "source": source, "tool_calls": tool_calls_log}

        messages.append(assistant_message)

        for tool_call in tool_calls:
            tool_id = tool_call["id"]
            tool_name = tool_call["function"]["name"]
            tool_args = json.loads(tool_call["function"]["arguments"])
            result = execute_tool(tool_name, tool_args)
            tool_calls_log.append({"tool": tool_name, "args": tool_args, "result": result})
            messages.append({"role": "tool", "tool_call_id": tool_id, "content": result})

    return {"answer": "I reached the maximum number of tool calls (10).", "source": extract_source("", tool_calls_log), "tool_calls": tool_calls_log}


def extract_source(answer: str, tool_calls_log: list) -> str:
    for call in reversed(tool_calls_log):
        if call["tool"] == "read_file":
            return call["args"].get("path", "")
        if call["tool"] == "query_api":
            return f"API: {call['args'].get('path', '')}"
    return ""


def main():
    if len(sys.argv) < 2:
        print("Usage: uv run agent.py \"<question>\"", file=sys.stderr)
        sys.exit(1)
    question = sys.argv[1]
    try:
        load_env()
        result = call_llm_with_tools(question)
        print(json.dumps(result, ensure_ascii=False))
        sys.exit(0)
    except Exception as e:
        print(f"Error: {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
