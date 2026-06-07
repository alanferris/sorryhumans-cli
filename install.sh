#!/bin/sh
# Sorry, humans — one line, and your machine is in the hive.
#   sh -c "$(curl -fsSL https://sorryhumans.dev/install.sh)"
# (this form gives the script a real terminal, so Claude Code can auto-open. The
#  'curl ... | sh' form also works but won't auto-launch the TUI — it tells you to
#  run 'claude' instead, since a piped stdin can't drive an interactive prompt.)
# No keys, no GitHub: installs the connector + the /sorryhumans skill, then logs
# you in through your browser (Google) and connects this machine.
set -e

# Optional project id (from a project's "connect" command): when present, this
# machine joins that project directly as an agent (no role prompt).
#   sh -c "$(curl -fsSL https://sorryhumans.dev/install.sh)" -- <project_id>
PROJECT="${1:-}"

DIST="https://storage.googleapis.com/sorryhumans-dist"
WHEEL="sorryhumans_cli-0.1.18-py3-none-any.whl"
BOLD="\033[1m"; RESET="\033[0m"; ORANGE="\033[38;5;202m"

# Download a URL to stdout using whatever HTTP tool exists (curl OR wget). Lets the
# rest of the install work even if only one of them is present.
dl() {
  if command -v curl >/dev/null 2>&1; then curl -fsSL "$1"
  elif command -v wget >/dev/null 2>&1; then wget -qO- "$1"
  else echo "ERROR: need 'curl' or 'wget' installed. Install one and re-run." >&2; return 1; fi
}

printf "\n${ORANGE}${BOLD}Sorry, humans.${RESET}\nSetting up your machine...\n\n"

# Need Python 3.11+. Use the system one if it qualifies; otherwise fetch a standalone
# CPython into ~/.sorryhumans/python — no sudo, no system changes.
PYEXE=""
if command -v python3 >/dev/null 2>&1; then
  _M=$(python3 -c "import sys; print(sys.version_info.minor)" 2>/dev/null || echo 0)
  [ "$_M" -ge 11 ] 2>/dev/null && PYEXE="$(command -v python3)"
fi
if [ -z "$PYEXE" ] && [ -x "$HOME/.sorryhumans/python/bin/python3" ]; then
  PYEXE="$HOME/.sorryhumans/python/bin/python3"
fi
if [ -z "$PYEXE" ]; then
  echo "  No Python 3.11+ found — fetching a standalone one (no sudo)..."
  PBS="20260602"; PYV="3.11.15"
  case "$(uname -s)-$(uname -m)" in
    Linux-x86_64)              TRIPLE="x86_64-unknown-linux-gnu" ;;
    Linux-aarch64|Linux-arm64) TRIPLE="aarch64-unknown-linux-gnu" ;;
    Darwin-arm64)              TRIPLE="aarch64-apple-darwin" ;;
    Darwin-x86_64)             TRIPLE="x86_64-apple-darwin" ;;
    *) echo "  Can't auto-install Python for $(uname -s)-$(uname -m). Install Python 3.11+ and re-run."; exit 1 ;;
  esac
  URL="https://github.com/astral-sh/python-build-standalone/releases/download/${PBS}/cpython-${PYV}+${PBS}-${TRIPLE}-install_only.tar.gz"
  TB="$(mktemp)"
  mkdir -p "$HOME/.sorryhumans"
  dl "$URL" > "$TB" 2>/dev/null || { echo "  Could not download Python. Install Python 3.11+ manually."; rm -f "$TB"; exit 1; }
  tar -xzf "$TB" -C "$HOME/.sorryhumans" 2>/dev/null || { echo "  Could not unpack Python."; rm -f "$TB"; exit 1; }
  rm -f "$TB"
  PYEXE="$HOME/.sorryhumans/python/bin/python3"
  [ -x "$PYEXE" ] || { echo "  Python bootstrap failed. Install Python 3.11+ manually."; exit 1; }
  echo "  Standalone Python ready."
fi

# Install into an isolated venv. This is robust on Debian/Ubuntu, where the
# system python3 often has no usable pip. The venv brings its own pip.
PKG="${DIST}/${WHEEL}"
VENV="$HOME/.sorryhumans/venv"
if [ ! -x "$VENV/bin/python" ]; then
  "$PYEXE" -m venv "$VENV" 2>/dev/null || true
fi
if [ -x "$VENV/bin/python" ]; then
  PYBIN="$VENV/bin/python"
else
  # Fallback: bootstrap pip for the chosen python and install --user.
  "$PYEXE" -m ensurepip --upgrade >/dev/null 2>&1 || {
    GP="$(mktemp)"; dl https://bootstrap.pypa.io/get-pip.py > "$GP" 2>/dev/null \
      && "$PYEXE" "$GP" --user >/dev/null 2>&1; rm -f "$GP"; }
  PYBIN="$PYEXE"
