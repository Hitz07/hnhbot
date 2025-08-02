from fastapi import FastAPI, Request, Form
from fastapi.responses import HTMLResponse, RedirectResponse
from fastapi.templating import Jinja2Templates
from fastapi import WebSocket, WebSocketDisconnect
from urllib.parse import parse_qs
from datetime import datetime
import json

app = FastAPI()
templates = Jinja2Templates(directory="templates")

with open("users.json") as f:
    valid_users = json.load(f)

active_sessions = {}
connected_clients = []
chat_history = []

@app.get("/", response_class=HTMLResponse)
async def show_login(request: Request):
    return templates.TemplateResponse("login.html", {"request": request, "error": None})

@app.post("/login", response_class=HTMLResponse)
async def login(request: Request, username: str = Form(...), password: str = Form(...)):
    if username in valid_users and valid_users[username] == password:
        active_sessions[request.client.host] = username
        return RedirectResponse(url="/chat", status_code=302)
    return templates.TemplateResponse("login.html", {"request": request, "error": "Invalid credentials"})

@app.get("/logout")
async def logout(request: Request):
    if request.client.host in active_sessions:
        del active_sessions[request.client.host]
    return RedirectResponse(url="/", status_code=302)

@app.get("/chat", response_class=HTMLResponse)
async def chat_page(request: Request):
    user = active_sessions.get(request.client.host)
    if not user:
        return RedirectResponse(url="/", status_code=302)
    return templates.TemplateResponse("chat.html", {"request": request, "username": user})

@app.websocket("/ws")
async def websocket_endpoint(websocket: WebSocket):
    query = parse_qs(websocket.url.query)
    sender = query.get("user", ["Unknown"])[0]

    await websocket.accept()

    if len(connected_clients) >= 2:
        await websocket.send_text("Chat room full. Only 2 users allowed.")
        await websocket.close()
        return

    websocket.sender = sender
    connected_clients.append(websocket)

    already_sent = set()
    for msg in chat_history:
        if msg not in already_sent:
            await websocket.send_text(msg)
            already_sent.add(msg)

    try:
        while True:
            data = await websocket.receive_text()

            if data.startswith("__typing__:"):
                for client in connected_clients:
                    if client != websocket:
                        await client.send_text(data)
                continue

            if data == "__clear__":
                chat_history.clear()
                for client in connected_clients:
                    await client.send_text("Chat cleared by user.")
                continue

            timestamp = datetime.now().strftime("%H:%M")
            formatted_msg = f"{sender}: {data} [{timestamp}]"
            chat_history.append(formatted_msg)

            for client in connected_clients:
                if client.sender == sender:
                    await client.send_text(f"You: {data} [{timestamp}]")
                else:
                    await client.send_text(formatted_msg)

    except WebSocketDisconnect:
        if websocket in connected_clients:
            connected_clients.remove(websocket)
