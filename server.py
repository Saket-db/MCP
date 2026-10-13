
from contextlib import asynccontextmanager

import uvicorn
from fastapi import FastAPI, HTTPException
from fastapi.responses import HTMLResponse
from pydantic import BaseModel
from mcp.server.fastmcp import FastMCP
from mcp.server.transport_security import TransportSecuritySettings

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
def add(a: int, b: int) -> int:
    """Add two numbers."""
    print(f"Adding {a} and {b}")
    return a + b


@mcp.tool()
def greet(name: str) -> str:
    """Greet a person by name."""
    print(f"Greeting {name}")
    return f"Hello, {name}!"


@mcp.tool()
def multiply(a: int, b: int) -> int:
    """Multiply two numbers."""
    print(f"Multiplying {a} and {b}")
    return a * b


@mcp.tool()
def divide(a: int, b: int) -> float:
    """Divide a by b."""
    if b == 0:
        raise ValueError("Cannot divide by zero.")
    return a / b


@mcp.tool()
def subtract(a: int, b: int) -> int:
    """Subtract b from a."""
    return a - b



# ============================================================
# 2. FASTAPI LIFECYCLE
# ============================================================

@asynccontextmanager
async def lifespan(app: FastAPI):
    # Start the MCP session manager when FastAPI starts.
    async with mcp.session_manager.run():
        yield


# ============================================================
# 3. FASTAPI APPLICATION
# ============================================================

app = FastAPI(
    title="MCP Server Dashboard",
    description="REST APIs and MCP tools",
    version="1.0.0",
    lifespan=lifespan,
)


# Mount the MCP Streamable HTTP endpoint.
app.mount("/mcp", mcp.streamable_http_app())


# ============================================================
# 4. REQUEST MODELS
# ============================================================

class Numbers(BaseModel):
    a: int
    b: int


class Greeting(BaseModel):
    name: str


# ============================================================
# 5. HEALTH CHECK API
# ============================================================

@app.get("/api/health")
def health_check():
    return {
        "status": "online",
        "service": "MCP Server",
        "rest_api": "available",
        "mcp_endpoint": "/mcp",
    }


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
        raise HTTPException(
            status_code=400,
            detail="Cannot divide by zero.",
        )

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
        * {
            box-sizing: border-box;
        }

        body {
            font-family: Arial, sans-serif;
            max-width: 800px;
            margin: 35px auto;
            padding: 0 18px;
            background: #f4f6f9;
            color: #202938;
        }

        h1 {
            margin-bottom: 8px;
        }

        .subtitle {
            color: #64748b;
            margin-bottom: 25px;
        }

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

        .online {
            color: #166534;
            background: #dcfce7;
        }

        .offline {
            color: #991b1b;
            background: #fee2e2;
        }

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

        button:hover {
            background: #1e40af;
        }

        pre {
            padding: 14px;
            background: #f1f5f9;
            border-radius: 6px;
            white-space: pre-wrap;
            overflow-wrap: anywhere;
            min-height: 42px;
        }

        a {
            color: #1d4ed8;
        }

        code {
            background: #f1f5f9;
            padding: 3px 6px;
            border-radius: 4px;
        }
    </style>
</head>

