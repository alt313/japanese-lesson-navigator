"""Maintain native Notion lesson navigation without changing lesson content."""
import os, re, time, requests

API = "https://api.notion.com/v1"
TOKEN = os.environ["NOTION_TOKEN"]
HEAD = {"Authorization": f"Bearer {TOKEN}", "Notion-Version": "2022-06-28", "Content-Type": "application/json"}
MONTH = "41c88625-f86b-8172-a652-ef82fcc57758"
PREFIX = "41c88625-f86b"
NAV_MARK = "☰ 전체 목차"
session = requests.Session()

def api(method, path, **kw):
    for attempt in range(5):
        r = session.request(method, API + path, headers=HEAD, timeout=40, **kw)
        if r.status_code in (429, 500, 502, 503, 504) and attempt < 4:
            time.sleep(3 * (attempt + 1))
            continue
        r.raise_for_status()
        return r.json()

def children(pid):
    all_blocks, cursor = [], None
    while True:
        params = {"page_size": 100}
        if cursor: params["start_cursor"] = cursor
        data = api("GET", f"/blocks/{pid}/children", params=params)
        all_blocks += data["results"]
        if not data.get("has_more"): return all_blocks
        cursor = data["next_cursor"]

def plain(rt):
    return "".join(t.get("plain_text", t.get("text", {}).get("content", "")) for t in rt)

def link(label, pid):
    return {"type": "text", "text": {"content": label, "link": {"url": "https://www.notion.so/" + pid.replace("-", "")}}}

def text(label):
    return {"type": "text", "text": {"content": label}}

def navigation(prev_id, next_id):
    bits = [link("← 이전", prev_id) if prev_id else text("← 처음"),
            text("　·　"), link(NAV_MARK, MONTH), text("　·　"),
            link("다음 →", next_id) if next_id else text("마지막 →")]
    return bits

def is_navigation(block):
    typ = block.get("type")
    if typ != "paragraph": return False
    value = plain(block["paragraph"].get("rich_text", []))
    return NAV_MARK in value and ("이전" in value or "처음" in value)

def main():
    # Pages live under the month page; do not touch other language archives.
    entries = []
    for block in children(MONTH):
        if block.get("type") != "child_page": continue
        title = block["child_page"].get("title", "")
        match = re.search(r"\bDay\s*(\d+)\b", title, re.I)
        if match:
            day_blocks = children(block["id"])
            substantive = [b for b in day_blocks if b.get("type") not in ("child_page", "child_database") and not is_navigation(b)]
            if substantive:
                entries.append((int(match.group(1)), block["id"]))
    entries.sort()
    print("Found:", [(d, p) for d, p in entries])
    if not entries: raise RuntimeError("No day pages found; refusing to edit")
    for index, (day, pid) in enumerate(entries):
        prev_id = entries[index-1][1] if index else None
        next_id = entries[index+1][1] if index+1 < len(entries) else None
        blocks = children(pid)
        existing = [b for b in blocks if is_navigation(b)]
        rt = navigation(prev_id, next_id)
        if existing:
            block = existing[-1]
            current = block["paragraph"].get("rich_text", [])
            if plain(current) == plain(rt) and [x.get("href") for x in current] == [x.get("text",{}).get("link",{}).get("url") for x in rt]:
                print(day, "unchanged"); continue
            api("PATCH", f"/blocks/{block['id']}", json={"paragraph": {"rich_text": rt}})
            print(day, "updated")
        else:
            # Older pages may have a previous navigation paragraph, remove only when clearly marked.
            api("PATCH", f"/blocks/{pid}/children", json={"children": [{"object": "block", "type": "paragraph", "paragraph": {"rich_text": rt}}]})
            print(day, "added")

if __name__ == "__main__": main()
