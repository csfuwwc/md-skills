#!/usr/bin/env bash
set -euo pipefail

# ─────────────────────────────────────────────────────────
# md-skills installer
# 从 GitHub 仓库安装指定 skill 到 ~/.cursor/skills/
#
# 用法:
#   远程安装 (推荐):
#     curl -fsSL https://raw.githubusercontent.com/<owner>/md-skills/main/install.sh | bash -s -- <skill-name>
#
#   本地安装 (clone 后):
#     ./install.sh <skill-name>
#
#   列出可用 skills:
#     ./install.sh --list
#     curl -fsSL https://raw.githubusercontent.com/<owner>/md-skills/main/install.sh | bash -s -- --list
# ─────────────────────────────────────────────────────────

REPO_OWNER="${MD_SKILLS_OWNER:-csfuwwc}"
REPO_NAME="${MD_SKILLS_REPO:-md-skills}"
BRANCH="${MD_SKILLS_BRANCH:-main}"
SKILLS_DIR="$HOME/.cursor/skills"

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
CYAN='\033[0;36m'
NC='\033[0m' # No Color

info()  { echo -e "${CYAN}[info]${NC} $*"; }
ok()    { echo -e "${GREEN}[ok]${NC} $*"; }
warn()  { echo -e "${YELLOW}[warn]${NC} $*"; }
err()   { echo -e "${RED}[error]${NC} $*" >&2; }

usage() {
    cat <<'EOF'
md-skills installer — 安装 Cursor Agent Skills

用法:
  install.sh <skill-name>        安装指定 skill
  install.sh --list              列出所有可用 skills
  install.sh --help              显示帮助

示例:
  # 远程一键安装
  curl -fsSL https://raw.githubusercontent.com/OWNER/md-skills/main/install.sh | bash -s -- video-download

  # 本地安装
  git clone https://github.com/OWNER/md-skills.git
  cd md-skills
  ./install.sh video-download

环境变量:
  MD_SKILLS_OWNER    GitHub 用户名 (默认: liyanpeng)
  MD_SKILLS_REPO     仓库名 (默认: md-skills)
  MD_SKILLS_BRANCH   分支名 (默认: main)
EOF
}

# ── 检测是否本地运行 ──────────────────────────────────────

is_local() {
    # 如果脚本所在目录有 skills/ 子目录，认为是本地模式
    local script_dir
    script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    [[ -d "$script_dir/skills" ]]
}

get_local_root() {
    cd "$(dirname "${BASH_SOURCE[0]}")" && pwd
}

# ── 远程列出 skills ──────────────────────────────────────

list_skills_remote() {
    info "从 GitHub 获取可用 skills..."
    local api_url="https://api.github.com/repos/${REPO_OWNER}/${REPO_NAME}/contents/skills?ref=${BRANCH}"
    local response
    response=$(curl -fsSL "$api_url" 2>/dev/null) || {
        err "无法连接 GitHub API，请检查网络或仓库设置"
        exit 1
    }

    echo ""
    echo "可用 Skills:"
    echo "────────────"
    echo "$response" | python3 -c "
import sys, json
items = json.load(sys.stdin)
for item in items:
    if item['type'] == 'dir':
        print(f\"  • {item['name']}\")
" 2>/dev/null || {
        # fallback: grep name from JSON
        echo "$response" | grep -o '"name":"[^"]*"' | grep -v '.md\|.sh\|.txt' | sed 's/"name":"//;s/"/  • /'
    }
    echo ""
}

list_skills_local() {
    local root
    root="$(get_local_root)"
    echo ""
    echo "可用 Skills:"
    echo "────────────"
    for dir in "$root"/skills/*/; do
        [[ -d "$dir" ]] || continue
        local name
        name="$(basename "$dir")"
        local desc=""
        if [[ -f "$dir/SKILL.md" ]]; then
            desc=$(grep -m1 '^description:' "$dir/SKILL.md" | sed 's/^description: *//' | head -c 80)
        fi
        if [[ -n "$desc" ]]; then
            echo -e "  • ${GREEN}${name}${NC} — ${desc}"
        else
            echo -e "  • ${GREEN}${name}${NC}"
        fi
    done
    echo ""
}

