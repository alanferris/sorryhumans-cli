#!/bin/sh
# Build the wheel and publish it (+ install.sh + install.ps1 + SKILL.md) to the GCS
# bucket that sorryhumans.dev/install.sh (sh/Git Bash) and /install.ps1 (PowerShell) use.
set -e
cd "$(dirname "$0")/.."

BUCKET="gs://sorryhumans-dist"

echo "Building wheel..."
rm -rf dist
python3 -m build --wheel 2>/dev/null || python3 -m pip wheel --no-deps -w dist .
WHEEL=$(ls dist/*.whl | head -1)
echo "Built: $WHEEL"

echo "Publishing to $BUCKET ..."
gcloud storage cp "$WHEEL" "$BUCKET/"
gcloud storage cp install.sh "$BUCKET/install.sh"
gcloud storage cp install.ps1 "$BUCKET/install.ps1"
gcloud storage cp .claude/skills/sorryhumans/SKILL.md "$BUCKET/SKILL.md"

echo "Done. Al subir versión, bump WHEEL= en install.sh Y \$Wheel en install.ps1"
echo "(y re-deploy del frontend: hornea public/install.sh y public/install.ps1)."
