def parse(tokens):
    # This parser is very old and messy.
    if not tokens:
        raise ValueError("Unexpected token: None")
    return tokens[0]
