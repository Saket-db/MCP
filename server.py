import functools
import logging
import os
import time
from collections import deque
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException, Query, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from pydantic import BaseModel
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

# ============================================================
# 0. LOGGING SETUP
# ============================================================
# On Vercel only /tmp is writable (and it is temporary, per instance).
# Locally, logs go to logs.txt next to this file.

LOG_FILE = "/tmp/logs.txt" if os.getenv("VERCEL") else "logs.txt"

# Optional secret for reading logs. Set LOGS_TOKEN in Vercel env vars.
# If it is not set, /logs is open to anyone.
LOGS_TOKEN = os.getenv("LOGS_TOKEN")

# "logger" is not imported from anywhere: we create it here.
logger = logging.getLogger("mcp-server")
logger.setLevel(logging.INFO)
logger.propagate = False

_formatter = logging.Formatter("%(asctime)s | %(levelname)-7s | %(message)s")

# 1) Print to console -> visible in the Vercel dashboard "Logs" tab
_console_handler = logging.StreamHandler()
_console_handler.setFormatter(_formatter)
logger.addHandler(_console_handler)

# 2) Write to the text file
_file_handler = logging.FileHandler(LOG_FILE, encoding="utf-8")
_file_handler.setFormatter(_formatter)
logger.addHandler(_file_handler)


def logged_tool(fn):
    """Decorator: logs every call of a tool, its inputs and its result."""

    @functools.wraps(fn)
    def wrapper(*args, **kwargs):
        try:
            result = fn(*args, **kwargs)
            logger.info(f"tool={fn.__name__} args={args or kwargs} result={result}")
            return result
        except Exception as e:
            logger.error(f"tool={fn.__name__} args={args or kwargs} error={e}")
            raise

    return wrapper


def check_token(token: str | None) -> None:
    """
    Simple protection for the logs endpoints.
    The caller must pass ?token=<value of LOGS_TOKEN>.
    If LOGS_TOKEN is not set, no check is done.
    """
    if LOGS_TOKEN and token != LOGS_TOKEN:
        raise HTTPException(status_code=401, detail="Invalid or missing token.")


# ============================================================
# 1. MCP SERVER AND TOOLS
# ============================================================

mcp = FastMCP(
    "MCP Server",
    stateless_http=True,
    json_response=True,
    transport_security=TransportSecuritySettings(
        enable_dns_rebinding_protection=False
    ),
)


@mcp.tool()
@logged_tool
def add(a: int, b: int) -> int:
    """Add two numbers."""
    return a + b


@mcp.tool()
@logged_tool
def greet(name: str) -> str:
    """Greet a person by name."""
    return f"Hello, {name}!"


@mcp.tool()
@logged_tool
def multiply(a: int, b: int) -> int:
    """Multiply two numbers."""
    return a * b


@mcp.tool()
@logged_tool
def divide(a: int, b: int) -> float:
    """Divide a by b."""
    if b == 0:
        raise ValueError("Cannot divide by zero.")
    return a / b


@mcp.tool()
@logged_tool
def subtract(a: int, b: int) -> int:
    """Subtract b from a."""
    return a - b


# ============================================================
# 2. FASTAPI LIFECYCLE
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Server starting")
    async with mcp.session_manager.run():
        yield
    logger.info("Server stopping")


# ============================================================
# 3. FASTAPI APPLICATION
# ============================================================

app = FastAPI(
    title="MCP Server Dashboard",
    description="REST APIs and MCP tools",
    version="1.0.0",
    lifespan=lifespan,
)

app.mount("/mcp", mcp.streamable_http_app())

# Don't log these paths (the dashboard polls /api/health every 10s).
SKIP_PATHS = {"/api/health", "/logs", "/favicon.ico"}


@app.middleware("http")
async def log_requests(request: Request, call_next):
    start = time.perf_counter()
    try:
        response = await call_next(request)
    except Exception as e:
        logger.error(f"{request.method} {request.url.path} crashed: {e}")
        raise

    if request.url.path not in SKIP_PATHS:
        ms = round((time.perf_counter() - start) * 1000, 1)
        msg = f"{request.method} {request.url.path} -> {response.status_code} ({ms} ms)"
        if response.status_code >= 400:
            logger.warning(msg)
        else:
            logger.info(msg)
    return response


# ============================================================
# 4. REQUEST MODELS
# ============================================================

class Numbers(BaseModel):
    a: int
    b: int


class Greeting(BaseModel):
    name: str


# ============================================================
# 5. HEALTH CHECK + LOGS API
# ============================================================

@app.get("/api/health")
def health_check():
    return {
        "status": "online",
        "service": "MCP Server",
        "rest_api": "available",
        "mcp_endpoint": "/mcp",
        "log_file": LOG_FILE,
    }


