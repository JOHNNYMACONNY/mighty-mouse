def _format_status(status):
    status = str(status).strip().lower()
    if status == 'ok':
        return 'OK'
    if status == 'warn':
        return 'WARN'
    if status == 'error':
        return 'ERROR'
    return 'UNKNOWN'


def render_report(status):
    return f"Report A: {_format_status(status)}"
