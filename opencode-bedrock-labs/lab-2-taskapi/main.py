import base64
import json
import time
from typing import Optional

from fastapi import FastAPI, HTTPException
from pydantic import BaseModel

from db import get_conn, init_db

app = FastAPI(title="Task Manager API")
init_db()


class TaskCreate(BaseModel):
    title: str
    description: str = ""
    status: str = "open"
    priority: int = 3


class TaskUpdate(BaseModel):
    title: Optional[str] = None
    description: Optional[str] = None
    status: Optional[str] = None
    priority: Optional[int] = None


def row_to_dict(row) -> dict:
    return {
        "id": row["id"],
        "title": row["title"],
        "description": row["description"],
        "status": row["status"],
        "priority": row["priority"],
        "created_at": row["created_at"],
    }


def escape_like(s: str) -> str:
    """Escape a user-supplied string for safe use inside a LIKE pattern.

    Order matters: backslash must be escaped first, or the escapes for
    % and _ would themselves get double-escaped.
    """
    return s.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")


def encode_cursor(created_at: float, id_: int) -> str:
    """Encode a (created_at, id) keyset anchor as an opaque cursor token."""
    payload = {"v": 1, "created_at": created_at, "id": id_}
    raw = json.dumps(payload).encode("utf-8")
    return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")


def decode_cursor(cursor: str) -> tuple:
    """Decode and validate an opaque cursor token.

    Raises HTTPException(400, "invalid cursor") if the token is malformed,
    is not version 1, or is missing/mistyped fields.
    """
    try:
        padded = cursor + "=" * (-len(cursor) % 4)
        raw = base64.urlsafe_b64decode(padded.encode("ascii"))
        payload = json.loads(raw)
    except Exception:
        raise HTTPException(status_code=400, detail="invalid cursor")

    if not isinstance(payload, dict):
        raise HTTPException(status_code=400, detail="invalid cursor")

    if payload.get("v") != 1:
        raise HTTPException(status_code=400, detail="invalid cursor")

    created_at = payload.get("created_at")
    if isinstance(created_at, bool) or not isinstance(created_at, (int, float)):
        raise HTTPException(status_code=400, detail="invalid cursor")

    id_ = payload.get("id")
    if isinstance(id_, bool) or not isinstance(id_, int):
        raise HTTPException(status_code=400, detail="invalid cursor")

    return created_at, id_


@app.post("/tasks", status_code=201)
def create_task(task: TaskCreate):
    conn = get_conn()
    cur = conn.execute(
        "INSERT INTO tasks (title, description, status, priority, created_at) VALUES (?, ?, ?, ?, ?)",
        (task.title, task.description, task.status, task.priority, time.time()),
    )
    conn.commit()
    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (cur.lastrowid,)).fetchone()
    conn.close()
    return row_to_dict(row)


