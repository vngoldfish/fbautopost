import json, urllib.parse, sys

har_path = r"c:\Users\Admin\Desktop\project\loitestcamxuc.har"
sys.stdout.reconfigure(encoding='utf-8')
print(f"=== Deep Inspecting Manual Actions in: {har_path} ===")

with open(har_path, 'r', encoding='utf-8', errors='ignore') as f:
    har = json.load(f)

entries = har['log']['entries']
print(f"Total network entries: {len(entries)}\n")

for idx, entry in enumerate(entries):
    req = entry.get('request', {})
    res = entry.get('response', {})
    url = req.get('url', '')
    method = req.get('method', '')
    status = res.get('status', 0)
    
    post_data = req.get('postData', {}).get('text', '')
    resp_text = res.get('content', {}).get('text', '')
    
    if '/api/graphql' in url and post_data:
        parsed = urllib.parse.parse_qs(post_data)
        name = parsed.get('fb_api_req_friendly_name', [''])[0]
        doc_id = parsed.get('doc_id', [''])[0]
        actor_id = parsed.get('av', [''])[0] or parsed.get('__user', [''])[0]
        variables = parsed.get('variables', [''])[0]
        
        print(f"[{idx+1:02d}] {method} {status} FriendlyName: {name}")
        print(f"     doc_id: {doc_id} | actor_id: {actor_id}")
        if variables:
            print(f"     Variables: {variables}")
        if resp_text:
            clean = resp_text.replace("for (;;);", "").strip()[:400]
            print(f"     Response: {clean}")
        print("=" * 80)
