"""
Automated Git Synchronization for Web Dashboard.
Commits and pushes updated data.json to GitHub repository, triggering GitHub Pages auto-deploy.
Gracefully skips if no remote origin is configured.
"""

import logging
import subprocess

logger = logging.getLogger(__name__)


def sync_dashboard_to_git() -> bool:
    """
    Checks if a git remote origin exists, and if data.json was modified,
    commits and pushes the update.
    """
    try:
        # Verify remote origin exists
        remotes = subprocess.run(
            ["git", "remote", "get-url", "origin"],
            capture_output=True,
            text=True,
        )
        if remotes.returncode != 0:
            return False

        # Stage data.json
        subprocess.run(["git", "add", "dashboard/data.json"], capture_output=True)

        # Check if there are staged differences
        diff = subprocess.run(
            ["git", "diff", "--cached", "--name-only"],
            capture_output=True,
            text=True,
        )
        if "dashboard/data.json" not in diff.stdout:
            return True

        # Commit
        subprocess.run(
            ["git", "commit", "-m", "chore: update dashboard market data [skip ci]"],
            capture_output=True,
        )

        # Pull and merge remote changes with -X ours to prevent any conflicts
        subprocess.run(
            ["git", "pull", "--no-rebase", "-X", "ours", "origin", "master", "-m", "chore: merge remote market data"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        # Push to remote
        push = subprocess.run(
            ["git", "push", "origin", "master"],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if push.returncode == 0:
            logger.info("Successfully pushed dashboard/data.json to GitHub.")
            return True
        else:
            logger.warning(f"Git push warning: {push.stderr.strip()}")
            return False
    except Exception as e:
        logger.debug(f"Git sync skipped: {e}")
        return False
