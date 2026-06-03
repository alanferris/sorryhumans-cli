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
WHEEL="sorryhumans_cli-0.1.14-py3-none-any.whl"
BOLD="\033[1m"; RESET="\033[0m"; ORANGE="\033[38;5;202m"

printf "\n${ORANGE}${BOLD}Sorry, humans.${RESET}\nSetting up your machine...\n\n"

# Python 3.11+
if ! command -v python3 >/dev/null 2>&1; then
  echo "Python 3.11+ is required. Install it from https://python.org and try again."
  exit 1
fi
PYMIN=$(python3 -c "import sys; print(sys.version_info.minor)" 2>/dev/null)
if [ "$PYMIN" -lt 11 ] 2>/dev/null; then
  echo "Python 3.11+ required (found 3.$PYMIN). Please upgrade."
  exit 1
fi

# Install into an isolated venv. This is robust on Debian/Ubuntu, where the
# system python3 often has no usable pip. The venv brings its own pip.
PKG="${DIST}/${WHEEL}"
VENV="$HOME/.sorryhumans/venv"
if [ ! -x "$VENV/bin/python" ]; then
  python3 -m venv "$VENV" 2>/dev/null || true
fi
if [ -x "$VENV/bin/python" ]; then
  PYBIN="$VENV/bin/python"
else
  # Fallback: bootstrap pip for the system python and install --user.
  python3 -m ensurepip --upgrade >/dev/null 2>&1 || {
    GP="$(mktemp)"; curl -fsSL https://bootstrap.pypa.io/get-pip.py -o "$GP" 2>/dev/null \
      && python3 "$GP" --user >/dev/null 2>&1; rm -f "$GP"; }
  PYBIN="python3"
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
if curl -fsSL "${DIST}/SKILL.md" -o "$SKILL_DIR/SKILL.md" 2>/dev/null; then
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
      *) printf "  Installing Claude Code...\n"; curl -fsSL https://claude.ai/install.sh | bash || true ;;
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

# Auto-launch Claude Code only if stdin is a real interactive tty. With 'curl | sh'
# stdin is the pipe (not a tty) and launching the TUI would hang, so we just tell
# the user how to open it.
if command -v claude >/dev/null 2>&1; then
  if [ -t 0 ]; then
    printf "\n${BOLD}Opening Claude Code...${RESET} (say \"check the hive\" once it loads)\n"
    sleep 1
    exec claude
  else
    printf "\n${BOLD}You're in the hive.${RESET} Run ${ORANGE}claude${RESET} and say \"check the hive\".\n\n"
  fi
fi
