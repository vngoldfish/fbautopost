import json, sys

har_path = r"c:\Users\Admin\Desktop\project\KHILOADFB.har"
print(f"=== Deep Inspecting: {har_path} ===")

with open(har_path, 'r', encoding='utf-8', errors='ignore') as f:
    har = json.load(f)

entries = har['log']['entries']
print(f"Total network entries logged during page load: {len(entries)}\n")

for idx, entry in enumerate(entries):
    req = entry.get('request', {})
    res = entry.get('response', {})
    url = req.get('url', '')
    method = req.get('method', '')
    status = res.get('status', 0)
    
    # Extract query params or POST body
    post_data = req.get('postData', {}).get('text', '')
    friendly_name = ""
    doc_id = ""
    actor_id = ""
    
    if post_data:
        from urllib.parse import parse_qs
        try:
            parsed = parse_qs(post_data)
            if 'fb_api_req_friendly_name' in parsed:
                friendly_name = parsed['fb_api_req_friendly_name'][0]
            if 'doc_id' in parsed:
                doc_id = parsed['doc_id'][0]
            if 'av' in parsed:
                actor_id = parsed['av'][0]
            elif '__user' in parsed:
                actor_id = parsed['__user'][0]
        except:
            pass

    headers = {h['name'].lower(): h['value'] for h in req.get('headers', [])}
    
    print(f"[{idx+1:02d}] {method} {status} {url[:100]}")
    if friendly_name or doc_id or actor_id:
        print(f"     GraphQL: name={friendly_name} | doc_id={doc_id} | actor_id={actor_id}")
    if 'cookie' in headers:
        cookies = headers['cookie']
        if 'c_user=' in cookies:
            import re
            c_u = re.search(r'c_user=(\d+)', cookies)
            if c_u:
                print(f"     Cookie c_user: {c_u.group(1)}")
    print("-" * 80)
