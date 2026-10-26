import sqlite3, json, os, time
DB = os.path.join(os.path.dirname(__file__), "tasks.db")

def _c():
    c = sqlite3.connect(DB, timeout=10); c.row_factory = sqlite3.Row; return c

def init():
    with _c() as c:
        c.execute("""CREATE TABLE IF NOT EXISTS tasks(id TEXT PRIMARY KEY, request TEXT, status TEXT,
                     events TEXT, result TEXT, duration REAL, created REAL, demo INTEGER)""")

def create(tid, request, demo):
    with _c() as c:
        c.execute("INSERT INTO tasks VALUES(?,?,?,?,?,?,?,?)",
                  (tid, request, "running", "[]", "{}", None, time.time(), int(demo)))

def update(tid, status=None, events=None, result=None, duration=None):
    with _c() as c:
        if status is not None: c.execute("UPDATE tasks SET status=? WHERE id=?", (status, tid))
        if events is not None: c.execute("UPDATE tasks SET events=? WHERE id=?", (json.dumps(events), tid))
        if result is not None: c.execute("UPDATE tasks SET result=? WHERE id=?", (json.dumps(result), tid))
        if duration is not None: c.execute("UPDATE tasks SET duration=? WHERE id=?", (duration, tid))

def get(tid):
    with _c() as c:
        r = c.execute("SELECT * FROM tasks WHERE id=?", (tid,)).fetchone()
    if not r: return None
    d = dict(r); d["events"] = json.loads(d["events"]); d["result"] = json.loads(d["result"]); d["demo"] = bool(d["demo"])
    return d
