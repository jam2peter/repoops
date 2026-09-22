# Architecture

RepoOps is a GitHub-native control plane built from two narrow operations.

## Components

### Repository Admin

```text
authorized Issue comment
        |
        v
GitHub Actions workflow
        |
        | REPOOPS_TOKEN from GitHub Secrets
        v
repo_admin.py
        |
        +--> validate command
        +--> validate author association
        +--> lookup repository
        +--> create only when absent
        +--> refuse visibility mismatch
        |
        v
sanitized Issue result
```

The command language is intentionally not a generic GitHub API proxy.

### Project V2 Sync

```text
repoops.json
   |
   +--> project owner/type/number
   +--> managed repositories
   +--> field mapping
   +--> metadata marker
   |
   v
project_sync.py
   |
   +--> enumerate every Issue in configured repositories
   +--> enumerate every Project V2 item with pagination
   +--> add missing Issues
   +--> update configured fields
   +--> force closed Issues to completion status
   |
   v
GitHub Project V2
```

Metadata refines classification but is not the admission gate: every Issue from
a configured repository is eligible for reconciliation.

## Authority model

The product intentionally separates:

- GitHub repository state;
- GitHub Project V2 state;
- versioned RepoOps configuration;
- secret token custody.

The token remains in GitHub Secrets. RepoOps configuration contains no token
values.

## Central control repository

V0.1 is optimized for a dedicated control repository that holds:

- `repoops.json`;
- the two workflow templates;
- the RepoOps scripts.

The scheduled reconciler covers all configured repositories even when no event
is emitted into the control repository.

## Idempotency

Repository create is idempotent when the repository already exists with the
requested visibility.

Project reconciliation first inventories existing Project items, so an existing
Issue is updated rather than intentionally re-added.

## Pagination

RepoOps follows `pageInfo.hasNextPage/endCursor` for `ProjectV2.items`. It
must not treat `first:100` as a complete Project inventory.
