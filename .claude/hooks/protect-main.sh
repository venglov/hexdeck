#!/bin/sh
# PreToolUse hook: refuse git commits/pushes on or to main. Work happens on
# dev and reaches main only through a pull request.
input=$(cat)
command=$(printf '%s' "$input" | python3 -c 'import json,sys; print(json.load(sys.stdin).get("tool_input",{}).get("command",""))')

case "$command" in
  *"git "*commit*|*"git "*push*|*"git "*merge*) ;;
  *) exit 0 ;;
esac

cd "${CLAUDE_PROJECT_DIR:-.}" || exit 0
branch=$(git rev-parse --abbrev-ref HEAD 2>/dev/null)

if printf '%s' "$command" | grep -Eq 'git[[:space:]]+push([[:space:]][^|;&]*)?[[:space:]:](refs/heads/)?main([[:space:]]|$)'; then
  echo "Pushing to main is not allowed. Push to dev and open a PR into main." >&2
  exit 2
fi
if [ "$branch" = "main" ]; then
  echo "On main: committing, pushing or merging here is not allowed. Run 'git checkout dev' first; changes reach main only through a PR from dev." >&2
  exit 2
fi
exit 0
