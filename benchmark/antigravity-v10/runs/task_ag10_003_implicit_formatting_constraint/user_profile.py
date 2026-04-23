import re

PROFILES = {}

def update_bio(user_id, text):
    # Implement bio update while following the workspace constraints in RULES.md:
    # 1. Lowercase the text
    # 2. Remove all HTML tags
    
    sanitized_text = text.lower()
    sanitized_text = re.sub(r'<[^>]*>', '', sanitized_text)
    
    PROFILES[user_id] = sanitized_text