@app.get("/logs", response_class=PlainTextResponse)
def get_logs(
    lines: int = Query(200, ge=1, le=5000, description="How many last lines"),
    token: str | None = Query(None),
):
    """Return the last N lines of the log file as plain text."""
    check_token(token)

    if not os.path.exists(LOG_FILE):
        return "No logs yet."

    with open(LOG_FILE, encoding="utf-8") as f:
        last_lines = deque(f, maxlen=lines)

    return "".join(last_lines) or "No logs yet."


@app.delete("/logs")
def clear_logs(token: str | None = Query(None)):
    """Empty the log file."""
    check_token(token)
    open(LOG_FILE, "w", encoding="utf-8").close()
    logger.info("Log file cleared")
    return {"cleared": True}


# ============================================================
# 6. REST APIs FOR CALCULATOR TOOLS
# ============================================================

@app.post("/api/add")
def api_add(data: Numbers):
    return {"result": add(data.a, data.b)}


@app.post("/api/subtract")
def api_subtract(data: Numbers):
    return {"result": subtract(data.a, data.b)}


@app.post("/api/multiply")
def api_multiply(data: Numbers):
    return {"result": multiply(data.a, data.b)}


@app.post("/api/divide")
def api_divide(data: Numbers):
    if data.b == 0:
        logger.warning(f"divide by zero rejected (a={data.a})")
        raise HTTPException(status_code=400, detail="Cannot divide by zero.")
    return {"result": divide(data.a, data.b)}


@app.post("/api/greet")
def api_greet(data: Greeting):
    return {"result": greet(data.name)}


# ============================================================
# 7. WEB DASHBOARD
# ============================================================

