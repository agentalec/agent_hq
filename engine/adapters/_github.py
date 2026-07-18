"""Thin GitHub REST client (D4): PAT auth via `AGENT_HQ_TOKEN`, read at
request time so a missing/rotated token fails at the call site, not at
import/construction time. Shared by the `github-issues`, `github-comment`,
and `pr-review` adapters rather than each wrapping `requests` separately.
"""

from __future__ import annotations

import os

import requests

BASE_URL = "https://api.github.com"


class GitHubClient:
    def __init__(self, base_url: str = BASE_URL):
        self.base_url = base_url

    def _headers(self) -> dict:
        token = os.environ.get("AGENT_HQ_TOKEN")
        if not token:
            raise RuntimeError("AGENT_HQ_TOKEN is not set")
        return {
            "Authorization": f"Bearer {token}",
            "Accept": "application/vnd.github+json",
        }

    def _request(self, method: str, path: str, *, json=None, params=None):
        resp = requests.request(
            method,
            f"{self.base_url}{path}",
            headers=self._headers(),
            json=json,
            params=params,
        )
        if not 200 <= resp.status_code < 300:
            raise RuntimeError(
                f"GitHub {method} {path} -> {resp.status_code}: {resp.text[:500]}"
            )
        if resp.status_code == 204 or not resp.content:
            return None
        return resp.json()

    def get(self, path: str, *, json=None, params=None):
        return self._request("GET", path, json=json, params=params)

    def post(self, path: str, *, json=None, params=None):
        return self._request("POST", path, json=json, params=params)

    def patch(self, path: str, *, json=None, params=None):
        return self._request("PATCH", path, json=json, params=params)

    def list_workflow_runs(self, repo: str, name: str) -> list[dict]:
        data = self.get(f"/repos/{repo}/actions/runs") or {}
        return [run for run in data.get("workflow_runs", []) if run.get("name") == name]

    def combined_check_status(self, repo: str, ref: str) -> str:
        data = self.get(f"/repos/{repo}/commits/{ref}/status")
        return data["state"]


def git_credential_args() -> list[str]:
    """Same credential-helper shim as `engine.state.GitJsonStateStore._cred_args`."""
    if os.environ.get("AGENT_HQ_TOKEN"):
        return [
            "-c",
            "credential.helper=!f(){ echo username=x-access-token; "
            'echo "password=$AGENT_HQ_TOKEN"; };f',
        ]
    return []
