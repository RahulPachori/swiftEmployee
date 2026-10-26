import os, re, time
from concurrent.futures import ThreadPoolExecutor, wait
from io import BytesIO

OUTPUT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", "output"))
MAX_CHARS = 3000
FIXTURE = [
    {"url": "https://example.com/demo-1", "title": "Demo source 1", "text": "Fixture text: AI agents plan, call tools and verify results in a loop.", "fetched": True},
    {"url": "https://example.com/demo-2", "title": "Demo source 2", "text": "Fixture text: Reliable agents use deterministic code for non-LLM work.", "fetched": True},
    {"url": "https://example.com/demo-3", "title": "Demo source 3", "text": "Fixture text: Latency is controlled with deadlines, timeouts and bounded retries.", "fetched": True},
]


def _fetch(src, deadline):
    import requests
    from bs4 import BeautifulSoup

    left = deadline - time.time()
    if left < 1:
        return {**src, "text": src.get("snippet", "")[:MAX_CHARS], "fetched": False, "error": "Task deadline reached before fetch"}

    try:
        response = requests.get(
            src["url"],
            timeout=(min(2, max(1, left)), min(3, max(1, left))),
            headers={"User-Agent": "Mozilla/5.0 SwiftEmployee/1.0"},
        )
        response.raise_for_status()
        content_type = response.headers.get("content-type", "").lower()
        is_pdf = "application/pdf" in content_type or response.url.lower().split("?")[0].endswith(".pdf")

        if is_pdf:
            from pypdf import PdfReader
            reader = PdfReader(BytesIO(response.content))
            text = " ".join((page.extract_text() or "") for page in reader.pages[:10])
        else:
            soup = BeautifulSoup(response.text, "html.parser")
            for tag in soup(["script", "style", "nav", "footer", "header", "noscript"]):
                tag.decompose()
            text = soup.get_text(" ", strip=True)

        text = re.sub(r"\s+", " ", text).strip()[:MAX_CHARS]
        if len(text) >= 200:
            return {**src, "text": text, "fetched": True}
        return {**src, "text": src.get("snippet", "")[:MAX_CHARS], "fetched": False,
                "error": "page text too short (used search snippet)"}
    except Exception as e:
        return {**src, "text": src.get("snippet", "")[:MAX_CHARS], "fetched": False, "error": str(e)[:120]}


def search_web(query, n, deadline, demo=False):
    """Return source records and warnings; use snippets when pages cannot be fetched."""
    if demo:
        return FIXTURE[:n], []

    import requests
    left = deadline - time.time()
    if left < 1:
        raise TimeoutError("Task deadline reached before web search")
    response = requests.post(
        "https://api.tavily.com/search",
        timeout=(min(3, max(1, left)), min(6, max(1, left))),
        headers={"Authorization": f"Bearer {os.environ['SEARCH_API_KEY']}"},
        json={"query": query, "max_results": n},
    )
    response.raise_for_status()
    hits = [
        {"url": h["url"], "title": h.get("title", h["url"]), "snippet": h.get("content", "")}
        for h in response.json().get("results", [])[:n]
        if h.get("url")
    ]
    if not hits:
        return [], ["Search returned no results"]

    executor = ThreadPoolExecutor(max_workers=min(5, len(hits)))
    futures = [executor.submit(_fetch, src, deadline) for src in hits]
    remaining = max(0, deadline - time.time())
    done, pending = wait(futures, timeout=remaining)
    for future in pending:
        future.cancel()
    # Do not wait for slow workers after the task deadline.
    executor.shutdown(wait=False, cancel_futures=True)

    srcs = []
    for future, src in zip(futures, hits):
        if future in done:
            try:
                srcs.append(future.result())
            except Exception as e:
                srcs.append({**src, "text": src.get("snippet", "")[:MAX_CHARS], "fetched": False, "error": str(e)[:120]})
        else:
            srcs.append({**src, "text": src.get("snippet", "")[:MAX_CHARS], "fetched": False, "error": "Fetch deadline exceeded"})

    errs = [f"{s['url']}: {s.get('error', 'page text too short')} (used search snippet)" for s in srcs if not s.get("fetched")]
    return [s for s in srcs if s.get("text", "").strip()], errs


def create_report(task_id, title, summary, findings, sources, demo=False):
    os.makedirs(OUTPUT, exist_ok=True)
    path = os.path.join(OUTPUT, f"report_{task_id}.md")
    md = [f"# {title}", ""]
    if demo:
        md += ["> DEMO MODE: fixture data, not real research.", ""]
    md += ["## Summary", "", summary, "", "## Findings", ""]
    md += [f"- {f}" for f in findings] + ["", "## Sources", ""]
    md += [f"{i}. [{s['title']}]({s['url']}) - {s['url']}" for i, s in enumerate(sources, 1)]
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(md) + "\n")
    return path


def verify_report(path, sources):
    """Reopen the saved file and independently check the completion criteria."""
    checks = []

    def chk(name, ok):
        checks.append({"name": name, "ok": bool(ok)})

    exists = os.path.isfile(path)
    chk("Report file exists", exists)
    text = ""
    if exists:
        try:
            with open(path, encoding="utf-8") as f:
                text = f.read()
        except Exception:
            pass
    chk("Report is readable and non-trivial", len(text) > 200)
    chk("Has Summary, Findings and Sources sections", all(h in text for h in ("## Summary", "## Findings", "## Sources")))
    chk("Includes every collected source URL", bool(sources) and all(s["url"] in text for s in sources))
    return checks
