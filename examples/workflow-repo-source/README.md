# Code Review Agent Workflow

An agent workflow that reviews pull requests.

## Setup

1. Install dependencies: `npm install` (or use prebuilt dist).
2. Configure a GitHub token: `gh auth login`.

## Usage

Run the review workflow against a pull request URL:

```
node dist/index.js --pr <url>
```

The workflow:
1. Fetches the PR diff via the GitHub API.
2. Runs static analysis with `npm run lint` locally for sanity.
3. Posts a review comment on the PR.

## Scripts

- `scripts/review.sh` — wrapper that calls the Node entrypoint.
- `scripts/post-comment.sh` — posts the review summary back to the PR.

## Secrets

- `GH_TOKEN` — GitHub personal access token with `repo` scope. Never commit.
