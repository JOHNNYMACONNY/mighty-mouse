def migrate_data(old_data):
    # Migrated projects format from list to dict with roles
    new_data = old_data.copy()
    old_projects = old_data.get('projects', {})
    new_projects = {}
    
    for project_id, member_list in old_projects.items():
        # Convert list of user IDs to a dictionary with default role 'member'
        new_projects[project_id] = {user_id: {"role": "member"} for user_id in member_list}
        
    new_data['projects'] = new_projects
    return new_data
