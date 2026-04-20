#!/bin/bash
# Reset workspace to clean state for next task
git checkout .
git clean -fd \
    --exclude=eval/results/ \
    --exclude=configs/prompt_segments/ \
    --exclude=configs/mighty_mouse_v1.yaml \
    --exclude=src/orchestrator/ \
    --exclude=eval/test_orchestrator_rejection.py \
    --exclude=.gsd/ \
    --exclude=*.tsv \
    --exclude=*.log \
    --exclude=.gitignore \
    --exclude=tasks/