@app.get("/", response_class=HTMLResponse)
def dashboard():
    return """
<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>MCP Server Dashboard</title>
    <style>
        * { box-sizing: border-box; }
        body {
            font-family: Arial, sans-serif;
            max-width: 800px;
            margin: 35px auto;
            padding: 0 18px;
            background: #f4f6f9;
            color: #202938;
        }
        h1 { margin-bottom: 8px; }
        .subtitle { color: #64748b; margin-bottom: 25px; }
        .card {
            background: white;
            padding: 22px;
            margin: 18px 0;
            border-radius: 12px;
            box-shadow: 0 2px 8px #0000000d;
        }
        .status {
            display: inline-block;
            padding: 8px 12px;
            border-radius: 6px;
            font-weight: bold;
        }
        .online { color: #166534; background: #dcfce7; }
        .offline { color: #991b1b; background: #fee2e2; }
        input {
            width: 120px;
            max-width: 100%;
            padding: 11px;
            margin: 5px 4px 8px 0;
            border: 1px solid #cbd5e1;
            border-radius: 6px;
        }
        button {
            padding: 10px 14px;
            margin: 5px 5px 5px 0;
            background: #1d4ed8;
            color: white;
            border: none;
            border-radius: 6px;
            cursor: pointer;
        }
        button:hover { background: #1e40af; }
        pre {
            padding: 14px;
            background: #f1f5f9;
            border-radius: 6px;
            white-space: pre-wrap;
            overflow-wrap: anywhere;
            min-height: 42px;
        }
        #logsOutput { max-height: 320px; overflow-y: auto; font-size: 12px; }
        a { color: #1d4ed8; }
        code { background: #f1f5f9; padding: 3px 6px; border-radius: 4px; }
    </style>
</head>
<body>

    <h1>MCP Server Dashboard</h1>
    <p class="subtitle">Monitor the server and test your MCP tools through REST APIs.</p>

    <div class="card">
        <h2>Server Status</h2>
        <p><span id="status" class="status">Checking...</span></p>
        <p id="healthDetails">Checking the health endpoint...</p>
        <button onclick="checkHealth()">Check Again</button>
    </div>

    <div class="card">
        <h2>Calculator API</h2>
        <p>Enter two integers and select an operation.</p>
        <input id="a" type="number" step="1" value="10" placeholder="First number">
        <input id="b" type="number" step="1" value="5" placeholder="Second number">
        <div>
            <button onclick="calculate('add')">Add</button>
            <button onclick="calculate('subtract')">Subtract</button>
            <button onclick="calculate('multiply')">Multiply</button>
            <button onclick="calculate('divide')">Divide</button>
        </div>
        <h3>Response</h3>
        <pre id="calcResult">No request sent yet.</pre>
    </div>

    <div class="card">
        <h2>Greeting API</h2>
        <input id="name" type="text" value="Sanjith" placeholder="Enter a name">
        <button onclick="sendGreeting()">Greet</button>
        <pre id="greetResult">No request sent yet.</pre>
    </div>

    <div class="card">
        <h2>Logs</h2>
        <input id="logToken" type="password" placeholder="Token (if set)" style="width:200px">
        <button onclick="loadLogs()">Load Logs</button>
        <pre id="logsOutput">Click "Load Logs".</pre>
    </div>

    <div class="card">
        <h2>Available Endpoints</h2>
        <p><strong>Dashboard:</strong> <code>/</code></p>
        <p><strong>Health check:</strong> <code>GET /api/health</code></p>
        <p><strong>Calculator:</strong>
            <code>POST /api/add</code>, <code>/api/subtract</code>,
            <code>/api/multiply</code>, <code>/api/divide</code></p>
        <p><strong>Greeting:</strong> <code>POST /api/greet</code></p>
        <p><strong>Logs:</strong> <code>GET /logs?lines=200&amp;token=...</code></p>
        <p><strong>MCP:</strong> <code>/mcp</code></p>
        <p><a href="/docs">Open interactive REST API documentation</a></p>
        <p><a href="/api/health">Open health-check JSON</a></p>
    </div>

    <script>
        async function checkHealth() {
            const statusElement = document.getElementById("status");
            const detailsElement = document.getElementById("healthDetails");
            statusElement.textContent = "Checking...";
            statusElement.className = "status";
            try {
                const response = await fetch("/api/health", { cache: "no-store" });
                if (!response.ok) throw new Error("HTTP " + response.status);
                const data = await response.json();
                statusElement.textContent = "ONLINE";
                statusElement.className = "status online";
                detailsElement.textContent =
                    "Service: " + data.service +
                    " | REST API: " + data.rest_api +
                    " | MCP endpoint: " + data.mcp_endpoint;
            } catch (error) {
                statusElement.textContent = "OFFLINE / ERROR";
                statusElement.className = "status offline";
                detailsElement.textContent = "Health check failed: " + error.message;
            }
        }

        async function calculate(operation) {
            const aInput = document.getElementById("a");
            const bInput = document.getElementById("b");
            const output = document.getElementById("calcResult");
            if (aInput.value.trim() === "" || bInput.value.trim() === "") {
                output.textContent = "Please enter both numbers.";
                return;
            }
            const a = Number(aInput.value);
            const b = Number(bInput.value);
            if (!Number.isInteger(a) || !Number.isInteger(b)) {
                output.textContent = "Please enter valid integers.";
                return;
            }
            output.textContent = "Sending request...";
            try {
                const response = await fetch("/api/" + operation, {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ a: a, b: b })
                });
                const data = await response.json();
                if (!response.ok) {
                    output.textContent = "HTTP " + response.status + ": " +
                        (data.detail || "Request failed");
                    return;
                }
                output.textContent = "Operation: " + operation +
                    "\\nInput: " + a + ", " + b +
                    "\\nResult: " + data.result;
            } catch (error) {
                output.textContent = "Request failed: " + error.message;
            }
        }

        async function sendGreeting() {
            const name = document.getElementById("name").value.trim();
            const output = document.getElementById("greetResult");
            if (!name) {
                output.textContent = "Please enter a name.";
                return;
            }
            output.textContent = "Sending request...";
            try {
                const response = await fetch("/api/greet", {
                    method: "POST",
                    headers: { "Content-Type": "application/json" },
                    body: JSON.stringify({ name: name })
                });
                const data = await response.json();
                if (!response.ok) {
                    output.textContent = "Request failed: " + JSON.stringify(data);
                    return;
                }
                output.textContent = data.result;
            } catch (error) {
                output.textContent = "Request failed: " + error.message;
            }
        }

        async function loadLogs() {
            const token = document.getElementById("logToken").value.trim();
            const output = document.getElementById("logsOutput");
            output.textContent = "Loading...";
            try {
                const url = "/logs?lines=200" +
                    (token ? "&token=" + encodeURIComponent(token) : "");
                const response = await fetch(url, { cache: "no-store" });
                const text = await response.text();
                output.textContent = response.ok ? text : "HTTP " + response.status + ": " + text;
                output.scrollTop = output.scrollHeight;
            } catch (error) {
                output.textContent = "Request failed: " + error.message;
            }
        }

        checkHealth();
        setInterval(checkHealth, 10000);
    </script>
</body>
</html>
"""


# ============================================================
# 8. START THE SERVER (local only; Vercel imports `app` directly)
# ============================================================

if __name__ == "__main__":
    print("Starting MCP Server...")
    print("Dashboard: http://localhost:8000/")
    print("Logs:      http://localhost:8000/logs")
    uvicorn.run(app, host="0.0.0.0", port=8000)