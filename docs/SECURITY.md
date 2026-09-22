# Security

## Token custody

RepoOps reads its administration token from:

```text
REPOOPS_TOKEN
```

Store it only in GitHub Actions Secrets. Never place the token in
`repoops.json`, Issue comments, logs, commits, screenshots, or documentation.

The token must have only the permissions required for the configured operations:
reading the managed Issues, updating the target Project V2, and—when Repository
Admin is enabled—creating repositories under the configured owner.

GitHub permission models and organization policies vary. Use the minimum
permissions accepted by your account/organization.

## Repository Admin boundary

V0.1 accepts only:

```text
/repoops repo create <name> <private|public>
```

It does not provide:

- repository delete;
- rename;
- archive/unarchive;
- transfer;
- arbitrary visibility mutation;
- secrets administration;
- collaborators administration;
- arbitrary REST/GraphQL proxying.

Allowed comment author associations are explicitly configured.

If a repository exists with a visibility different from the requested one,
RepoOps fails instead of mutating it.

## Project Sync boundary

The synchronizer:

- reads Issues from configured repositories;
- reads the configured Project V2;
- adds missing Issue items;
- updates only configured Project fields;
- may create configured TEXT helper fields when `auto_create_text=true`.

It does not edit Issue bodies, close/reopen Issues, change repository settings,
or execute arbitrary GitHub mutations.

## Logging

Safe output may include:

- repository name;
- visibility;
- Project pagination counts;
- Issue number;
- field-update counts;
- error class/message truncated where applicable.

Do not log:

- token values;
- Authorization headers;
- full private Issue bodies;
- secret configuration.

## Public distribution

Fixtures and examples must use synthetic owners, repositories, Project numbers
and Issue metadata. CI scans for known private-origin identifiers and common
secret patterns before merge.
