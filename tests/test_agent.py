"""Regression tests for agent.py CLI."""

import json
import subprocess
from pathlib import Path


def get_project_root() -> Path:
    """Get the project root directory."""
    return Path(__file__).parent.parent


def run_agent(question: str) -> subprocess.CompletedProcess:
    """Run the agent with a question and return the result."""
    return subprocess.run(
        ["uv", "run", "agent.py", question],
        capture_output=True,
        text=True,
        cwd=get_project_root(),
    )


def parse_json_output(result: subprocess.CompletedProcess) -> dict:
    """Parse the JSON output from the agent."""
    assert result.returncode == 0, f"Agent exited with code {result.returncode}, stderr: {result.stderr}"
    stdout = result.stdout.strip()
    assert stdout, "stdout is empty"
    return json.loads(stdout)


def test_task1_agent_returns_structured_json():
    """Test that agent.py outputs valid JSON with required fields (Task 1)."""
    result = run_agent("What is 2 + 2?")
    response = parse_json_output(result)

    assert "answer" in response, "Missing 'answer' field in response"
    assert isinstance(response["answer"], str), "'answer' must be a string"
    assert len(response["answer"]) > 0, "'answer' is empty"

    assert "tool_calls" in response, "Missing 'tool_calls' field in response"
    assert isinstance(response["tool_calls"], list), "'tool_calls' must be a list"


def test_task2_merge_conflict_uses_read_file():
    """Test that agent uses read_file to answer merge conflict question (Task 2)."""
    result = run_agent("How do you resolve a merge conflict?")
    response = parse_json_output(result)

    # Check required fields
    assert "answer" in response, "Missing 'answer' field"
    assert "source" in response, "Missing 'source' field"
    assert "tool_calls" in response, "Missing 'tool_calls' field"
    
    # Check that answer is non-empty
    assert len(response["answer"]) > 0, "'answer' is empty"
    
    # Check that tool_calls were made
    assert len(response["tool_calls"]) > 0, "No tool calls were made"
    
    # Check that read_file was used
    tool_names = [call["tool"] for call in response["tool_calls"]]
    assert "read_file" in tool_names, "read_file was not used"
    
    # Check that source contains wiki/git-workflow.md
    assert "wiki/git-workflow.md" in response["source"], \
        f"Expected 'wiki/git-workflow.md' in source, got: {response['source']}"


def test_task2_list_files_in_wiki():
    """Test that agent uses list_files to answer wiki directory question (Task 2)."""
    result = run_agent("What files are in the wiki?")
    response = parse_json_output(result)

    # Check required fields
    assert "answer" in response, "Missing 'answer' field"
    assert "source" in response, "Missing 'source' field"
    assert "tool_calls" in response, "Missing 'tool_calls' field"
    
    # Check that answer is non-empty
    assert len(response["answer"]) > 0, "'answer' is empty"
    
    # Check that tool_calls were made
    assert len(response["tool_calls"]) > 0, "No tool calls were made"
    
    # Check that list_files was used
    tool_names = [call["tool"] for call in response["tool_calls"]]
    assert "list_files" in tool_names, "list_files was not used"