<body>

    <h1>MCP Server Dashboard</h1>

    <p class="subtitle">
        Monitor the server and test your MCP tools through REST APIs.
    </p>

    <!-- SERVER HEALTH -->

    <div class="card">
        <h2>Server Status</h2>

        <p>
            <span id="status" class="status">
                Checking...
            </span>
        </p>

        <p id="healthDetails">
            Checking the health endpoint...
        </p>

        <button onclick="checkHealth()">
            Check Again
        </button>
    </div>


    <!-- CALCULATOR -->

    <div class="card">
        <h2>Calculator API</h2>

        <p>Enter two integers and select an operation.</p>

        <input
            id="a"
            type="number"
            step="1"
            value="10"
            placeholder="First number"
        >

        <input
            id="b"
            type="number"
            step="1"
            value="5"
            placeholder="Second number"
        >

        <div>
            <button onclick="calculate('add')">Add</button>

            <button onclick="calculate('subtract')">
                Subtract
            </button>

            <button onclick="calculate('multiply')">
                Multiply
            </button>

            <button onclick="calculate('divide')">
                Divide
            </button>
        </div>

        <h3>Response</h3>

        <pre id="calcResult">No request sent yet.</pre>
    </div>


    <!-- GREETING -->

    <div class="card">
        <h2>Greeting API</h2>

        <input
            id="name"
            type="text"
            value="Sanjith"
            placeholder="Enter a name"
        >

        <button onclick="sendGreeting()">
            Greet
        </button>

        <pre id="greetResult">No request sent yet.</pre>
    </div>


    <!-- ENDPOINTS -->

    <div class="card">
        <h2>Available Endpoints</h2>

        <p>
            <strong>Dashboard:</strong>
            <code>/</code>
        </p>

        <p>
            <strong>Health check:</strong>
            <code>GET /api/health</code>
        </p>

        <p>
            <strong>Calculator:</strong>
            <code>POST /api/add</code>,
            <code>/api/subtract</code>,
            <code>/api/multiply</code>,
            <code>/api/divide</code>
        </p>

        <p>
            <strong>Greeting:</strong>
            <code>POST /api/greet</code>
        </p>

        <p>
            <strong>MCP:</strong>
            <code>/mcp</code>
        </p>

        <p>
            <a href="/docs">Open interactive REST API documentation</a>
        </p>

        <p>
            <a href="/api/health">Open health-check JSON</a>
        </p>
    </div>


    <script>
        // ----------------------------------------------------
        // HEALTH CHECK
        // ----------------------------------------------------

        async function checkHealth() {
            const statusElement =
                document.getElementById("status");

            const detailsElement =
                document.getElementById("healthDetails");

            statusElement.textContent = "Checking...";
            statusElement.className = "status";

            try {
                const response = await fetch("/api/health", {
                    cache: "no-store"
                });

                if (!response.ok) {
                    throw new Error("HTTP " + response.status);
                }

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

                detailsElement.textContent =
                    "Health check failed: " + error.message;
            }
        }


        // ----------------------------------------------------
        // CALCULATOR API
        // ----------------------------------------------------

        async function calculate(operation) {
            const aInput = document.getElementById("a");
            const bInput = document.getElementById("b");

            const output =
                document.getElementById("calcResult");

            if (
                aInput.value.trim() === "" ||
                bInput.value.trim() === ""
            ) {
                output.textContent =
                    "Please enter both numbers.";
                return;
            }

            const a = Number(aInput.value);
            const b = Number(bInput.value);

            if (!Number.isInteger(a) || !Number.isInteger(b)) {
                output.textContent =
                    "Please enter valid integers.";
                return;
            }

            output.textContent = "Sending request...";

            try {
                const response = await fetch(
                    "/api/" + operation,
                    {
                        method: "POST",
                        headers: {
                            "Content-Type": "application/json"
                        },
                        body: JSON.stringify({a: a, b: b})
                    }
                );

                const data = await response.json();

                if (!response.ok) {
                    output.textContent =
                        "HTTP " + response.status +
                        ": " + (data.detail || "Request failed");
                    return;
                }

                output.textContent =
                    "Operation: " + operation +
                    "\\nInput: " + a + ", " + b +
                    "\\nResult: " + data.result;

            } catch (error) {
                output.textContent =
                    "Request failed: " + error.message;
            }
        }


        // ----------------------------------------------------
        // GREETING API
        // ----------------------------------------------------

        async function sendGreeting() {
            const name =
                document.getElementById("name").value.trim();

            const output =
                document.getElementById("greetResult");

            if (!name) {
                output.textContent = "Please enter a name.";
                return;
            }

            output.textContent = "Sending request...";

            try {
                const response = await fetch("/api/greet", {
                    method: "POST",
                    headers: {
                        "Content-Type": "application/json"
                    },
                    body: JSON.stringify({name: name})
                });

                const data = await response.json();

                if (!response.ok) {
                    output.textContent =
                        "Request failed: " +
                        JSON.stringify(data);
                    return;
                }

                output.textContent = data.result;

            } catch (error) {
                output.textContent =
                    "Request failed: " + error.message;
            }
        }


        // Initial check and periodic refresh.
        checkHealth();
        setInterval(checkHealth, 10000);
    </script>

</body>
</html>
"""


# ============================================================
# 8. START THE SERVER
# ============================================================

# if __name__ == "__main__":
#     print("Starting MCP Server...")
#     print("Dashboard: http://localhost/")
#     print("Health API: http://localhost/api/health")
#     print("REST API docs: http://localhost/docs")
#     print("MCP endpoint: http://localhost/mcp")

#     uvicorn.run(
#         app
#     )


if __name__ == "__main__":
    print("Starting MCP Server...")
    print("Dashboard: http://localhost/")
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=8000
    )