"""Crawl handler — Example with dependencies.

Register via CLI:
    tasklane register crawl examples/crawl_handler.py --deps requests,beautifulsoup4

Handler rules:
- Function named `handle`, takes `dict`, returns `dict`
- Put imports inside the function body or at module level
- Workers auto-install dependencies listed in `--deps`
"""


def handle(params: dict) -> dict:
    import requests
    resp = requests.get(params["url"])
    return {"status": resp.status_code, "length": len(resp.text)}
