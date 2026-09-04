def test_create_and_get_task(client):
    r = client.post("/tasks", json={"title": "Write report", "priority": 2})
    assert r.status_code == 201
    task = r.json()
    assert task["title"] == "Write report"
    assert task["status"] == "open"

    r2 = client.get(f"/tasks/{task['id']}")
    assert r2.status_code == 200
    assert r2.json()["title"] == "Write report"


def test_get_missing_task_404(client):
    r = client.get("/tasks/9999")
    assert r.status_code == 404


def test_list_tasks(client):
    client.post("/tasks", json={"title": "A"})
    client.post("/tasks", json={"title": "B"})
    r = client.get("/tasks")
    assert r.status_code == 200
    assert len(r.json()) == 2


def test_update_task(client):
    created = client.post("/tasks", json={"title": "Old title"}).json()
    r = client.patch(f"/tasks/{created['id']}", json={"status": "done"})
    assert r.status_code == 200
    assert r.json()["status"] == "done"
    assert r.json()["title"] == "Old title"


def test_delete_task(client):
    created = client.post("/tasks", json={"title": "Temp"}).json()
    r = client.delete(f"/tasks/{created['id']}")
    assert r.status_code == 204
    assert client.get(f"/tasks/{created['id']}").status_code == 404
