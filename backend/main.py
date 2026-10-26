import os, re, uuid
from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from pydantic import BaseModel

def _load_env():
    p = os.path.join(os.path.dirname(__file__), ".env")
    if os.path.exists(p):
        for line in open(p, encoding="utf-8"):
            if "=" in line and not line.startswith("#"):
                k, v = line.strip().split("=", 1); os.environ.setdefault(k, v)
_load_env()
import database as db, agent, tools

db.init()
app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=[
        "http://localhost:5173",
        "https://swift-employee.vercel.app"
    ], allow_methods=["*"], allow_headers=["*"])

class TaskIn(BaseModel):
    request: str
    demo: bool = False

@app.post("/api/tasks")
def start(body: TaskIn, bg: BackgroundTasks):
    if not body.request.strip(): raise HTTPException(400, "Enter a task first.")
    if not body.demo:
        missing = [k for k in ("GEMINI_API_KEY", "SEARCH_API_KEY") if not os.getenv(k)]
        if missing: raise HTTPException(400, f"Missing {', '.join(missing)} in backend/.env. Add them, or tick Demo mode.")
    tid = uuid.uuid4().hex
    db.create(tid, body.request, body.demo)
    bg.add_task(agent.run_task, tid, body.request, body.demo)
    return {"task_id": tid}

@app.get("/api/tasks/{task_id}")
def status(task_id: str):
    t = db.get(task_id) if re.fullmatch(r"[a-f0-9]{32}", task_id) else None
    if not t: raise HTTPException(404, "Task not found")
    return t

@app.get("/api/artifacts/{artifact_id}/download")
def download(artifact_id: str):
    if not re.fullmatch(r"[a-f0-9]{32}", artifact_id): raise HTTPException(400, "Invalid artifact id")
    t = db.get(artifact_id)
    path = os.path.realpath(os.path.join(tools.OUTPUT, f"report_{artifact_id}.md"))
    if not t or not path.startswith(os.path.realpath(tools.OUTPUT) + os.sep) or not os.path.isfile(path):
        raise HTTPException(404, "Report not found")
    return FileResponse(path, media_type="text/markdown", filename=f"report_{artifact_id[:8]}.md")
