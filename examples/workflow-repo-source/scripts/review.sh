#!/bin/sh
# Review workflow wrapper. Requires GH_TOKEN and a PR URL.
set -e

if [ -z "$1" ]; then
  echo "usage: review.sh <pr-url>" >&2
  exit 1
fi

PR_URL="$1"
export GH_TOKEN="${GH_TOKEN:?GH_TOKEN is required}"

cd "$(dirname "$0")/.."
npm run lint
node dist/index.js --pr "$PR_URL"
