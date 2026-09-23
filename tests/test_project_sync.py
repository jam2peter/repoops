import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from project_sync import (
    list_project_items,
    load_config,
    normalize_operator,
    parse_metadata,
    project_query,
)


class FakeGraphql:
    def __init__(self):
        self.calls = 0

    def graphql(self, query, variables):
        self.calls += 1
        if self.calls == 1:
            return {
                "user": {
                    "projectV2": {
                        "items": {
                            "nodes": [{"id": "ITEM1", "content": None}],
                            "pageInfo": {
                                "hasNextPage": True,
                                "endCursor": "CURSOR1",
                            },
                        }
                    }
                }
            }
        return {
            "user": {
                "projectV2": {
                    "items": {
                        "nodes": [{"id": "ITEM2", "content": None}],
                        "pageInfo": {
                            "hasNextPage": False,
                            "endCursor": None,
                        },
                    }
                }
            }
        }

    def rest(self, url):
        raise AssertionError("not used")


class ProjectSyncTests(unittest.TestCase):
    def setUp(self):
        self.cfg = load_config(str(ROOT / "repoops.example.json"))

    def test_example_config_is_valid(self):
        self.assertEqual(self.cfg["project_number"], 1)
        self.assertEqual(self.cfg["metadata_marker"], "REPOOPS")

    def test_metadata_is_optional_and_parsed_when_present(self):
        self.assertEqual(parse_metadata("plain text", "REPOOPS"), {})
        body = """text
<!-- REPOOPS
project=Platform
status=In Progress
operator=Automation
start_date=2026-09-22
-->
"""
        meta = parse_metadata(body, "REPOOPS")
        self.assertEqual(meta["project"], "Platform")
        self.assertEqual(meta["status"], "In Progress")
        self.assertEqual(meta["operator"], "Automation")
        self.assertEqual(meta["start_date"], "2026-09-22")

    def test_operator_precedence_metadata_then_label_then_default(self):
        issue = {"labels": [{"name": "operator:automation"}]}
        self.assertEqual(
            normalize_operator({"operator": "Human"}, issue, self.cfg),
            "Human",
        )
        self.assertEqual(
            normalize_operator({}, issue, self.cfg),
            "Automation",
        )
        self.assertEqual(
            normalize_operator({}, {"labels": []}, self.cfg),
            "Unassigned",
        )

    def test_project_pagination_is_complete(self):
        api = FakeGraphql()
        items, pages = list_project_items(api, self.cfg)
        self.assertEqual(pages, 2)
        self.assertEqual([item["id"] for item in items], ["ITEM1", "ITEM2"])
        self.assertEqual(api.calls, 2)

    def test_owner_query_supports_user_and_organization(self):
        root, user_query = project_query("user")
        self.assertEqual(root, "user")
        self.assertIn("user(login:$owner)", user_query)
        root, org_query = project_query("organization")
        self.assertEqual(root, "organization")
        self.assertIn("organization(login:$owner)", org_query)


if __name__ == "__main__":
    unittest.main()