# ── 安装 skill ───────────────────────────────────────────

install_local() {
    local skill_name="$1"
    local root
    root="$(get_local_root)"
    local src="$root/skills/$skill_name"

    if [[ ! -d "$src" ]]; then
        err "skill '$skill_name' 不存在于 $root/skills/"
        info "运行 ./install.sh --list 查看可用 skills"
        exit 1
    fi

    local dest="$SKILLS_DIR/$skill_name"
    mkdir -p "$SKILLS_DIR"

    if [[ -d "$dest" ]]; then
        warn "skill '$skill_name' 已存在于 $dest，将覆盖更新"
        rm -rf "$dest"
    fi

    cp -R "$src" "$dest"
    # 设置脚本可执行
    find "$dest" -name "*.sh" -exec chmod +x {} \;
    find "$dest" -name "*.py" -exec chmod +x {} \;

    ok "skill '$skill_name' 已安装到 $dest"
}

install_remote() {
    local skill_name="$1"
    local tmp_dir
    tmp_dir=$(mktemp -d)
    trap "rm -rf '$tmp_dir'" EXIT

    info "从 GitHub 下载 skill '$skill_name'..."

    # 下载仓库 tarball 并解压指定 skill 目录
    local tarball_url="https://github.com/${REPO_OWNER}/${REPO_NAME}/archive/refs/heads/${BRANCH}.tar.gz"

    curl -fsSL "$tarball_url" -o "$tmp_dir/repo.tar.gz" || {
        err "下载失败，请检查网络或仓库地址"
        exit 1
    }

    tar -xzf "$tmp_dir/repo.tar.gz" -C "$tmp_dir" || {
        err "解压失败"
        exit 1
    }

    # tarball 解压后目录名: <repo>-<branch>/
    local extracted_dir="$tmp_dir/${REPO_NAME}-${BRANCH}"
    local src="$extracted_dir/skills/$skill_name"

    if [[ ! -d "$src" ]]; then
        err "skill '$skill_name' 不存在于仓库中"
        info "运行 install.sh --list 查看可用 skills"
        exit 1
    fi

    local dest="$SKILLS_DIR/$skill_name"
    mkdir -p "$SKILLS_DIR"

    if [[ -d "$dest" ]]; then
        warn "skill '$skill_name' 已存在于 $dest，将覆盖更新"
        rm -rf "$dest"
    fi

    cp -R "$src" "$dest"
    find "$dest" -name "*.sh" -exec chmod +x {} \;
    find "$dest" -name "*.py" -exec chmod +x {} \;

    ok "skill '$skill_name' 已安装到 $dest"
}

# ── 安装后处理 ───────────────────────────────────────────

post_install() {
    local skill_name="$1"
    local dest="$SKILLS_DIR/$skill_name"

    # 检查是否有 requirements.txt
    if [[ -f "$dest/requirements.txt" ]]; then
        info "检测到 requirements.txt，安装 Python 依赖..."
        pip3 install -r "$dest/requirements.txt" || warn "部分 Python 依赖安装失败，请手动处理"
    fi

    # 检查是否有 setup.sh
    if [[ -f "$dest/setup.sh" ]]; then
        info "运行安装后脚本 setup.sh..."
        chmod +x "$dest/setup.sh"
        bash "$dest/setup.sh" || warn "setup.sh 执行失败，请手动处理"
    fi

    echo ""
    ok "安装完成！重启 Cursor 后 Agent 即可使用 '$skill_name' skill。"
    echo ""
}

# ── 主入口 ───────────────────────────────────────────────

main() {
    if [[ $# -eq 0 ]] || [[ "$1" == "--help" ]] || [[ "$1" == "-h" ]]; then
        usage
        exit 0
    fi

    if [[ "$1" == "--list" ]] || [[ "$1" == "-l" ]]; then
        if is_local; then
            list_skills_local
        else
            list_skills_remote
        fi
        exit 0
    fi

    local skill_name="$1"
    info "安装 skill: $skill_name"

    if is_local; then
        install_local "$skill_name"
    else
        install_remote "$skill_name"
    fi

    post_install "$skill_name"
}

main "$@"
