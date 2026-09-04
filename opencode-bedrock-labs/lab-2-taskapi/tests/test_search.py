"""
Acceptance tests for GET /tasks/search - the feature this lab adds.

These are written against the SPEC in main.py's trailing comment, not
against any implementation - they should all fail until /tasks/search
exists and matches that spec, most importantly the cursor-stability
requirement in test_search_pagination_stable_under_concurrent_insert.
"""
import time


def _make(client, title, status="open", priority=3):
    return client.post("/tasks", json={"title": title, "status": status, "priority": priority}).json()


def test_search_by_text_query(client):
    _make(client, "Write quarterly report")
    _make(client, "Fix login bug")
    r = client.get("/tasks/search", params={"q": "report"})
    assert r.status_code == 200
    results = r.json()["results"]
    assert len(results) == 1
    assert results[0]["title"] == "Write quarterly report"


def test_search_by_status(client):
    _make(client, "A", status="open")
    _make(client, "B", status="done")
    r = client.get("/tasks/search", params={"status": "done"})
    results = r.json()["results"]
    assert len(results) == 1
    assert results[0]["title"] == "B"


def test_search_by_priority_range(client):
    _make(client, "Low", priority=1)
    _make(client, "Mid", priority=3)
    _make(client, "High", priority=5)
    r = client.get("/tasks/search", params={"min_priority": 2, "max_priority": 4})
    results = r.json()["results"]
    assert len(results) == 1
    assert results[0]["title"] == "Mid"


def test_search_pagination_returns_next_cursor(client):
    for i in range(5):
        _make(client, f"Task {i}")
        time.sleep(0.01)  # ensure distinct created_at ordering
    r = client.get("/tasks/search", params={"limit": 2})
    body = r.json()
    assert len(body["results"]) == 2
    assert body["next_cursor"] is not None

    r2 = client.get("/tasks/search", params={"limit": 2, "cursor": body["next_cursor"]})
    body2 = r2.json()
    assert len(body2["results"]) == 2
    # no overlap between page 1 and page 2
    ids_page1 = {t["id"] for t in body["results"]}
    ids_page2 = {t["id"] for t in body2["results"]}
    assert ids_page1.isdisjoint(ids_page2)


def test_search_pagination_stable_under_concurrent_insert(client):
    """
    The real acceptance test: results are sorted newest-first (created_at
    DESC). Fetch page 1, then simulate a concurrent write (a new task
    created between page requests - the most common real-world case,
    e.g. another user submitting a task while this one is paging through
    results), then fetch page 2 via the cursor. Page 2 must be exactly the
    next 2 tasks from the ORIGINAL ordering - not shifted, not duplicated,
    not skipped - because it's anchored to a specific row, not a numeric
    offset. This is the test a naive `OFFSET`-based implementation fails.
    """
    original = []
    for i in range(5):
        original.append(_make(client, f"Original {i}"))
        time.sleep(0.01)
    # original[4] is newest (created last), original[0] is oldest

    page1 = client.get("/tasks/search", params={"limit": 2}).json()
    page1_ids = [t["id"] for t in page1["results"]]
    assert page1_ids == [original[4]["id"], original[3]["id"]], (
        "page 1 (newest-first, limit 2) should be the 2 newest original tasks"
    )

    # Simulate a concurrent write: a brand new task lands while the caller
    # is still paging.
    time.sleep(0.01)
    _make(client, "Inserted mid-pagination")

    page2 = client.get("/tasks/search", params={"limit": 2, "cursor": page1["next_cursor"]}).json()
    page2_ids = [t["id"] for t in page2["results"]]
    assert page2_ids == [original[2]["id"], original[1]["id"]], (
        "page 2 must continue from where page 1 left off in the ORIGINAL order "
        f"({[original[2]['id'], original[1]['id']]}), not be shifted by the "
        f"task inserted in between. Got {page2_ids} instead - if this contains "
        "the newly-inserted task's id or repeats a page-1 id, pagination is "
        "using OFFSET instead of a stable cursor."
    )


def test_search_limit_capped_at_100(client):
    for i in range(120):
        client.post("/tasks", json={"title": f"Bulk {i}"})
    r = client.get("/tasks/search", params={"limit": 500})
    assert r.status_code == 200
    assert len(r.json()["results"]) <= 100, "limit must be capped at 100 even if a larger value is requested"
