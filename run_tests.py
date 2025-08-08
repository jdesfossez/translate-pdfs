#!/usr/bin/env python3
"""
Test runner script for the PDF Translation Service.
"""

import subprocess
import sys
from pathlib import Path


def run_tests(with_coverage=False):
    """Run the test suite."""
    print("Running PDF Translation Service Tests")
    print("=" * 50)

    # Ensure we're in the right directory
    project_root = Path(__file__).parent

    # Run pytest with optional coverage
    cmd = [
        sys.executable, "-m", "pytest",
        "tests/",
        "-v",
        "--tb=short",
        "-x",  # Stop on first failure
    ]

    if with_coverage:
        cmd.extend([
            "--cov=src",
            "--cov-report=html",
            "--cov-report=term-missing"
        ])
    
    try:
        result = subprocess.run(cmd, cwd=project_root, check=False)
        return result.returncode
    except KeyboardInterrupt:
        print("\nTests interrupted by user")
        return 1
    except Exception as e:
        print(f"Error running tests: {e}")
        return 1


def run_linting():
    """Run code linting."""
    print("\nRunning Code Linting")
    print("=" * 20)
    
    # Check if tools are available
    tools = ["black", "isort", "flake8"]
    for tool in tools:
        try:
            subprocess.run([tool, "--version"], capture_output=True, check=True)
        except (subprocess.CalledProcessError, FileNotFoundError):
            print(f"Warning: {tool} not found, skipping...")
            continue
        
        print(f"Running {tool}...")
        if tool == "black":
            subprocess.run([tool, "--check", "src/", "tests/", "main.py"])
        elif tool == "isort":
            subprocess.run([tool, "--check-only", "src/", "tests/", "main.py"])
        elif tool == "flake8":
            subprocess.run([tool, "src/", "tests/", "main.py"])


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Run tests for PDF Translation Service")
    parser.add_argument("--lint", action="store_true", help="Run linting checks")
    parser.add_argument("--coverage", action="store_true", help="Run tests with coverage reporting")
    parser.add_argument("--no-gpu", action="store_true", help="Skip GPU tests")

    args = parser.parse_args()

    if args.lint:
        run_linting()

    exit_code = run_tests(with_coverage=args.coverage)
    sys.exit(exit_code)
