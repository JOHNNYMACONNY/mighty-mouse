def _format_status(status):
    status = str(status).strip().lower()
    if status == 'ok':
        return 'OK'
    if status == 'warn':
        return 'WARN'
    if status == 'error':
        return 'ERROR'
    return 'UNKNOWN'


def render_summary(status):
    return f"Report B: {_format_status(status)}"
