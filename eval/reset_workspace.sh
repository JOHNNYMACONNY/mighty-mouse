#!/bin/bash
# Mighty Mouse: Workspace Reset Utility (Hardened for autonomous loop)

# 1. Revert tracked changes (Protects established infrastructure)
git checkout src/ tasks/ eval/ .gsd/ configs/ requirements.txt

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

echo "[*] Workspace reset: Infrastructure preserved, transient implementations purged."
