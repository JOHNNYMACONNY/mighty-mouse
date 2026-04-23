def parse(tokens):
    # This parser is very old and messy.
    if not tokens:
        raise ValueError("Unexpectd token: None")
    return tokens[0]
