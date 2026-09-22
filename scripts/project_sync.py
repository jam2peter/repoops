#!/usr/bin/env python3
"""RepoOps GitHub Project V2 reconciler."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any, Protocol

DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")


def fail(message: str) -> "NoReturn":
    print(f"ERROR: {message}", file=sys.stderr)
    raise SystemExit(1)


def load_config(path: str) -> dict[str, Any]:
    with open(path, "r", encoding="utf-8") as fh:
        data = json.load(fh)
    cfg = data.get("project_sync")
    if not isinstance(cfg, dict):
        raise ValueError("project_sync config missing")
    validate_config(cfg)
    return cfg


def validate_config(cfg: dict[str, Any]) -> None:
    owner = cfg.get("project_owner")
    if not isinstance(owner, dict):
        raise ValueError("project_owner missing")
    if owner.get("type") not in {"user", "organization"}:
        raise ValueError("project_owner.type must be user|organization")
    if not isinstance(owner.get("login"), str) or not owner["login"].strip():
        raise ValueError("project_owner.login missing")
    number = cfg.get("project_number")
    if not isinstance(number, int) or number < 1:
        raise ValueError("project_number invalid")
    repos = cfg.get("repositories")
    if not isinstance(repos, list) or not repos:
        raise ValueError("repositories missing")
    for repo in repos:
        if not isinstance(repo, str) or repo.count("/") != 1:
            raise ValueError(f"invalid repository: {repo}")
    marker = cfg.get("metadata_marker", "REPOOPS")
    if not isinstance(marker, str) or not re.fullmatch(r"[A-Z0-9_]{2,40}", marker):
        raise ValueError("metadata_marker invalid")
    fields = cfg.get("fields")
    if not isinstance(fields, dict) or "status" not in fields:
        raise ValueError("fields.status is required")


def parse_metadata(body: str | None, marker: str) -> dict[str, str]:
    pattern = re.compile(
        rf"<!--\s*{re.escape(marker)}\s*(.*?)-->",
        re.S | re.I,
    )
    match = pattern.search(body or "")
    if not match:
        return {}
    out: dict[str, str] = {}
    for raw in match.group(1).splitlines():
        raw = raw.strip()
        if not raw or raw.startswith("#") or "=" not in raw:
            continue
        key, value = raw.split("=", 1)
        out[key.strip().lower()] = value.strip()
    return out


def normalize_operator(
    meta: dict[str, str], issue: dict[str, Any], cfg: dict[str, Any]
) -> str:
    fields = cfg.get("fields", {})
    op_cfg = fields.get("operator", {}) if isinstance(fields, dict) else {}
    metadata_key = str(op_cfg.get("metadata_key", "operator"))
    explicit = meta.get(metadata_key, "").strip()
    if explicit:
        return explicit[:100]

    labels = {
        str(item.get("name", "")).casefold()
        for item in issue.get("labels", [])
        if isinstance(item, dict)
    }
    mapping = cfg.get("operator_labels", {})
    if isinstance(mapping, dict):
        for label, operator in mapping.items():
            if str(label).casefold() in labels:
                return str(operator)[:100]
    return str(op_cfg.get("default", "Unassigned"))[:100]


class Api(Protocol):
    def rest(self, url: str) -> Any: ...
    def graphql(self, query: str, variables: dict[str, Any]) -> dict[str, Any]: ...


class GitHubApi:
    def __init__(self, token: str):
        if not token:
            raise ValueError("REPOOPS_TOKEN is not configured")
        self._token = token

    def _request(
        self,
        url: str,
        *,
        method: str = "GET",
        payload: dict[str, Any] | None = None,
    ) -> Any:
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
                raw = response.read().decode("utf-8")
                return json.loads(raw or "{}")
        except urllib.error.HTTPError as exc:
            body = exc.read().decode("utf-8", errors="replace")
            raise RuntimeError(f"GitHub API HTTP {exc.code}: {body[:300]}") from exc

    def rest(self, url: str) -> Any:
        return self._request(url)

    def graphql(self, query: str, variables: dict[str, Any]) -> dict[str, Any]:
        data = self._request(
            "https://api.github.com/graphql",
            method="POST",
            payload={"query": query, "variables": variables},
        )
        if not isinstance(data, dict):
            raise RuntimeError("GraphQL response invalid")
        if data.get("errors"):
            raise RuntimeError(
                "GraphQL error: " + json.dumps(data["errors"], ensure_ascii=False)[:600]
            )
        return data["data"]


def project_query(owner_type: str) -> tuple[str, str]:
    root = "user" if owner_type == "user" else "organization"
    query = f"""
    query($owner:String!, $number:Int!) {{
      {root}(login:$owner) {{
        projectV2(number:$number) {{
          id
          title
          fields(first:100) {{
            nodes {{
              ... on ProjectV2Field {{ id name dataType }}
              ... on ProjectV2SingleSelectField {{
                id name dataType options {{ id name }}
              }}
            }}
          }}
        }}
      }}
    }}
    """
    return root, query


def get_project(api: Api, cfg: dict[str, Any]) -> dict[str, Any]:
    owner = cfg["project_owner"]
    root, query = project_query(owner["type"])
    data = api.graphql(
        query,
        {"owner": owner["login"], "number": cfg["project_number"]},
    )
    project = (data.get(root) or {}).get("projectV2")
    if not isinstance(project, dict):
        raise RuntimeError("configured Project V2 not found")
    return project


def list_project_items(api: Api, cfg: dict[str, Any]) -> tuple[list[dict[str, Any]], int]:
    owner = cfg["project_owner"]
    root = "user" if owner["type"] == "user" else "organization"
    query = f"""
    query($owner:String!, $number:Int!, $after:String) {{
      {root}(login:$owner) {{
        projectV2(number:$number) {{
          items(first:100, after:$after) {{
            nodes {{
              id
              content {{
                ... on Issue {{
                  id
                  number
                  repository {{ nameWithOwner }}
                }}
              }}
            }}
            pageInfo {{ hasNextPage endCursor }}
          }}
        }}
      }}
    }}
    """
    out: list[dict[str, Any]] = []
    after: str | None = None
    pages = 0
    while True:
        data = api.graphql(
            query,
            {
                "owner": owner["login"],
                "number": cfg["project_number"],
                "after": after,
            },
        )
        project = (data.get(root) or {}).get("projectV2")
        if not isinstance(project, dict):
            raise RuntimeError("configured Project V2 not found")
        conn = project["items"]
        out.extend(node for node in conn.get("nodes", []) if isinstance(node, dict))
        pages += 1
        page = conn["pageInfo"]
        if not page.get("hasNextPage"):
            break
        after = page.get("endCursor")
        if not after:
            raise RuntimeError("pagination missing endCursor")
    return out, pages


def list_issues(api: Api, repo: str) -> list[dict[str, Any]]:
    owner, name = repo.split("/", 1)
    page = 1
    issues: list[dict[str, Any]] = []
    while True:
        url = (
            f"https://api.github.com/repos/{urllib.parse.quote(owner)}/"
            f"{urllib.parse.quote(name)}/issues?state=all&per_page=100&page={page}"
        )
        batch = api.rest(url)
        if not isinstance(batch, list):
            raise RuntimeError(f"Issues response invalid for {repo}")
        for issue in batch:
            if isinstance(issue, dict) and "pull_request" not in issue:
                issue["_repo"] = repo
                issues.append(issue)
        if len(batch) < 100:
            break
        page += 1
    return issues


def create_text_field(api: Api, project_id: str, name: str) -> dict[str, Any]:
    query = """
    mutation($project:ID!, $name:String!) {
      createProjectV2Field(input:{
        projectId:$project, name:$name, dataType:TEXT
      }) {
        projectV2Field {
          ... on ProjectV2Field { id name dataType }
        }
      }
    }
    """
    data = api.graphql(query, {"project": project_id, "name": name})
    field = data["createProjectV2Field"]["projectV2Field"]
    if not isinstance(field, dict):
        raise RuntimeError(f"failed to create text field {name}")
    return field


def add_item(api: Api, project_id: str, content_id: str) -> str:
    query = """
    mutation($project:ID!, $content:ID!) {
      addProjectV2ItemById(input:{projectId:$project, contentId:$content}) {
        item { id }
      }
    }
    """
    data = api.graphql(query, {"project": project_id, "content": content_id})
    return str(data["addProjectV2ItemById"]["item"]["id"])


def set_text(api: Api, project_id: str, item_id: str, field_id: str, value: str) -> None:
    query = """
    mutation($project:ID!, $item:ID!, $field:ID!, $value:String!) {
      updateProjectV2ItemFieldValue(input:{
        projectId:$project, itemId:$item, fieldId:$field,
        value:{text:$value}
      }) { projectV2Item { id } }
    }
    """
    api.graphql(
        query,
        {"project": project_id, "item": item_id, "field": field_id, "value": value},
    )


def set_single(
    api: Api, project_id: str, item_id: str, field_id: str, option_id: str
) -> None:
    query = """
    mutation($project:ID!, $item:ID!, $field:ID!, $option:String!) {
      updateProjectV2ItemFieldValue(input:{
        projectId:$project, itemId:$item, fieldId:$field,
        value:{singleSelectOptionId:$option}
      }) { projectV2Item { id } }
    }
    """
    api.graphql(
        query,
        {"project": project_id, "item": item_id, "field": field_id, "option": option_id},
    )


def set_date(api: Api, project_id: str, item_id: str, field_id: str, value: str) -> None:
    query = """
    mutation($project:ID!, $item:ID!, $field:ID!, $value:Date!) {
      updateProjectV2ItemFieldValue(input:{
        projectId:$project, itemId:$item, fieldId:$field,
        value:{date:$value}
      }) { projectV2Item { id } }
    }
    """
    api.graphql(
        query,
        {"project": project_id, "item": item_id, "field": field_id, "value": value},
    )


@dataclass
class SyncStats:
    issues: int = 0
    added: int = 0
    updates: int = 0
    without_metadata: int = 0


class RepoOpsSync:
    def __init__(self, api: Api, cfg: dict[str, Any]):
        self.api = api
        self.cfg = cfg

    def run(self) -> SyncStats:
        project = get_project(self.api, self.cfg)
        project_id = str(project["id"])
        fields = {
            node["name"]: node
            for node in project.get("fields", {}).get("nodes", [])
            if isinstance(node, dict) and node.get("name")
        }

        configured = self.cfg["fields"]
        for _, field_cfg in configured.items():
            if not isinstance(field_cfg, dict):
                continue
            name = str(field_cfg.get("name", "")).strip()
            if not name:
                continue
            if name not in fields:
                if field_cfg.get("auto_create_text"):
                    fields[name] = create_text_field(self.api, project_id, name)
                    print(f"FIELD_CREATED name={name}")
                else:
                    raise RuntimeError(f"Project field missing: {name}")

        items, pages = list_project_items(self.api, self.cfg)
        print(f"PROJECT_ITEMS pages={pages} total={len(items)}")

        existing: dict[tuple[str, int], str] = {}
        for node in items:
            content = node.get("content")
            if not isinstance(content, dict):
                continue
            repo = content.get("repository")
            if not isinstance(repo, dict):
                continue
            existing[
                (str(repo["nameWithOwner"]), int(content["number"]))
            ] = str(node["id"])

        stats = SyncStats()
        marker = str(self.cfg.get("metadata_marker", "REPOOPS"))

        for repo in self.cfg["repositories"]:
            for issue in list_issues(self.api, repo):
                stats.issues += 1
                meta = parse_metadata(issue.get("body"), marker)
                if not meta:
                    stats.without_metadata += 1

                key = (repo, int(issue["number"]))
                item_id = existing.get(key)
                if not item_id:
                    node_id = issue.get("node_id")
                    if not isinstance(node_id, str) or not node_id:
                        raise RuntimeError(f"Issue node_id missing: {repo}#{issue['number']}")
                    item_id = add_item(self.api, project_id, node_id)
                    existing[key] = item_id
                    stats.added += 1

                stats.updates += self._apply_fields(
                    project_id, item_id, fields, issue, repo, meta
                )

        print(
            "RESULT "
            f"issues={stats.issues} added={stats.added} "
            f"field_updates={stats.updates} "
            f"without_metadata={stats.without_metadata}"
        )
        return stats

    def _field(self, logical: str) -> dict[str, Any] | None:
        value = self.cfg["fields"].get(logical)
        return value if isinstance(value, dict) else None

    def _apply_fields(
        self,
        project_id: str,
        item_id: str,
        fields: dict[str, dict[str, Any]],
        issue: dict[str, Any],
        repo: str,
        meta: dict[str, str],
    ) -> int:
        updates = 0

        repo_cfg = self._field("repository")
        if repo_cfg:
            field = fields[str(repo_cfg["name"])]
            set_text(self.api, project_id, item_id, str(field["id"]), repo)
            updates += 1

        operator_cfg = self._field("operator")
        if operator_cfg:
            field = fields[str(operator_cfg["name"])]
            operator = normalize_operator(meta, issue, self.cfg)
            set_text(self.api, project_id, item_id, str(field["id"]), operator)
            updates += 1

        status_cfg = self._field("status")
        assert status_cfg is not None
        status_field = fields[str(status_cfg["name"])]
        options = {
            str(opt["name"]).casefold(): str(opt["id"])
            for opt in status_field.get("options", [])
            if isinstance(opt, dict)
        }
        if issue.get("state") == "closed":
            status_name = str(status_cfg.get("closed", "Done"))
        else:
            key = str(status_cfg.get("metadata_key", "status"))
            status_name = meta.get(key) or str(status_cfg.get("default_open", "Todo"))
        option_id = options.get(status_name.casefold())
        if option_id:
            set_single(self.api, project_id, item_id, str(status_field["id"]), option_id)
            updates += 1
        else:
            print(
                f"WARN {repo}#{issue['number']}: "
                f"status option not found: {status_name}"
            )

        project_cfg = self._field("project")
        if project_cfg:
            key = str(project_cfg.get("metadata_key", "project"))
            value = meta.get(key, "").strip()
            if value:
                field = fields[str(project_cfg["name"])]
                options = {
                    str(opt["name"]).casefold(): str(opt["id"])
                    for opt in field.get("options", [])
                    if isinstance(opt, dict)
                }
                option_id = options.get(value.casefold())
                if option_id:
                    set_single(self.api, project_id, item_id, str(field["id"]), option_id)
                    updates += 1
                else:
                    print(
                        f"WARN {repo}#{issue['number']}: "
                        f"project option not found: {value}"
                    )

        for logical in ("start_date", "target_date"):
            field_cfg = self._field(logical)
            if not field_cfg:
                continue
            key = str(field_cfg.get("metadata_key", logical))
            value = meta.get(key, "").strip()
            if not value:
                continue
            if not DATE_RE.fullmatch(value):
                print(f"WARN {repo}#{issue['number']}: invalid {key}: {value}")
                continue
            field = fields[str(field_cfg["name"])]
            set_date(self.api, project_id, item_id, str(field["id"]), value)
            updates += 1

        print(
            f"SYNC {repo}#{issue['number']} "
            f"state={issue.get('state', 'unknown')} metadata={'yes' if meta else 'no'}"
        )
        return updates


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--config", required=True)
    args = parser.parse_args()

    try:
        cfg = load_config(args.config)
        api = GitHubApi(os.environ.get("REPOOPS_TOKEN", ""))
        RepoOpsSync(api, cfg).run()
    except (ValueError, OSError, json.JSONDecodeError, RuntimeError) as exc:
        fail(str(exc))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
