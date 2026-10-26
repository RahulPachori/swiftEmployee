import json, os, re, time
import database as db, tools


def _gemini(prompt, timeout, json_mode=False):
    from google import genai
    from google.genai import types

    timeout = max(1, min(12, int(timeout)))
    client = genai.Client(
        api_key=os.environ["GEMINI_API_KEY"],
        http_options=types.HttpOptions(timeout=timeout * 1000),
    )
    cfg = types.GenerateContentConfig(response_mime_type="application/json") if json_mode else None
    response = client.models.generate_content(
        model=os.getenv("GEMINI_MODEL", "gemini-2.5-flash"),
        contents=prompt,
        config=cfg,
    )
    if not response.text:
        raise RuntimeError("Gemini returned an empty response")
    return response.text


def run_task(task_id, request, demo=False):
    t0 = time.time()
    timeout_seconds = max(15, float(os.getenv("TASK_TIMEOUT_SECONDS", "60")))
    deadline = t0 + timeout_seconds
    events = []

    def ev(step, status, detail=""):
        events.append({"step": step, "status": status, "detail": detail, "t": round(time.time() - t0, 2)})
        db.update(task_id, events=events)
        return len(events) - 1

    def upd(i, status, detail=""):
        events[i].update(status=status, detail=detail, t=round(time.time() - t0, 2))
        db.update(task_id, events=events)

    def check_deadline():
        if time.time() >= deadline:
            raise TimeoutError("Task deadline exceeded")

    def finish(status, result):
        db.update(task_id, status=status, events=events, result=result, duration=round(time.time() - t0, 2))

    try:
        # Use a deterministic plan; avoid spending an API call before search starts.
        i = ev("Understand and plan", "running")
        plan = {
            "title": "Research report",
            "query": request.strip(),
            "n_sources": 3,
            "steps": ["Search", "Report", "Verify"],
        }
        upd(i, "ok", f"Query: {plan['query']} | 3 sources | Search; Report; Verify")

        check_deadline()
        i = ev("Search web and fetch sources", "running")
        sources, errs = tools.search_web(plan["query"], plan["n_sources"], deadline - 3, demo)
        for error in errs:
            ev("Source issue", "warn", error)
        if not sources:
            raise RuntimeError("No source content could be retrieved. Check the search API key or try Demo mode.")
        upd(i, "ok" if len(sources) >= plan["n_sources"] else "warn",
            f"{len(sources)}/{plan['n_sources']} sources, {sum(bool(s.get('fetched')) for s in sources)} fully fetched")

        check_deadline()
        i = ev("Summarize findings", "running")
        findings = [f"{s['text'][:240].strip()}... [{k}]" for k, s in enumerate(sources, 1) if s.get("text", "").strip()]
        summary = " ".join(s["text"][:300].strip() for s in sources[:3] if s.get("text", "").strip())[:900]
        left = deadline - time.time()
        if not demo and left > 15:
            try:
                ctx = "\n\n".join(
                    f"[{k}] {s['title']} ({s['url']})\n{s['text']}"
                    for k, s in enumerate(sources, 1)
                )
                prompt = (
                    'Using ONLY these sources, return JSON {"summary":str (<=120 words),'
                    '"findings":[4-6 strings each ending with a citation like [1]]}. '
                    'Do not invent facts.\n'
                    f"Task: {request}\n\n{ctx}"
                )
                out = _gemini(prompt, min(12, left - 3), True)
                data = json.loads(out)
                if isinstance(data.get("summary"), str) and isinstance(data.get("findings"), list):
                    summary = data["summary"].strip() or summary
                    findings = [str(x) for x in data["findings"] if str(x).strip()] or findings
                    upd(i, "ok", "Gemini synthesis")
                else:
                    raise ValueError("Gemini response is missing summary or findings")
            except Exception as e:
                upd(i, "warn", f"LLM synthesis failed ({str(e)[:100]}); used extractive summary")
        else:
            upd(i, "warn" if not demo else "ok", "Extractive summary (demo or insufficient time)")

        # Report creation and verification are local operations and should still run
        # after synthesis fallback so a useful partial report is produced.
        i = ev("Create report", "running")
        path = tools.create_report(task_id, plan["title"], summary, findings, sources, demo)
        upd(i, "ok", os.path.basename(path))

        i = ev("Verify report", "running")
        checks = tools.verify_report(path, sources)
        passed = all(c["ok"] for c in checks)
        upd(i, "ok" if passed else "error", f"{sum(c['ok'] for c in checks)}/{len(checks)} checks passed")
        status = "failed" if not passed else ("completed" if len(sources) >= plan["n_sources"] and time.time() <= deadline else "partial")
        finish(status, {
            "summary": summary,
            "checks": checks,
            "artifact_id": task_id if passed else None,
            "sources": [{"url": s["url"], "title": s["title"], "fetched": bool(s.get("fetched"))} for s in sources],
            "error": None if passed else "Verification failed",
        })
    except Exception as e:
        ev("Task failed", "error", str(e)[:300])
        finish("failed", {"summary": "", "checks": [], "artifact_id": None, "sources": [], "error": str(e)[:300]})
