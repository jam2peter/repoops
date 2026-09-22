# Configuration

Copy `repoops.example.json` to `repoops.json`.

## Repository Admin

```json
{
  "repository_admin": {
    "owner": "example-owner",
    "owner_type": "user",
    "allowed_author_associations": ["OWNER"]
  }
}
```

`owner_type` is `user` or `organization`.

Repository creation is triggered by:

```text
/repoops repo create <name> <public|private>
```

Organization repository creation is still subject to the configured token's
permissions and the organization's own repository-creation policy.

## Project owner

```json
{
  "project_owner": {
    "type": "user",
    "login": "example-owner"
  },
  "project_number": 1
}
```

Project owner type may be `user` or `organization`.

## Managed repositories

Every Issue from every configured repository is reconciled.

```json
{
  "repositories": [
    "example-owner/repository-a",
    "example-owner/repository-b"
  ]
}
```

## Metadata

Default marker:

```html
<!-- REPOOPS
project=Platform
status=In Progress
operator=Automation
start_date=2026-09-22
target_date=2026-09-30
-->
```

Metadata is optional. Missing metadata never excludes an Issue.

## Fields

The status field is required in v0.1. Other field mappings are optional if you
remove them from the configuration.

Repository and Operator helper fields can be created automatically when:

```json
"auto_create_text": true
```

Single-select options are not created automatically. Their configured values
must already exist in the Project.

Date values must use `YYYY-MM-DD`.

## Workflow installation

Run:

```bash
python3 scripts/install.py --target /path/to/control-repository
```

The installer refuses to overwrite existing files unless `--force` is given.

After installation:

1. review/edit `repoops.json`;
2. store the token as GitHub Secret `REPOOPS_TOKEN`;
3. optionally set GitHub variable `REPOOPS_CONFIG` if the config path differs;
4. commit the control repository changes;
5. run the Project Sync workflow manually once and inspect its logs.

## Schedule

The template reconciles twice per hour. Edit the cron in your control repository
if your environment needs a different cadence.
