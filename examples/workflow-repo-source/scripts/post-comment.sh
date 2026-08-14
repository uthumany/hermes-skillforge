#!/bin/sh
# Posts a review summary comment to a GitHub PR.
set -e

if [ -z "$1" ] || [ -z "$2" ]; then
  echo "usage: post-comment.sh <pr-url> <comment-file>" >&2
  exit 1
fi

PR_URL="$1"
COMMENT_FILE="$2"

if [ ! -f "$COMMENT_FILE" ]; then
  echo "error: comment file missing: $COMMENT_FILE" >&2
  exit 2
fi

export GH_TOKEN="${GH_TOKEN:?GH_TOKEN is required}"
gh api "$PR_URL/comments" -f body="$(cat "$COMMENT_FILE")"
