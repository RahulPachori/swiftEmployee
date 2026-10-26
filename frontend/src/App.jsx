import { useState, useRef, useEffect } from "react";

const SAMPLE = "Research AI agents using three real sources, summarize the findings, create a report, and verify the report.";

export default function App() {
  const [text, setText] = useState(SAMPLE);
  const [demo, setDemo] = useState(false);
  const [task, setTask] = useState(null);
  const [error, setError] = useState("");
  const timer = useRef(null);

  useEffect(() => () => clearInterval(timer.current), []);

  const poll = (id) => {
    clearInterval(timer.current);
    timer.current = setInterval(async () => {
      try {
        const response = await fetch(`/api/tasks/${id}`);
        if (!response.ok) throw new Error("Task status request failed");
        const currentTask = await response.json();
        setTask(currentTask);
        if (currentTask.status !== "running") clearInterval(timer.current);
      } catch {
        setError("Lost connection to the backend. Check that the backend is still running.");
        clearInterval(timer.current);
      }
    }, 1000);
  };

  const run = async () => {
    clearInterval(timer.current);
    setError("");
    setTask(null);
    if (!text.trim()) {
      setError("Enter a research task first.");
      return;
    }

    try {
      const response = await fetch("/api/tasks", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ request: text, demo }),
      });

      let data;
      try {
        data = await response.json();
      } catch {
        setError("Invalid response from the backend. Check the backend terminal.");
        return;
      }

      if (!response.ok) {
        setError(data.detail || "Could not start the task.");
        return;
      }
      setTask({ status: "running", events: [], result: {} });
      poll(data.task_id);
    } catch {
      setError("Backend not reachable. Start uvicorn on port 8000.");
    }
  };

  const res = task?.result || {};
  const running = task?.status === "running";

  return (
    <main>
      <h1>SwiftEmployee</h1>
      <p className="lede">Describe a research task. It plans, searches, writes a report and checks its own work.</p>
      <textarea value={text} onChange={(e) => setText(e.target.value)} rows={3} />
      <div className="bar">
        <button onClick={run} disabled={running}>{running ? "Running…" : "Run task"}</button>
        <label><input type="checkbox" checked={demo} onChange={(e) => setDemo(e.target.checked)} /> Demo mode (fixture data, no APIs)</label>
      </div>
      {error && <p className="err">{error}</p>}
      {task && (
        <>
          <section>
            <h2>Timeline <span className={`pill ${task.status}`}>{task.status}</span>
              {task.duration != null && <span className="dur">{task.duration}s total</span>}</h2>
            <ol className="timeline">
              {(task.events || []).map((event, index) => (
                <li key={index} className={event.status}>
                  <b>{event.step}</b> <small>{event.t}s</small><div>{event.detail}</div>
                </li>
              ))}
            </ol>
          </section>
          {res.checks?.length > 0 && (
            <section><h2>Verification</h2>
              <ul className="checks">{res.checks.map((check) => <li key={check.name} className={check.ok ? "ok" : "error"}>{check.ok ? "Pass" : "Fail"}: {check.name}</li>)}</ul>
            </section>
          )}
          {res.summary && (
            <section><h2>Summary</h2><p>{res.summary}</p>
              <ul className="sources">{(res.sources || []).map((source) => <li key={source.url}><a href={source.url} target="_blank" rel="noreferrer">{source.title}</a>{!source.fetched && " (snippet only)"}</li>)}</ul>
              {res.artifact_id && <a className="dl" href={`/api/artifacts/${res.artifact_id}/download`}>Download report</a>}
            </section>
          )}
          {res.error && <p className="err">{res.error}</p>}
        </>
      )}
    </main>
  );
}