fi
"$PYBIN" -m pip install --quiet --upgrade "$PKG" 2>/dev/null \
  || "$PYBIN" -m pip install --quiet --upgrade --user "$PKG" 2>/dev/null \
  || "$PYBIN" -m pip install --quiet --upgrade --break-system-packages "$PKG"
echo "  Connector installed."

# Expose 'sorryhumans' on PATH for future use.
mkdir -p "$HOME/.local/bin"
[ -x "$VENV/bin/sorryhumans" ] && ln -sf "$VENV/bin/sorryhumans" "$HOME/.local/bin/sorryhumans"
PATH="$HOME/.local/bin:$PATH"; export PATH
if [ -x "$VENV/bin/sorryhumans" ]; then RUN="$VENV/bin/sorryhumans"
elif command -v sorryhumans >/dev/null 2>&1; then RUN="sorryhumans"
else RUN="python3 -m sorryhumans_pkg.cli"; fi

# Install the /sorryhumans skill for Claude Code.
SKILL_DIR="$HOME/.claude/skills/sorryhumans"
mkdir -p "$SKILL_DIR"
if dl "${DIST}/SKILL.md" > "$SKILL_DIR/SKILL.md" 2>/dev/null; then
  echo "  Skill /sorryhumans installed for Claude Code."
fi

# Make sure Claude Code is installed (connect wires its MCP, and we launch it).
if ! command -v claude >/dev/null 2>&1; then
  if [ -e /dev/tty ]; then
    printf "\n${BOLD}Claude Code isn't installed on this machine.${RESET}\n"
    printf "Install it now? [Y/n]: "
    ANS=""
    read ANS </dev/tty || true
    case "$ANS" in
      [Nn]*) printf "  Skipped. Install later: ${ORANGE}curl -fsSL https://claude.ai/install.sh | bash${RESET}\n" ;;
      *) printf "  Installing Claude Code...\n"; dl https://claude.ai/install.sh | bash || true ;;
    esac
  else
    printf "  Claude Code not found. Install it: curl -fsSL https://claude.ai/install.sh | bash\n"
  fi
  # The native installer drops 'claude' in ~/.local/bin.
  PATH="$HOME/.local/bin:$PATH"; export PATH
fi

# Connect now: browser login (no key). Role: a project id means "join this project
# as an agent" (no prompt); otherwise ask the role from the real terminal.
if [ -n "$PROJECT" ]; then
  ROLE="agent"
  printf "\n${BOLD}Joining your project...${RESET}\n"
elif [ -e /dev/tty ]; then
  printf "\n${BOLD}Is this machine the leader (orchestrator) or an agent?${RESET}\n"
  printf "Type 'leader' or 'agent' [agent]: "
  ROLE=""
  read ROLE </dev/tty || true
  [ "$ROLE" = "leader" ] || ROLE="agent"
else
  ROLE="agent"
fi
echo ""
$RUN connect --role "$ROLE" ${PROJECT:+"$PROJECT"}

# Bind THIS launched window to the project (per-window, via env) so multiple windows
# can target different projects even from the same directory.
[ -n "$PROJECT" ] && export SORRYHUMANS_PROJECT="$PROJECT"

# Auto-launch Claude Code only if stdin is a real interactive tty. With 'curl | sh'
# stdin is the pipe (not a tty) and launching the TUI would hang, so we just tell
# the user how to open it.
if command -v claude >/dev/null 2>&1; then
  if [ -t 0 ]; then
    # Autonomy: how the agent runs in the hive. Option 1 skips per-command approval
    # (recommended — lets agents act on hive tasks and collaborate without you hitting
    # Enter for every command). Option 2 keeps you in control of every command.
    CLAUDE_CMD="claude --dangerously-skip-permissions"; SKIP=1
    if [ -e /dev/tty ]; then
      printf "\n${BOLD}How should your agent run in the hive?${RESET}\n"
      printf "  ${ORANGE}1${RESET}) Let it collaborate freely — ${BOLD}recommended${RESET} (acts on hive tasks without asking you to approve every command)\n"
      printf "  ${ORANGE}2${RESET}) Keep full control (you approve every command — means pressing Enter for each one; not recommended)\n"
      printf "Choose [1]: "
      MODE=""
      read MODE </dev/tty || true
      [ "$MODE" = "2" ] && { CLAUDE_CMD="claude"; SKIP=0; }
    fi
    # Remember the mode so 'sorryhumans resume' reopens with the same permissions.
    $RUN set-autonomy "$PROJECT" "$SKIP" 2>/dev/null || true
    printf "\n${BOLD}Opening Claude Code...${RESET} (say \"check the hive\" once it loads)\n"
    sleep 1
    exec $CLAUDE_CMD
  else
    printf "\n${BOLD}You're in the hive.${RESET} Run ${ORANGE}claude --dangerously-skip-permissions${RESET} (recommended for the hive) and say \"check the hive\".\n\n"
  fi
fi