# NOTE: this static route MUST be declared before GET /tasks/{task_id}.
# Starlette matches routes in declaration order, and "search" fails the
# int coercion for {task_id} -- if this handler is moved below get_task,
# every request to /tasks/search will 422 instead of matching here.
@app.get("/tasks/search")
def search_tasks(
    q: Optional[str] = None,
    status: Optional[str] = None,
    min_priority: Optional[int] = None,
    max_priority: Optional[int] = None,
    cursor: Optional[str] = None,
    limit: int = 20,
):
    """Search tasks with filters and stable keyset pagination.

    - q: case-insensitive (ASCII only) substring match on title.
    - status: exact match.
    - min_priority / max_priority: inclusive range filter.
    - cursor: opaque token from a previous response's next_cursor; pass
      it back verbatim to fetch the next page. Filters are NOT encoded
      in the cursor -- resend the same q/status/min_priority/max_priority
      alongside cursor on every request. Changing filters while holding
      a cursor yields undefined-but-safe results.
    - limit: page size, silently clamped to [1, 100] (never rejected).

    Pagination is keyset-based (sort key: created_at DESC, id DESC), not
    offset-based, so results stay stable (no duplicates, no skips) even
    if tasks are inserted or deleted between page requests.

    Known limitation: non-ASCII characters in q are matched
    case-sensitively (SQLite's LIKE/LOWER are ASCII-only).
    """
    c_created_at = None
    c_id = None
    if cursor is not None:
        c_created_at, c_id = decode_cursor(cursor)

    effective_limit = max(1, min(limit, 100))

    fragments = []
    params: list = []

    if q is not None:
        fragments.append("title LIKE ? ESCAPE '\\'")
        params.append("%" + escape_like(q) + "%")
    if status is not None:
        fragments.append("status = ?")
        params.append(status)
    if min_priority is not None:
        fragments.append("priority >= ?")
        params.append(min_priority)
    if max_priority is not None:
        fragments.append("priority <= ?")
        params.append(max_priority)
    if cursor is not None:
        fragments.append("(created_at < ? OR (created_at = ? AND id < ?))")
        params.extend([c_created_at, c_created_at, c_id])

    sql = "SELECT id, title, description, status, priority, created_at FROM tasks"
    if fragments:
        sql += " WHERE " + " AND ".join(fragments)
    sql += " ORDER BY created_at DESC, id DESC LIMIT ?"
    params.append(effective_limit + 1)

    conn = get_conn()
    rows = conn.execute(sql, params).fetchall()
    conn.close()

    if len(rows) > effective_limit:
        rows = rows[:effective_limit]
        last = rows[-1]
        next_cursor = encode_cursor(last["created_at"], last["id"])
    else:
        next_cursor = None

    return {
        "results": [row_to_dict(r) for r in rows],
        "next_cursor": next_cursor,
        "limit": effective_limit,
    }


# NOTE: like /tasks/search above, this static route MUST be declared before
# DELETE /tasks/{task_id}. Starlette matches in declaration order and "bulk"
# fails the int coercion for {task_id} -- if this moves below delete_task,
# every DELETE /tasks/bulk returns 422 instead of matching here.
@app.delete("/tasks/bulk")
def bulk_delete_tasks(
    status: Optional[str] = None,
    max_priority: Optional[int] = None,
):
    """Delete every task matching the given filters (ANDed). Returns the count.

    At least one filter is required: an unfiltered call would silently wipe
    the table, so it is rejected with 400 rather than treated as "match all".
    """
    # `is None`, not falsiness: max_priority=0 is a real filter.
    if status is None and max_priority is None:
        raise HTTPException(
            status_code=400,
            detail="at least one filter (status, max_priority) is required",
        )

    fragments = []
    params: list = []
    if status is not None:
        fragments.append("status = ?")
        params.append(status)
    if max_priority is not None:
        fragments.append("priority <= ?")
        params.append(max_priority)

    sql = "DELETE FROM tasks WHERE " + " AND ".join(fragments)

    conn = get_conn()
    cur = conn.execute(sql, params)
    conn.commit()
    deleted = cur.rowcount
    conn.close()

    return {"deleted_count": deleted}


@app.get("/tasks/{task_id}")
def get_task(task_id: int):
    conn = get_conn()
    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    conn.close()
    if row is None:
        raise HTTPException(status_code=404, detail="task not found")
    return row_to_dict(row)


@app.get("/tasks")
def list_tasks():
    conn = get_conn()
    rows = conn.execute("SELECT * FROM tasks ORDER BY id").fetchall()
    conn.close()
    return [row_to_dict(r) for r in rows]


@app.patch("/tasks/{task_id}")
def update_task(task_id: int, update: TaskUpdate):
    conn = get_conn()
    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    if row is None:
        conn.close()
        raise HTTPException(status_code=404, detail="task not found")

    fields = update.model_dump(exclude_unset=True)
    if fields:
        set_clause = ", ".join(f"{k} = ?" for k in fields)
        conn.execute(f"UPDATE tasks SET {set_clause} WHERE id = ?", (*fields.values(), task_id))
        conn.commit()

    row = conn.execute("SELECT * FROM tasks WHERE id = ?", (task_id,)).fetchone()
    conn.close()
    return row_to_dict(row)


@app.delete("/tasks/{task_id}", status_code=204)
def delete_task(task_id: int):
    conn = get_conn()
    conn.execute("DELETE FROM tasks WHERE id = ?", (task_id,))
    conn.commit()
    conn.close()
    return None

