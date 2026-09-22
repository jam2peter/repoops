# RepoOps

**RepoOps** turns GitHub Issues and GitHub Project V2 into a small operational
control plane.

It packages two capabilities:

1. **Repository Admin** — create public/private repositories from an authorized
   Issue comment without printing the administration token.
2. **Project V2 Sync** — reconcile every Issue from configured repositories into
   one GitHub Project V2, with optional metadata-driven fields.

> Status: `v0.1-beta` candidate.

## Why

A GitHub-based operation often starts simple and then accumulates manual steps:

- create a repository;
- remember its visibility;
- wire it into the team's Project;
- keep Issues synchronized;
- classify status/project/operator/dates;
- reconcile missed events.

RepoOps makes those steps explicit, versioned, idempotent where possible, and
auditable through GitHub Actions.

## Repository creation

After installing the Repository Admin workflow, an authorized user can comment:

```text
/repoops repo create my-tool public
```

or:

```text
/repoops repo create internal-tool private
```

The operation:

- validates the repository name;
- validates the comment author's association;
- checks whether the repository already exists;
- creates it only when absent;
- refuses to silently change visibility;
- records a sanitized result on the Issue.

No token value is emitted.

## Project V2 reconciliation

RepoOps reads a versioned `repoops.json` and reconciles every Issue from the
configured repositories into a Project V2.

Metadata is optional. An Issue without metadata still belongs in the Project.

Example metadata:

```html
<!-- REPOOPS
project=Platform
status=In Progress
operator=Automation
start_date=2026-09-22
target_date=2026-09-30
-->
```

Closing an Issue forces the configured completion status.

The synchronizer paginates the complete Project item connection instead of
assuming the first 100 items are the full inventory.

## Install model

RepoOps is designed to live in a small **control repository**.

1. copy `repoops.example.json` to `repoops.json`;
2. edit owner/project/repositories/fields;
3. add the required GitHub token as `REPOOPS_TOKEN`;
4. copy the workflow templates from `templates/workflows/` into
   `.github/workflows/`;
5. copy or vendor the `scripts/` directory.

See [Configuration](docs/CONFIGURATION.md).

## Security boundary

RepoOps does not expose a generic GitHub administration console.

Repository Admin v0.1 supports only:

```text
create <name> <public|private>
```

It does not implement delete, rename, archive, transfer, visibility mutation,
webhook administration, secrets administration, or arbitrary API calls.

Project Sync only reads Issues/Project state and performs the Project mutations
required by its configured field model.

See [Security](docs/SECURITY.md).

## Repository layout

```text
.
├── repoops.example.json
├── scripts/
│   ├── repo_admin.py
│   └── project_sync.py
├── templates/workflows/
│   ├── repository-admin.yml
│   └── project-sync.yml
├── tests/
├── docs/
│   ├── ARCHITECTURE.md
│   ├── CONFIGURATION.md
│   └── SECURITY.md
└── .github/workflows/ci.yml
```

## Tests

```bash
python3 -m unittest discover -s tests -p 'test_*.py' -v
python3 -m py_compile scripts/repo_admin.py scripts/project_sync.py
```

## Origin

RepoOps is a clean product extraction of GitHub operations proven in the
JamPeter environment. The public repository contains synthetic configuration
only; it does not include private Project numbers, repository inventories,
tokens, Issue bodies, or infrastructure identifiers.

## License

MIT
