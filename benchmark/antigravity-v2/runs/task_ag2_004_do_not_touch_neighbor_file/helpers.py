def render_prefix():
    return '[item] '


def render_label(value):
    return render_prefix() + str(value)


def render_template(value):
    return f'<span>{value}</span>'
