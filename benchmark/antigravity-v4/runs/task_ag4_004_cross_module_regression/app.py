from db import get_user_data

def display_user(user_id):
    data = get_user_data(user_id)
    print(f"User: {data['user_name']}")
