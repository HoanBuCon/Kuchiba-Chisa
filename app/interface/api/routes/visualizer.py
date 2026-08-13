import os
import json
import asyncio
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse
from typing import List, Dict, Any
from app.infrastructure.logging.pipeline_tracker import pipeline_tracker

router = APIRouter()

TEMPLATES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
    "templates"
)
DASHBOARD_FILE = os.path.join(TEMPLATES_DIR, "visualizer_dashboard.html")

@router.get("/api/v1/visualizer/traces", response_model=List[Dict[str, Any]])
async def get_traces():
    """Get the history of chat pipeline traces."""
    return pipeline_tracker.get_traces()

@router.websocket("/api/v1/visualizer/ws")
async def websocket_endpoint(websocket: WebSocket):
    """Real-time WebSocket feed of chat pipeline execution traces."""
    await websocket.accept()
    
    queue: asyncio.Queue = asyncio.Queue()
    loop = asyncio.get_running_loop()
    
    def listener(trace: Dict[str, Any]):
        # Safely schedule the trace to be put in the queue on the event loop
        loop.call_soon_threadsafe(queue.put_nowait, trace)
        
    pipeline_tracker.register_listener(listener)
    
    try:
        while True:
            trace = await queue.get()
            text = json.dumps(trace, default=str, ensure_ascii=False)
            await websocket.send_text(text)
    except WebSocketDisconnect:
        pass
    finally:
        pipeline_tracker.unregister_listener(listener)

@router.get("/visualizer", response_class=HTMLResponse)
async def serve_dashboard():
    """Serve the premium visualizer dashboard webpage."""
    if not os.path.exists(DASHBOARD_FILE):
        return HTMLResponse(
            content=f"<h3>Error: Visualizer dashboard file not found at {DASHBOARD_FILE}</h3>",
            status_code=404
        )
    
    with open(DASHBOARD_FILE, "r", encoding="utf-8") as f:
        html_content = f.read()
        
    return HTMLResponse(content=html_content)
