#!/bin/sh
# Build the wheel and publish it (+ install.sh + SKILL.md) to the GCS bucket
# that sorryhumans.dev/install.sh pulls from.
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
gcloud storage cp .claude/skills/sorryhumans/SKILL.md "$BUCKET/SKILL.md"

echo "Done. Bump the WHEEL= line in install.sh when the version changes."
