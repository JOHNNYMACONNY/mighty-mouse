#!/bin/bash
# Mighty Mouse: Workspace Reset Utility (Hardened for autonomous loop)

# 1. Revert tracked changes (Protects established infrastructure)
git checkout .gsd/ requirements.txt

# 2. Clean untracked files (Removes transient agent outputs)
# We exclude the infrastructure directories to avoid destructive side effects during rapid iteration.
git clean -fd \
    -e src/ \
    -e tasks/ \
    -e eval/ \
	-e logs/ \
	-e .gsd/ \
	-e .planning/ \
	-e configs/ \
	-e requirements.txt

# 3. Hygiene Guard: Detect and purge "Ghost Files" (Adversarial artifacts)
# We ensure no untracked .py files exist in the root, and we purge AppleDouble junk.
find . -maxdepth 1 -name "*.py" -not -path "./legacy_registry.py" -not -path "./helpers.py" -not -path "./val_sys.py" -delete
find . -name "._*" -delete

# 4. Integrity Check
DIRTY_FILES=$(git ls-files --others --exclude-standard | grep -vE "^(logs/|eval/results/)")
if [ ! -z "$DIRTY_FILES" ]; then
    echo "[!] WARNING: Dirty workspace detected after reset:"
    echo "$DIRTY_FILES"
    # We do NOT exit 1 here yet, but we log it for the agent to see.
fi

echo "[*] Workspace reset: Infrastructure preserved, transient implementations purged."
