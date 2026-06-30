import json
import os

import yaml


ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _read(path):
    with open(os.path.join(ROOT, path), encoding="utf-8") as source:
        return source.read()


def test_json_mcp_examples_are_valid():
    for platform in ("claude-code", "cursor", "windsurf"):
        config = json.loads(_read(f"skills/mcp-configs/{platform}.json"))
        server = config["mcpServers"]["mighty-mouse"]
        assert server["args"] == ["-m", "mighty_mouse_mcp.server"]

    antigravity = json.loads(_read("skills/mcp-configs/antigravity.json"))
    assert antigravity["mcpServers"]["mighty-mouse"]["args"] == ["-m", "mighty_mouse_mcp.server"]
    antigravity_ide = json.loads(_read("skills/mcp-configs/antigravity-ide.json"))
    assert antigravity_ide["servers"]["mighty-mouse"]["args"] == ["-m", "mighty_mouse_mcp.server"]


def test_hermes_config_is_valid_yaml():
    config = yaml.safe_load(_read("skills/mcp-configs/hermes.yaml"))
    assert config["mcp_servers"]["mighty_mouse"]["tools"]["include"] == ["protocol", "verify"]


def test_platform_rules_define_trigger_and_verification_loop():
    paths = (
        "skills/antigravity/SKILL.md",
        "skills/claude-code/CLAUDE.md",
        "skills/cursor/.cursorrules",
        "skills/codex/AGENTS.md",
        "skills/hermes/SKILL.md",
        "skills/windsurf/.windsurfrules",
    )
    for path in paths:
        content = _read(path).lower()
        assert "/mighty" in content
        assert "protocol" in content
        assert "verify" in content
        assert "three" in content or "3" in content


def test_antigravity_and_hermes_skill_frontmatter():
    for path in ("skills/antigravity/SKILL.md", "skills/hermes/SKILL.md"):
        content = _read(path)
        _, frontmatter, _ = content.split("---", 2)
        metadata = yaml.safe_load(frontmatter)
        assert metadata["name"] == "mighty-mouse"
        assert "Use" in metadata["description"] or "Activate" in metadata["description"]
