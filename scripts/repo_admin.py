#!/usr/bin/env python3
"""RepoOps repository provisioning command.

The command surface is intentionally narrow:

    /repoops repo create <name> <public|private>

The token is read from REPOOPS_TOKEN and is never printed.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol

COMMAND_RE = re.compile(
    r"/repoops repo create ([A-Za-z0-9._-]{1,100}) (private|public)"
)


def die(message: str, code: int = 1) -> "NoReturn":
    print(json.dumps({"ok": False, "error": message}, separators=(",", ":")))
    raise SystemExit(code)


def load_config(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    cfg = data.get("repository_admin")
    if not isinstance(cfg, dict):
        raise ValueError("repository_admin config missing")
    return cfg


@dataclass(frozen=True)
class CreateCommand:
    name: str
    visibility: str


def parse_command(body: str) -> CreateCommand:
    match = COMMAND_RE.fullmatch(body.strip())
    if not match:
        raise ValueError(
            "invalid command; expected /repoops repo create <name> <private|public>"
        )
    return CreateCommand(*match.groups())


class RestApi(Protocol):
    def request(
        self, url: str, method: str = "GET", payload: dict[str, Any] | None = None
    ) -> tuple[int, dict[str, Any]]: ...


class GitHubRest:
    def __init__(self, token: str):
        if not token:
            raise ValueError("REPOOPS_TOKEN is not configured")
        self._token = token

    def request(
        self, url: str, method: str = "GET", payload: dict[str, Any] | None = None
    ) -> tuple[int, dict[str, Any]]:
        data = None if payload is None else json.dumps(payload).encode("utf-8")
        headers = {
            "Authorization": f"Bearer {self._token}",
            "Accept": "application/vnd.github+json",
            "X-GitHub-Api-Version": "2022-11-28",
            "User-Agent": "RepoOps/0.1",
        }
        if data is not None:
            headers["Content-Type"] = "application/json"
        req = urllib.request.Request(url, data=data, method=method, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=30) as response:
                raw = response.read().decode("utf-8") or "{}"
                return response.status, json.loads(raw)
        except urllib.error.HTTPError as exc:
            raw = exc.read().decode("utf-8", errors="replace") or "{}"
            try:
                parsed = json.loads(raw)
            except json.JSONDecodeError:
                parsed = {"message": "HTTP error"}
            return exc.code, parsed


def provision(
    cfg: dict[str, Any],
    association: str,
    command: CreateCommand,
    api: RestApi,
) -> dict[str, Any]:
    allowed = cfg.get("allowed_author_associations", ["OWNER"])
    if not isinstance(allowed, list) or association not in allowed:
        return {
            "ok": False,
            "error": "author_association_denied",
            "repository": command.name,
            "visibility": command.visibility,
        }

    owner = str(cfg.get("owner", "")).strip()
    owner_type = str(cfg.get("owner_type", "user")).strip().lower()
    if not owner or owner_type not in {"user", "organization"}:
        raise ValueError("repository_admin owner/owner_type invalid")

    repo_url = f"https://api.github.com/repos/{owner}/{command.name}"
    status, existing = api.request(repo_url)

    created = False
    if status == 200:
        result = existing
    elif status == 404:
        if owner_type == "user":
            identity_status, identity = api.request("https://api.github.com/user")
            if identity_status != 200:
                return {
                    "ok": False,
                    "error": "authenticated_user_lookup_failed",
                    "http_status": identity_status,
                    "repository": command.name,
                    "visibility": command.visibility,
                }
            authenticated_login = str(identity.get("login", "")).strip()
            if authenticated_login.casefold() != owner.casefold():
                return {
                    "ok": False,
                    "error": "authenticated_user_owner_mismatch",
                    "repository": command.name,
                    "configured_owner": owner,
                    "authenticated_owner": authenticated_login,
                    "visibility": command.visibility,
                }
            endpoint = "https://api.github.com/user/repos"
        else:
            endpoint = f"https://api.github.com/orgs/{owner}/repos"

        payload = {
            "name": command.name,
            "description": str(cfg.get("default_description", "Managed by RepoOps")),
            "private": command.visibility == "private",
            "auto_init": bool(cfg.get("auto_init", True)),
            "has_issues": bool(cfg.get("has_issues", True)),
            "has_projects": bool(cfg.get("has_projects", True)),
            "has_wiki": bool(cfg.get("has_wiki", False)),
            "delete_branch_on_merge": bool(cfg.get("delete_branch_on_merge", True)),
        }
        status, result = api.request(endpoint, method="POST", payload=payload)
        if status != 201:
            return {
                "ok": False,
                "error": "repository_create_failed",
                "http_status": status,
                "message": str(result.get("message", "unknown error"))[:160],
                "repository": command.name,
                "visibility": command.visibility,
            }
        created = True
    else:
        return {
            "ok": False,
            "error": "repository_lookup_failed",
            "http_status": status,
            "message": str(existing.get("message", "unknown error"))[:160],
            "repository": command.name,
            "visibility": command.visibility,
        }

    actual_private = bool(result.get("private"))
    requested_private = command.visibility == "private"
    if actual_private != requested_private:
        return {
            "ok": False,
            "error": "visibility_mismatch_refusing_mutation",
            "repository": command.name,
            "requested_visibility": command.visibility,
            "actual_visibility": "private" if actual_private else "public",
        }

    return {
        "ok": True,
        "repository": command.name,
        "full_name": str(result.get("full_name", f"{owner}/{command.name}")),
        "created": created,
        "visibility": command.visibility,
        "url": str(result.get("html_url", repo_url)),
        "secret_exposed": False,
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    parser.add_argument("--comment", required=True)
    parser.add_argument("--association", required=True)
    args = parser.parse_args()

    try:
        cfg = load_config(args.config)
        command = parse_command(args.comment)
        api = GitHubRest(os.environ.get("REPOOPS_TOKEN", ""))
        result = provision(cfg, args.association, command, api)
    except (ValueError, OSError, json.JSONDecodeError) as exc:
        die(str(exc))

    print(json.dumps(result, separators=(",", ":"), ensure_ascii=False))
    return 0 if result.get("ok") else 2


if __name__ == "__main__":
    raise SystemExit(main())
