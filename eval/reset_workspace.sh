#!/bin/bash
# Reset workspace to clean state for next task
# Preserves eval/results and logs
git checkout .
git clean -fd --exclude=eval/results/ --exclude=configs/prompt_segments/ --exclude=configs/mighty_mouse_v1.yaml
