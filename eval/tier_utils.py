import json
import os
from typing import Dict, Any, Optional

DEFAULT_CONFIG_PATH = "eval/evaluation_config.json"
DEFAULT_STATE_PATH = "logs/perpetual_state.json"
FALLBACK_TIERS = ["tier_1", "tier_overnight", "tier_3", "tier_4", "tier_5", "tier_6", "tier_7", "tier_8", "tier_9"]


def load_tier_config(config_path=DEFAULT_CONFIG_PATH):
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                return json.load(f)
        except Exception as e:
            print(f"[!] Error loading tier config {config_path}: {e}")
    return {}

def load_tier_sequence(config_path=DEFAULT_CONFIG_PATH):
    cfg = load_tier_config(config_path)
    if "tier_sequence" in cfg and isinstance(cfg["tier_sequence"], list):
        return cfg["tier_sequence"]
    if "tiers" in cfg and isinstance(cfg["tiers"], dict):
        return list(cfg["tiers"].keys())
    return FALLBACK_TIERS

def get_current_tier(state_path=DEFAULT_STATE_PATH, config_path=DEFAULT_CONFIG_PATH):
    tiers = load_tier_sequence(config_path)
    if os.path.exists(state_path):
        try:
            with open(state_path, "r") as f:
                state = json.load(f)
                ct = state.get("current_tier")
                if ct in tiers:
                    return ct
        except Exception:
            pass
    return tiers[0] if tiers else "tier_1"

def get_replay_tiers(current_tier, config_path=DEFAULT_CONFIG_PATH):
    tiers = load_tier_sequence(config_path)
    if current_tier in tiers:
        idx = tiers.index(current_tier)
        return tiers[:idx + 1]
    return tiers

def parse_pass_rate(summary: Optional[Dict[str, Any]]) -> float:
    if not summary:
        return 0.0
    rate_str = summary.get("success_rate", "0/0")
    try:
        passed, total = map(int, rate_str.split('/'))
        return (passed / total) if total > 0 else 0.0
    except Exception:
        return 0.0
