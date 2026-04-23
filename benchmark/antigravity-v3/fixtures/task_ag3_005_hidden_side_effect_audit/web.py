from utils import format_price

def render_web(price):
    # This renders the price in the web UI.
    # Be careful not to break the layout!
    return "<span>" + format_price(price) + "</span>"
