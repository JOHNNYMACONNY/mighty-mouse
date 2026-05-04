# transaction_manager.py
import local_db
import remote_api

def save_transaction(data):
    tx_id = data.get('id')
    # 1. Write to local database
    local_db.insert(tx_id, data)
    
    try:
        # 2. Write to remote API
        remote_api.post_data(data)
    except Exception as e:
        # 3. Manual rollback on failure
        local_db.delete(tx_id)
        raise e
