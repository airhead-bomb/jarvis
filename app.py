import os

from fastapi import FastAPI, File, Form, Request, UploadFile
from fastapi.responses import FileResponse, HTMLResponse, JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from itsdangerous import BadSignature, SignatureExpired, URLSafeTimedSerializer
from pydantic import BaseModel

from brain import ask_jarvis, ask_jarvis_with_file, ask_jarvis_with_image, reset_memory
from file_reader import extract_text

STATIC_DIR = os.path.join(os.path.dirname(__file__), "static")

APP_USERNAME = os.environ.get("APP_USERNAME", "jarvis")
APP_PASSWORD = os.environ["APP_PASSWORD"]
SESSION_SECRET = os.environ["SESSION_SECRET"]  # 아무 랜덤 문자열이나 (쿠키 서명용)

COOKIE_NAME = "jarvis_session"
COOKIE_MAX_AGE = 60 * 60 * 24 * 90  # 90일 — 이 기간 동안은 다시 로그인 안 물어봄

serializer = URLSafeTimedSerializer(SESSION_SECRET)

app = FastAPI()
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


def _read_session(request: Request) -> str | None:
    token = request.cookies.get(COOKIE_NAME)
    if not token:
        return None
    try:
        return serializer.loads(token, max_age=COOKIE_MAX_AGE)
    except (BadSignature, SignatureExpired):
        return None


def _login_html(error: str = "") -> str:
    with open(os.path.join(STATIC_DIR, "login.html"), encoding="utf-8") as f:
        return f.read().replace("__ERROR__", error)


@app.get("/login")
def login_page():
    return HTMLResponse(_login_html())


@app.post("/login")
async def login_submit(request: Request):
    form = await request.form()
    username = form.get("username", "")
    password = form.get("password", "")

    if username == APP_USERNAME and password == APP_PASSWORD:
        token = serializer.dumps(username)
        resp = RedirectResponse(url="/", status_code=303)
        resp.set_cookie(
            COOKIE_NAME, token, max_age=COOKIE_MAX_AGE, httponly=True, samesite="lax"
        )
        return resp

    return HTMLResponse(_login_html(error="아이디 또는 비밀번호가 틀렸어요."), status_code=401)


@app.get("/logout")
def logout():
    resp = RedirectResponse(url="/login", status_code=303)
    resp.delete_cookie(COOKIE_NAME)
    return resp


@app.get("/")
def serve_index(request: Request):
    if not _read_session(request):
        return RedirectResponse(url="/login", status_code=303)
    return FileResponse(os.path.join(STATIC_DIR, "index.html"))


@app.get("/manifest.json")
def serve_manifest():
    # 크롬이 PWA 설치 가능 여부를 확인할 때 인증 없이 읽어야 해서 잠금 제외
    return FileResponse(os.path.join(STATIC_DIR, "manifest.json"))


@app.get("/sw.js")
def serve_sw():
    return FileResponse(os.path.join(STATIC_DIR, "sw.js"), media_type="application/javascript")


class ChatRequest(BaseModel):
    message: str
    session_id: str = "web-default"


@app.post("/api/chat")
def api_chat(req: ChatRequest, request: Request):
    if not _read_session(request):
        return JSONResponse({"error": "로그인이 필요해요."}, status_code=401)
    reply = ask_jarvis(req.session_id, req.message)
    return {"reply": reply}


@app.post("/api/reset")
def api_reset(req: ChatRequest, request: Request):
    if not _read_session(request):
        return JSONResponse({"error": "로그인이 필요해요."}, status_code=401)
    reset_memory(req.session_id)
    return {"ok": True}


MAX_UPLOAD_BYTES = 15 * 1024 * 1024  # 15MB — 무료 서버 메모리 보호용


@app.post("/api/chat-upload")
async def api_chat_upload(
    request: Request,
    message: str = Form(""),
    session_id: str = Form("web-default"),
    file: UploadFile = File(...),
):
    if not _read_session(request):
        return JSONResponse({"error": "로그인이 필요해요."}, status_code=401)

    file_bytes = await file.read()
    if len(file_bytes) > MAX_UPLOAD_BYTES:
        return JSONResponse({"error": "파일이 너무 커요 (15MB 이하만 가능해요)."}, status_code=413)

    content_type = file.content_type or ""

    try:
        if content_type.startswith("image/"):
            reply = ask_jarvis_with_image(session_id, message, file_bytes, content_type)
        else:
            text = extract_text(file_bytes, content_type, file.filename or "")
            reply = ask_jarvis_with_file(session_id, message, text, file.filename or "파일")
    except ValueError as e:
        return JSONResponse({"error": str(e)}, status_code=422)

    return {"reply": reply}


if __name__ == "__main__":
    import uvicorn

    port = int(os.environ.get("PORT", 8080))
    print(f"JARVIS 웹앱 시작 (포트 {port})...")
    uvicorn.run(app, host="0.0.0.0", port=port)
