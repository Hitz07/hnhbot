from fastapi import FastAPI, Request, Form, WebSocket, WebSocketDisconnect
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
import json
import logging
from datetime import datetime
import pytz
import os

# --- Logger setup ---
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("hnhbot")

app = FastAPI()
templates = Jinja2Templates(directory="templates")

# --- Globals ---
connected_clients = {}

# --- Timezone ---
ist = pytz.timezone("Asia/Kolkata")

def current_ist_time():
    return datetime.now(ist).strftime("[%Y-%m-%d %H:%M]")

# --- Paths ---
HISTORY_FILE = "chat_history.json"

def load_chat_history():
    if not os.path.exists(HISTORY_FILE):
        with open(HISTORY_FILE, "w") as f:
            json.dump([], f)
    with open(HISTORY_FILE, "r") as f:
        return json.load(f)

def save_chat_history(history):
    with open(HISTORY_FILE, "w") as f:
        json.dump(history, f, indent=2)

# Load existing chat
chat_history = load_chat_history()

# Load users
with open("users.json") as f:
    valid_users = json.load(f)

# Sessions
active_sessions = {}

@app.get("/", response_class=HTMLResponse)
async def show_login(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})

@app.post("/login", response_class=HTMLResponse)
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    if username in valid_users and valid_users[username] == password:
        active_sessions[request.client.host] = username
        logger.info(f"[LOGIN] {username} logged in from {request.client.host}")
        return RedirectResponse(url="/chat", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid credentials"})

@app.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request):
    user = active_sessions.get(request.client.host)
    if not user:
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse("chat.html", {"request": request, "username": user})

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    await websocket.accept()
    username = websocket.query_params.get("user", "Unknown")
    logger.info(f"[WS CONNECT] {username} connected")

    if len(connected_clients) >= 2:
        await websocket.send_text("Chat room full. Only 2 users allowed.")
        await websocket.close()
        return

    connected_clients[websocket] = username

    # Send previous messages
    for item in chat_history:
        sender = item["user"]
        timestamp = item["timestamp"]
        label = "You" if sender == username else sender

        if item.get("type") == "emotion":
            emotion = item["message"]
            await websocket.send_text(f"💌 {label} sent {emotion} {timestamp}")
        else:
            message = item["message"]
            await websocket.send_text(f"{label}: {message} {timestamp}")

    try:
        while True:
            data = await websocket.receive_text()

            if data == "__clear__":
                logger.info(f"[CLEAR] Chat cleared by {username}")
                chat_history.clear()
                save_chat_history(chat_history)
                for client in connected_clients:
                    await client.send_text("Chat cleared by user.")
                continue

            if data.startswith("__typing__"):
                typing_msg = f"{username} is typing... {current_ist_time()}"
                for client in connected_clients:
                    if client != websocket:
                        await client.send_text(f"__typing__:{typing_msg}")
                continue

            timestamp = current_ist_time()

            if data.startswith("__emotion__:"):
                emotion_type = data.replace("__emotion__:", "").strip()
                emotion_display = {
                    "love": "❤️ Love",
                    "hug": "🤗 Hug",
                    "kiss": "😘 Kiss",
                    "miss": "🥺 Miss you"
                }.get(emotion_type, f"✨ {emotion_type}")

                msg_record = {
                    "user": username,
                    "message": emotion_display,
                    "timestamp": timestamp,
                    "type": "emotion"
                }
                chat_history.append(msg_record)
                save_chat_history(chat_history)

                for client in connected_clients:
                    label = "You" if client == websocket else username
                    await client.send_text(f"💌 {label} sent {emotion_display} {timestamp}")
            else:
                msg_record = {
                    "user": username,
                    "message": data,
                    "timestamp": timestamp,
                    "type": "text"
                }
                chat_history.append(msg_record)
                save_chat_history(chat_history)

                for client in connected_clients:
                    label = "You" if client == websocket else username
                    await client.send_text(f"{label}: {data} {timestamp}")

    except WebSocketDisconnect:
        logger.info(f"[DISCONNECT] {username} disconnected")
        connected_clients.pop(websocket, None)
