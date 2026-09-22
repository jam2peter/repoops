import pathlib
import sys
import unittest

ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "scripts"))

from repo_admin import parse_command, provision


class FakeRest:
    def __init__(self, responses):
        self.responses = list(responses)
        self.calls = []

    def request(self, url, method="GET", payload=None):
        self.calls.append((url, method, payload))
        return self.responses.pop(0)


CFG = {
    "owner": "example-owner",
    "owner_type": "user",
    "allowed_author_associations": ["OWNER"],
    "default_description": "Managed by RepoOps",
    "auto_init": True,
    "has_issues": True,
    "has_projects": True,
    "has_wiki": False,
    "delete_branch_on_merge": True,
}


class RepositoryAdminTests(unittest.TestCase):
    def test_parse_command(self):
        cmd = parse_command("/repoops repo create demo-tool public")
        self.assertEqual(cmd.name, "demo-tool")
        self.assertEqual(cmd.visibility, "public")

    def test_invalid_command_rejected(self):
        with self.assertRaises(ValueError):
            parse_command("/repoops repo delete demo-tool")

    def test_author_association_denied_without_api_call(self):
        api = FakeRest([])
        result = provision(
            CFG,
            "CONTRIBUTOR",
            parse_command("/repoops repo create demo public"),
            api,
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "author_association_denied")
        self.assertEqual(api.calls, [])

    def test_create_public_repository(self):
        api = FakeRest([
            (404, {"message": "Not Found"}),
            (
                201,
                {
                    "full_name": "example-owner/demo",
                    "private": False,
                    "html_url": "https://github.com/example-owner/demo",
                },
            ),
        ])
        result = provision(
            CFG,
            "OWNER",
            parse_command("/repoops repo create demo public"),
            api,
        )
        self.assertTrue(result["ok"])
        self.assertTrue(result["created"])
        self.assertFalse(api.calls[1][2]["private"])

    def test_existing_repository_is_idempotent(self):
        api = FakeRest([
            (
                200,
                {
                    "full_name": "example-owner/demo",
                    "private": False,
                    "html_url": "https://github.com/example-owner/demo",
                },
            )
        ])
        result = provision(
            CFG,
            "OWNER",
            parse_command("/repoops repo create demo public"),
            api,
        )
        self.assertTrue(result["ok"])
        self.assertFalse(result["created"])
        self.assertEqual(len(api.calls), 1)

    def test_visibility_mismatch_refuses_mutation(self):
        api = FakeRest([
            (
                200,
                {
                    "full_name": "example-owner/demo",
                    "private": True,
                    "html_url": "https://github.com/example-owner/demo",
                },
            )
        ])
        result = provision(
            CFG,
            "OWNER",
            parse_command("/repoops repo create demo public"),
            api,
        )
        self.assertFalse(result["ok"])
        self.assertEqual(result["error"], "visibility_mismatch_refusing_mutation")


if __name__ == "__main__":
    unittest.main()
