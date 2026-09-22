import json, re, urllib.parse

har_path = r"c:\Users\Admin\Desktop\project\seedingerrr.har"
print(f"=== Deep Inspecting: {har_path} ===")

with open(har_path, 'r', encoding='utf-8', errors='ignore') as f:
    har = json.load(f)

entries = har['log']['entries']
print(f"Total network entries logged in seedingerrr.har: {len(entries)}\n")

for idx, entry in enumerate(entries):
    req = entry.get('request', {})
    res = entry.get('response', {})
    url = req.get('url', '')
    method = req.get('method', '')
    status = res.get('status', 0)
    
    post_data = req.get('postData', {}).get('text', '')
    resp_text = res.get('content', {}).get('text', '')
    
    friendly_name = ""
    doc_id = ""
    actor_id = ""
    variables = ""
    
    if post_data:
        try:
            parsed = urllib.parse.parse_qs(post_data)
            if 'fb_api_req_friendly_name' in parsed: friendly_name = parsed['fb_api_req_friendly_name'][0]
            if 'doc_id' in parsed: doc_id = parsed['doc_id'][0]
            if 'av' in parsed: actor_id = parsed['av'][0]
            elif '__user' in parsed: actor_id = parsed['__user'][0]
            if 'variables' in parsed: variables = parsed['variables'][0]
        except:
            pass

    clean_resp = ""
    if resp_text:
        clean_resp = resp_text.replace("for (;;);", "").strip()[:500]
        
    print(f"[{idx+1:02d}] {method} {status} {url}")
    if friendly_name or doc_id or actor_id:
        print(f"     GraphQL: name={friendly_name} | doc_id={doc_id} | actor_id={actor_id}")
        if variables:
            print(f"     Variables: {variables[:200]}")
    if clean_resp:
        print(f"     Response: {clean_resp}")
    print("-" * 80)
