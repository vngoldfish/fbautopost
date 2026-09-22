import time
import database

def handle_projects_route(path: str, method: str, body: dict = None, query: dict = None) -> tuple:
    if path == '/api/projects' and method == 'GET':
        projects = database.get_collection('projects')
        return 200, {'projects': projects, 'total': len(projects)}

    if path == '/api/projects' and method == 'POST':
        payload = body or {}
        project_id = (payload.get('id') or payload.get('projectKey') or payload.get('key') or '').strip().lower()
        project_name = (payload.get('name') or project_id).strip()
        description = payload.get('description', '')

        if not project_id:
            return 400, {'error': 'Ma project_id khong duoc de trong'}

        projects = database.get_collection('projects')
        existing = next((p for p in projects if p.get('id') == project_id), None)

        if existing:
            existing['name'] = project_name
            existing['description'] = description
            database.save_collection('projects', projects)
            return 200, {'success': True, 'project': existing, 'message': 'Cap nhat project thanh cong'}
        else:
            new_project = {
                'id': project_id,
                'name': project_name,
                'description': description,
                'createdAt': int(time.time() * 1000)
            }
            database.insert_item('projects', new_project)
            return 200, {'success': True, 'project': new_project, 'message': 'Tao project moi thanh cong'}

    if path.startswith('/api/projects/') and method == 'DELETE':
        parts = [p for p in path.split('/') if p]
        project_id = parts[2] if len(parts) > 2 else ''
        projects = database.get_collection('projects')
        new_projects = [p for p in projects if p.get('id') != project_id]
        if len(new_projects) < len(projects):
            database.save_collection('projects', new_projects)
            return 200, {'success': True, 'message': 'Da xoa project'}
        return 404, {'error': 'Khong tim thay project'}

    return 404, {'error': 'Endpoint project khong ton tai'}
