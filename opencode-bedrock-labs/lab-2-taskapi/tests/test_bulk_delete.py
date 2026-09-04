"""
Acceptance tests for DELETE /tasks/bulk - the SECOND missing feature, added
in Lab 2 Part D. Not implemented yet; these should all fail until it exists.
"""


def _make(client, title, status="open", priority=3):
    return client.post("/tasks", json={"title": title, "status": status, "priority": priority}).json()


def test_bulk_delete_by_status(client):
    _make(client, "A", status="done")
    _make(client, "B", status="done")
    _make(client, "C", status="open")

    r = client.request("DELETE", "/tasks/bulk", params={"status": "done"})
    assert r.status_code == 200
    assert r.json() == {"deleted_count": 2}

    remaining = client.get("/tasks").json()
    assert len(remaining) == 1
    assert remaining[0]["title"] == "C"


def test_bulk_delete_by_max_priority(client):
    _make(client, "Low1", priority=1)
    _make(client, "Low2", priority=2)
    _make(client, "High", priority=5)

    r = client.request("DELETE", "/tasks/bulk", params={"max_priority": 2})
    assert r.status_code == 200
    assert r.json() == {"deleted_count": 2}
    assert len(client.get("/tasks").json()) == 1


def test_bulk_delete_combines_filters_with_and(client):
    _make(client, "Match", status="done", priority=1)
    _make(client, "WrongStatus", status="open", priority=1)
    _make(client, "WrongPriority", status="done", priority=5)

    r = client.request("DELETE", "/tasks/bulk", params={"status": "done", "max_priority": 2})
    assert r.status_code == 200
    assert r.json() == {"deleted_count": 1}
    remaining_titles = {t["title"] for t in client.get("/tasks").json()}
    assert remaining_titles == {"WrongStatus", "WrongPriority"}


def test_bulk_delete_with_no_filters_is_rejected(client):
    """Safety requirement: no filters means 'delete everything' by accident.
    This must be a 400, not a successful full-table wipe."""
    _make(client, "Should survive")
    r = client.request("DELETE", "/tasks/bulk")
    assert r.status_code == 400
    assert len(client.get("/tasks").json()) == 1


def test_bulk_delete_matching_nothing_returns_zero(client):
    _make(client, "Untouched", status="open")
    r = client.request("DELETE", "/tasks/bulk", params={"status": "archived"})
    assert r.status_code == 200
    assert r.json() == {"deleted_count": 0}
    assert len(client.get("/tasks").json()) == 1
