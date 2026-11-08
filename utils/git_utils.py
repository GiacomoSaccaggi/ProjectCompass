"""
░░██████╗░██╗████████╗░░░░░░██╗░░░██╗████████╗██╗██╗░░░░░░██████╗
░██╔════╝░██║╚══██╔══╝░░░░░░██║░░░██║╚══██╔══╝██║██║░░░░░██╔════╝
░██║░░██╗░██║░░░██║░░░█████╗██║░░░██║░░░██║░░░██║██║░░░░░╚█████╗░
░██║░░╚██╗██║░░░██║░░░╚════╝██║░░░██║░░░██║░░░██║██║░░░░░░╚═══██╗
░╚██████╔╝██║░░░██║░░░░░░░░░╚██████╔╝░░░██║░░░██║███████╗██████╔╝
░░╚═════╝░╚═╝░░░╚═╝░░░░░░░░░░╚═════╝░░░░╚═╝░░░╚═╝╚══════╝╚═════╝░
"""

from __future__ import annotations

import os
import subprocess
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from logging_config import logger


class GitSyncUtils:
    """Parent class encapsulating optional Git repository synchronization for Analyses/.

    Uses standard `git` CLI invocations via `subprocess.run` to initialize or pull
    from a remote repository on application startup and to commit/push flow and
    analysis changes on save when `USE_GIT_SYNC` (or `USE_GITLAB_REPO`) is enabled.
    """

    def __init__(self, dir_path: str = "", data_dir: str = "", **kwargs: Any) -> None:
        """Initialize Git synchronization state and forward cooperative kwargs."""
        self.dir_path: str = dir_path
        self.data_dir: str = data_dir or dir_path
        super().__init__(dir_path=dir_path, data_dir=self.data_dir, **kwargs)

    @staticmethod
    def _inject_git_token(repo_url: str, token: str = "") -> str:
        """Embed an authentication token into an HTTP/HTTPS Git URL when provided."""
        raw_url = (repo_url or "").strip()
        clean_token = (token or "").strip()
        if not raw_url or not clean_token:
            return raw_url
        if not raw_url.startswith(("http://", "https://")):
            return raw_url
        parts = urlsplit(raw_url)
        if "@" in parts.netloc:
            return raw_url
        auth_netloc = f"oauth2:{clean_token}@{parts.netloc}"
        return urlunsplit((parts.scheme, auth_netloc, parts.path, parts.query, parts.fragment))

    @staticmethod
    def _sanitize_git_text(text: str, token: str = "") -> str:
        """Redact any credential token from command arguments or error messages before logging."""
        if not text:
            return ""
        clean_token = (token or "").strip()
        if clean_token and clean_token in text:
            return text.replace(clean_token, "***")
        return text

    def _is_git_sync_enabled(self) -> bool:
        """Return True when Git synchronization is enabled via environment or Flask config."""
        env_sync = os.environ.get("USE_GIT_SYNC")
        if env_sync is not None:
            return env_sync.strip().lower() in ("true", "1", "yes")
        env_legacy = os.environ.get("USE_GITLAB_REPO")
        if env_legacy is not None:
            return env_legacy.strip().lower() in ("true", "1", "yes")

        from flask import current_app, has_app_context

        if has_app_context():
            return bool(
                current_app.config.get("USE_GIT_SYNC")
                or current_app.config.get("USE_GITLAB_REPO")
            )
        return False

    def _is_git_sync_on_save_enabled(self) -> bool:
        """Return True when both Git sync and automatic commit/push on save are enabled."""
        if not self._is_git_sync_enabled():
            return False
        env_on_save = os.environ.get("GIT_SYNC_ON_SAVE")
        if env_on_save is not None:
            return env_on_save.strip().lower() in ("true", "1", "yes")

        from flask import current_app, has_app_context

        if has_app_context():
            return bool(current_app.config.get("GIT_SYNC_ON_SAVE", True))
        return True

    def _run_git_cmd(
        self,
        args: list[str],
        cwd: str,
        token: str = "",
        timeout: int = 30,
    ) -> subprocess.CompletedProcess[str]:
        """Execute a non-interactive git command inside `cwd`."""
        env = dict(os.environ)
        env["GIT_TERMINAL_PROMPT"] = "0"
        return subprocess.run(
            ["git", *args],
            cwd=cwd,
            env=env,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )

    def _ensure_git_identity(self, target_dir: str) -> None:
        """Ensure local git user.name and user.email are configured for automated commits."""
        self._run_git_cmd(["config", "user.name", "ProjectCompass"], cwd=target_dir)
        self._run_git_cmd(["config", "user.email", "compass@cluster.local"], cwd=target_dir)

    def git_init_or_clone(
        self,
        repo_url: str | None = None,
        branch: str | None = None,
        target_dir: str | None = None,
        token: str | None = None,
    ) -> bool:
        """Initialize or clone the Git repository into `target_dir`, or pull if already initialized."""
        resolved_dir = target_dir or getattr(self, "save_folder_path", "")
        resolved_url = (repo_url if repo_url is not None else os.environ.get("GIT_REPO_URL", "")).strip()
        resolved_branch = (branch if branch is not None else os.environ.get("GIT_BRANCH", "main")).strip() or "main"
        resolved_token = (token if token is not None else os.environ.get("GIT_TOKEN", "")).strip()

        if not resolved_dir or not resolved_url:
            return False

        os.makedirs(resolved_dir, exist_ok=True)
        git_meta_dir = os.path.join(resolved_dir, ".git")
        auth_url = self._inject_git_token(resolved_url, resolved_token)

        try:
            if os.path.isdir(git_meta_dir):
                self._ensure_git_identity(resolved_dir)
                self._run_git_cmd(["remote", "set-url", "origin", auth_url], cwd=resolved_dir, token=resolved_token)
                return self.git_pull(target_dir=resolved_dir, branch=resolved_branch, token=resolved_token)

            entries = [e for e in os.listdir(resolved_dir) if not e.startswith(".")]
            if not entries:
                clone_res = self._run_git_cmd(
                    ["clone", "--branch", resolved_branch, auth_url, "."],
                    cwd=resolved_dir,
                    token=resolved_token,
                )
                if clone_res.returncode == 0 and os.path.isdir(git_meta_dir):
                    self._ensure_git_identity(resolved_dir)
                    return True

            # Fallback when target_dir already has files or remote repository has no commits yet
            init_res = self._run_git_cmd(["init", "-b", resolved_branch], cwd=resolved_dir)
            if init_res.returncode != 0:
                self._run_git_cmd(["init"], cwd=resolved_dir)
                self._run_git_cmd(["checkout", "-b", resolved_branch], cwd=resolved_dir)

            self._ensure_git_identity(resolved_dir)
            self._run_git_cmd(["remote", "remove", "origin"], cwd=resolved_dir)
            self._run_git_cmd(["remote", "add", "origin", auth_url], cwd=resolved_dir, token=resolved_token)
            self.git_pull(target_dir=resolved_dir, branch=resolved_branch, token=resolved_token)
            return True
        except Exception as exc:
            logger.warning(
                f"Git initialization/clone failed for {resolved_dir}: "
                f"{self._sanitize_git_text(str(exc), resolved_token)}"
            )
            return False

    def git_pull(
        self,
        target_dir: str | None = None,
        branch: str | None = None,
        token: str | None = None,
    ) -> bool:
        """Pull latest changes from origin; on conflict, log a warning and keep local version."""
        resolved_dir = target_dir or getattr(self, "save_folder_path", "")
        resolved_branch = (branch if branch is not None else os.environ.get("GIT_BRANCH", "main")).strip() or "main"
        resolved_token = (token if token is not None else os.environ.get("GIT_TOKEN", "")).strip()

        if not resolved_dir or not os.path.isdir(os.path.join(resolved_dir, ".git")):
            return False

        try:
            pull_res = self._run_git_cmd(
                ["pull", "--no-rebase", "origin", resolved_branch],
                cwd=resolved_dir,
                token=resolved_token,
            )
            if pull_res.returncode == 0:
                return True

            err_msg = self._sanitize_git_text(pull_res.stderr or pull_res.stdout, resolved_token)
            logger.warning(f"Git pull encountered an issue or conflict (keeping local files): {err_msg}")
            self._run_git_cmd(["merge", "--abort"], cwd=resolved_dir)
            return False
        except Exception as exc:
            logger.warning(
                f"Git pull failed for {resolved_dir}: {self._sanitize_git_text(str(exc), resolved_token)}"
            )
            return False

    def git_commit_and_push(
        self,
        target_dir: str | None = None,
        message: str = "Sync analyses",
        branch: str | None = None,
        token: str | None = None,
    ) -> bool:
        """Stage all files in `target_dir`, commit with `message`, and push to origin."""
        resolved_dir = target_dir or getattr(self, "save_folder_path", "")
        resolved_branch = (branch if branch is not None else os.environ.get("GIT_BRANCH", "main")).strip() or "main"
        resolved_token = (token if token is not None else os.environ.get("GIT_TOKEN", "")).strip()

        if not resolved_dir:
            return False

        git_meta_dir = os.path.join(resolved_dir, ".git")
        if not os.path.isdir(git_meta_dir):
            repo_url = os.environ.get("GIT_REPO_URL", "").strip()
            if repo_url:
                self.git_init_or_clone(
                    repo_url=repo_url,
                    branch=resolved_branch,
                    target_dir=resolved_dir,
                    token=resolved_token,
                )
            if not os.path.isdir(git_meta_dir):
                return False

        try:
            self._ensure_git_identity(resolved_dir)
            add_res = self._run_git_cmd(["add", "-A"], cwd=resolved_dir)
            if add_res.returncode != 0:
                return False

            commit_res = self._run_git_cmd(
                ["commit", "-m", message or "Sync analyses"],
                cwd=resolved_dir,
            )
            combined_out = (commit_res.stdout or "") + (commit_res.stderr or "")
            if commit_res.returncode != 0 and "nothing to commit" not in combined_out.lower():
                logger.warning(
                    f"Git commit failed: {self._sanitize_git_text(combined_out, resolved_token)}"
                )
                return False

            push_res = self._run_git_cmd(
                ["push", "-u", "origin", f"HEAD:{resolved_branch}"],
                cwd=resolved_dir,
                token=resolved_token,
            )
            if push_res.returncode != 0:
                err_out = self._sanitize_git_text(push_res.stderr or push_res.stdout, resolved_token)
                logger.warning(f"Git push failed: {err_out}")
                return False
            return True
        except Exception as exc:
            logger.warning(
                f"Git commit and push failed for {resolved_dir}: "
                f"{self._sanitize_git_text(str(exc), resolved_token)}"
            )
            return False
