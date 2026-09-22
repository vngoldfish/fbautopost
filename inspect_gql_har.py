import json, urllib.parse

har_path = r"c:\Users\Admin\Desktop\project\KHILOADFB.har"
with open(har_path, 'r', encoding='utf-8', errors='ignore') as f:
    har = json.load(f)

gql_queries = []
for entry in har['log']['entries']:
    url = entry.get('request', {}).get('url', '')
    if '/api/graphql' in url:
        pd = entry.get('request', {}).get('postData', {}).get('text', '')
        if pd:
            parsed = urllib.parse.parse_qs(pd)
            name = parsed.get('fb_api_req_friendly_name', [''])[0]
            doc_id = parsed.get('doc_id', [''])[0]
            actor_id = parsed.get('av', [''])[0] or parsed.get('__user', [''])[0]
            gql_queries.append({'name': name, 'doc_id': doc_id, 'actor_id': actor_id})

print(f"Found {len(gql_queries)} GraphQL queries in KHILOADFB.har:\n")
for idx, q in enumerate(gql_queries):
    print(f"{idx+1:02d}. Name: {q['name']:<50} | doc_id: {q['doc_id']:<20} | actor_id: {q['actor_id']}")
