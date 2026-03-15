"""Regression tests for agent.py CLI."""

import json
import subprocess
import sys
from pathlib import Path


def test_agent_returns_structured_json():
    """Test that agent.py outputs valid JSON with required fields."""
    # Get the project root directory (parent of tests/)
    project_root = Path(__file__).parent.parent
    
    result = subprocess.run(
        ["uv", "run", "agent.py", "What is 2 + 2?"],
        capture_output=True,
        text=True,
        cwd=project_root,
    )

    assert result.returncode == 0, f"Agent exited with code {result.returncode}, stderr: {result.stderr}"

    stdout = result.stdout.strip()
    assert stdout, "stdout is empty"

    response = json.loads(stdout)

    assert "answer" in response, "Missing 'answer' field in response"
    assert isinstance(response["answer"], str), "'answer' must be a string"
    assert len(response["answer"]) > 0, "'answer' is empty"

    assert "tool_calls" in response, "Missing 'tool_calls' field in response"
    assert isinstance(response["tool_calls"], list), "'tool_calls' must be a list"
