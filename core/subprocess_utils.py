"""Utility functions for subprocess calls with clean environment handling."""
import logging
import os
import subprocess
from pathlib import Path
from typing import Optional, Union

logger = logging.getLogger(__name__)


def get_clean_env() -> dict[str, str]:
    """Get environment without our virtual env variables."""
    env = os.environ.copy()
    if "VIRTUAL_ENV" in env:
        del env["VIRTUAL_ENV"]
    if "POETRY_ACTIVE" in env:
        del env["POETRY_ACTIVE"]
    return env


def run_command(
    cmd: list[str],
    cwd: Optional[Union[str, Path]] = None,
    capture_output: bool = True,
    text: bool = True,
    check: bool = False,
    clean_env: bool = True,
    extra_env: Optional[dict[str, str]] = None,
    debug: bool = False,
) -> subprocess.CompletedProcess:
    """
    Run a command with optional clean environment and debug logging.

    Args:
        cmd: Command and arguments to run
        cwd: Working directory
        capture_output: Whether to capture stdout/stderr
        text: Whether to return text output
        check: Whether to raise exception on non-zero exit
        clean_env: Whether to use clean environment (without VIRTUAL_ENV)
        extra_env: Additional environment variables to add
        debug: Whether to log debug information

    Returns:
        CompletedProcess result
    """
    working_dir = str(cwd) if cwd else None

    # Prepare environment
    if clean_env:
        env = get_clean_env()
    else:
        env = os.environ.copy()

    if extra_env:
        env.update(extra_env)

    if debug:
        logger.info(f"Running command: {' '.join(cmd)}")
        if working_dir:
            logger.info(f"Working directory: {working_dir}")

    try:
        result = subprocess.run(
            cmd, cwd=working_dir, capture_output=capture_output, text=text, check=check, env=env
        )

        if debug and capture_output:
            if result.stdout:
                logger.info(f"Command stdout:\n{result.stdout}")
            if result.stderr:
                logger.info(f"Command stderr:\n{result.stderr}")
            logger.info(f"Command exit code: {result.returncode}")

        return result

    except subprocess.CalledProcessError as e:
        if debug:
            logger.error(f"Command failed with exit code {e.returncode}")
            if hasattr(e, "stdout") and e.stdout:
                logger.error(f"Failed command stdout:\n{e.stdout}")
            if hasattr(e, "stderr") and e.stderr:
                logger.error(f"Failed command stderr:\n{e.stderr}")
        raise


def run_git_command(
    cmd: list[str], cwd: Optional[Union[str, Path]] = None, debug: bool = False
) -> subprocess.CompletedProcess:
    """
    Run a git command with error handling.

    Args:
        cmd: Git command and arguments
        cwd: Working directory
        debug: Whether to log debug information

    Returns:
        CompletedProcess result

    Raises:
        RuntimeError: If git command fails
    """
    try:
        return run_command(
            cmd,
            cwd=cwd,
            check=True,
            clean_env=False,  # Git usually doesn't need clean env
            debug=debug,
        )
    except subprocess.CalledProcessError as e:
        raise RuntimeError(f"Git command failed: {' '.join(cmd)}\n{e.stderr}")


def run_ce_install_command(
    subcommand: list[str], cwd: Union[str, Path], debug: bool = False
) -> subprocess.CompletedProcess:
    """
    Run a ce_install command with clean environment.

    Args:
        subcommand: ce_install subcommand and arguments (without 'bin/ce_install')
        cwd: Working directory (should be infra repo path)
        debug: Whether to log debug information

    Returns:
        CompletedProcess result
    """
    cmd = ["bin/ce_install"] + subcommand
    return run_command(cmd, cwd=cwd, clean_env=True, debug=debug)


def run_make_command(
    target: str,
    cwd: Union[str, Path],
    extra_env: Optional[dict[str, str]] = None,
    debug: bool = False,
) -> subprocess.CompletedProcess:
    """
    Run a make command with clean environment.

    Args:
        target: Make target to run
        cwd: Working directory
        extra_env: Additional environment variables
        debug: Whether to log debug information

    Returns:
        CompletedProcess result
    """
    cmd = ["make", target]
    return run_command(cmd, cwd=cwd, clean_env=True, extra_env=extra_env, debug=debug)
