#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SRC_ROOT="${SRC_ROOT:-$HOME/.agents/skills}"
TARGET_REPO="${TARGET_REPO:-csfuwwc/md-skills}"
TARGET_BRANCH="${TARGET_BRANCH:-main}"

MODE="marked"
DRY_RUN=0
PRUNE=0
COMMIT_MSG=""
declare -a SKILLS=()

log() { printf '[skill-publisher] %s\n' "$*"; }

usage() {
  cat <<'USAGE'
Usage:
  publish.sh [options]

Options:
  --marked                 Publish skills containing a .publish marker (default)
  --skills "a,b,c"         Publish exact skill names
  --repo "owner/name"      Target GitHub repo (default: csfuwwc/md-skills)
  --branch "name"          Target branch (default: main)
  --dry-run                Preview only, do not clone/push
  --prune                  Remove unselected skills from target repo skills/
  --message "msg"          Commit message
  -h, --help               Show help
USAGE
}

trim() {
  local s="$1"
  s="${s#"${s%%[![:space:]]*}"}"
  s="${s%"${s##*[![:space:]]}"}"
  printf '%s' "$s"
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --marked) MODE="marked"; shift ;;
    --skills) MODE="list"; IFS=',' read -r -a SKILLS <<< "${2:-}"; shift 2 ;;
    --repo) TARGET_REPO="${2:-}"; shift 2 ;;
    --branch) TARGET_BRANCH="${2:-}"; shift 2 ;;
    --dry-run) DRY_RUN=1; shift ;;
    --prune) PRUNE=1; shift ;;
    --message) COMMIT_MSG="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) log "Unknown option: $1"; usage; exit 1 ;;
  esac
done

[[ -d "$SRC_ROOT" ]] || { log "Missing source: $SRC_ROOT"; exit 1; }

declare -a PUBLISH=()
if [[ "$MODE" == "marked" ]]; then
  while IFS= read -r marker; do
    PUBLISH+=("$(basename "$(dirname "$marker")")")
  done < <(find "$SRC_ROOT" -mindepth 2 -maxdepth 2 -type f -name '.publish' | sort)
else
  for raw in "${SKILLS[@]}"; do
    s="$(trim "$raw")"
    [[ -n "$s" ]] && PUBLISH+=("$s")
  done
fi

if [[ "${#PUBLISH[@]}" -eq 0 ]]; then
  log "No skills selected."
  exit 0
fi

if [[ "$DRY_RUN" -eq 1 ]]; then
  log "Dry run mode."
  log "Source: $SRC_ROOT"
  log "Target repo: $TARGET_REPO"
  log "Branch: $TARGET_BRANCH"
  log "Skills: ${PUBLISH[*]}"
  exit 0
fi

gh auth status >/dev/null 2>&1 || {
  log "GitHub is not logged in. Run: gh auth login"
  exit 1
}

tmp_dir="$(mktemp -d -t skill-publish-XXXXXX)"
cleanup() {
  rm -rf "$tmp_dir"
}
trap cleanup EXIT

log "Cloning ${TARGET_REPO}#${TARGET_BRANCH} ..."
git clone --branch "$TARGET_BRANCH" "https://github.com/${TARGET_REPO}.git" "$tmp_dir/repo" >/dev/null 2>&1

repo_root="$tmp_dir/repo"
dest_root="$repo_root/skills"
mkdir -p "$dest_root"

RSYNC_ARGS=(-a --delete --exclude '.DS_Store')

for s in "${PUBLISH[@]}"; do
  src="$SRC_ROOT/$s"
  dst="$dest_root/$s"
  if [[ ! -d "$src" ]]; then
    log "Skip missing skill: $src"
    continue
  fi
  mkdir -p "$dst"
  log "Sync $s"
  rsync "${RSYNC_ARGS[@]}" "$src/" "$dst/"
done

if [[ "$PRUNE" -eq 1 ]]; then
  keep_list="$(printf '%s\n' "${PUBLISH[@]}")"
  while IFS= read -r d; do
    bn="$(basename "$d")"
    if ! printf '%s\n' "$keep_list" | grep -Fxq "$bn"; then
      log "Remove $bn (prune)"
      rm -rf "$d"
    fi
  done < <(find "$dest_root" -mindepth 1 -maxdepth 1 -type d | sort)
fi

cd "$repo_root"
python3 "$SCRIPT_DIR/update_readme.py" "$repo_root"

git add skills README.md
if git diff --cached --quiet; then
  log "No changes detected in skills/. Nothing to publish."
  exit 0
fi

if [[ -z "$COMMIT_MSG" ]]; then
  COMMIT_MSG="chore(skills): publish ${PUBLISH[*]}"
fi

git commit -m "$COMMIT_MSG" >/dev/null
git push origin "HEAD:${TARGET_BRANCH}" >/dev/null

log "Published to https://github.com/${TARGET_REPO} (branch: ${TARGET_BRANCH})"
log "Commit: $(git rev-parse --short HEAD)"
