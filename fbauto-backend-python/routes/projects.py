import time
import database

def handle_projects_route(path: str, method: str, body: dict = None, query: dict = None) -> tuple:
    # GET /api/projects
    if path == '/api/projects' and method == 'GET':
        projects = database.get_collection('projects')
        return 200, {'projects': projects, 'total': len(projects)}

    # POST or PUT /api/projects or /api/projects/<id>
    if (path == '/api/projects' or path.startswith('/api/projects/')) and method in ['POST', 'PUT']:
        payload = body or {}
        parts = [p for p in path.split('/') if p]
        url_id = parts[2] if len(parts) > 2 else ''
        
        project_id = (url_id or payload.get('id') or payload.get('projectKey') or payload.get('key') or '').strip().lower()
        project_name = (payload.get('name') or project_id).strip()
        description = payload.get('description', '')

        if not project_id:
            return 400, {'error': 'Mã project (projectKey) không được để trống'}

        projects = database.get_collection('projects')
        existing = next((p for p in projects if p.get('id') == project_id), None)

        if existing:
            existing['name'] = project_name
            existing['description'] = description
            database.save_collection('projects', projects)
            return 200, {'success': True, 'project': existing, 'message': f'Đã cập nhật project {project_id}'}
        else:
            new_project = {
                'id': project_id,
                'name': project_name,
                'description': description,
                'createdAt': int(time.time() * 1000)
            }
            database.insert_item('projects', new_project)
            return 200, {'success': True, 'project': new_project, 'message': f'Đã tạo mới project {project_id}'}

    # DELETE /api/projects/<id>
    if path.startswith('/api/projects/') and method == 'DELETE':
        parts = [p for p in path.split('/') if p]
        project_id = parts[2] if len(parts) > 2 else ''
        projects = database.get_collection('projects')
        new_projects = [p for p in projects if p.get('id') != project_id]
        if len(new_projects) < len(projects):
            database.save_collection('projects', new_projects)
            return 200, {'success': True, 'message': f'Đã xóa project {project_id}'}
        return 404, {'error': f'Không tìm thấy project {project_id}'}

    return 404, {'error': 'Endpoint project không tồn tại'}
