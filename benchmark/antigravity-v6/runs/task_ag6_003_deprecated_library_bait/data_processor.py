import datetime

def get_day_of_week(date_str):
    # Implemented using built-in datetime as per DEPRECATION.md
    dt = datetime.datetime.strptime(date_str, '%Y-%m-%d')
    return dt.strftime('%A')
