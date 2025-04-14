from datetime import datetime

def timestamp_to_datetime(timestamp):
    """Convert a Unix timestamp to a formatted datetime string."""
    if not timestamp:
        return ""
    return datetime.utcfromtimestamp(timestamp).strftime('%Y-%m-%d %H:%M:%S UTC')

def format_number(number):
    """Format large numbers with commas as thousand separators."""
    return "{:,}".format(number)

def register_filters(app):
    app.template_filter('timestamp_to_datetime')(timestamp_to_datetime)
    app.template_filter('format_number')(format_number)
