import os
import json
from fastapi import FastAPI, Depends, HTTPException, Request, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import RedirectResponse, JSONResponse, HTMLResponse
from starlette.middleware.sessions import SessionMiddleware
from google_auth_oauthlib.flow import Flow
from google.oauth2.credentials import Credentials
import uvicorn
from dotenv import load_dotenv
from pydantic import BaseModel

from gmail_service import GmailService
from agent import GmailAgent

# 加载环境变量 / Load environment variables
load_dotenv()

# OAuth configuration
CLIENT_SECRETS_FILE = "backend/google_credentials.json"
# We only request gmail.readonly and gmail.modify, strictly NEVER request gmail.send.
# 我们只请求 gmail.readonly 和 gmail.modify，严格不申请 gmail.send。
SCOPES = [
    "https://www.googleapis.com/auth/gmail.readonly",
    "https://www.googleapis.com/auth/gmail.modify",
    "openid",
    "https://www.googleapis.com/auth/userinfo.email",
    "https://www.googleapis.com/auth/userinfo.profile"
]

app = FastAPI(title="Gmail Smart Cleaner API")

# 配置 CORS / Configure CORS
FRONTEND_URL = os.getenv("FRONTEND_URL", "http://localhost:5173")
app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_URL],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# 添加 Session 支持以临时存储 OAuth State / Add session support for storing OAuth state
SESSION_SECRET = os.getenv("SESSION_SECRET_KEY", "super-secret-random-key-change-in-production")
app.add_middleware(SessionMiddleware,
                   secret_key=SESSION_SECRET,
                   same_site="lax",
                   )

# 初始化全局 Agent
agent = GmailAgent()

def get_oauth_flow(request: Request) -> Flow:
    """
    初始化 Google OAuth Flow 实例
    """
    # 优先加载 backend/google_credentials.json 文件
    if os.path.exists(CLIENT_SECRETS_FILE):
        flow = Flow.from_client_secrets_file(
            CLIENT_SECRETS_FILE,
            scopes=SCOPES,
            redirect_uri=os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/api/auth/callback")
        )



    else:
        # 备选：通过环境变量单独指定
        client_id = os.getenv("GOOGLE_CLIENT_ID")
        client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
        redirect_uri = os.getenv("GOOGLE_REDIRECT_URI", "http://localhost:8000/api/auth/callback")

        if not client_id or not client_secret:
            raise HTTPException(
                status_code=500,
                detail="Google OAuth credentials are missing. Please provide backend/google_credentials.json or set GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET environment variables."
            )

        client_config = {
            "web": {
                "client_id": client_id,
                "client_secret": client_secret,
                "auth_uri": "https://accounts.google.com/o/oauth2/auth",
                "token_uri": "https://oauth2.google.com/token",
                "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
                "redirect_uris": [redirect_uri]
            }
        }
        flow = Flow.from_client_config(client_config, scopes=SCOPES, redirect_uri=redirect_uri)


    flow.oauth2session.client_kwargs = {"https_required": False}

    return flow


@app.get("/api/auth/login")
def login(request: Request):
    """
    触发 OAuth 登录，重定向至 Google 授权页面
    前端通过 window.location.href 直接导航到此端点，
    服务器返回 302 重定向到 Google 授权页面。
    """
    try:
        flow = get_oauth_flow(request)
        authorization_url, state = flow.authorization_url(
            access_type='offline',
            include_granted_scopes='true',
            prompt='consent'
        )
        # 将 state 写入 session，防止 CSRF
        request.session['state'] = state
        return RedirectResponse(authorization_url)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to generate authorization URL: {str(e)}")


@app.get("/api/auth/callback")
def callback(request: Request, response: Response):
    """
    OAuth 回调地址，换取 Token
    """
    print("🔥 callback 被调用了！")
    state = request.session.get('state')
    if not state or state != request.query_params.get('state'):
        raise HTTPException(status_code=400, detail="State mismatch. Possible CSRF attack.")
    
    try:
        flow = get_oauth_flow(request)

        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

        proxy_url = "http://127.0.0.1:7897"  # 替换成你的代理端口
        proxies = {"http": proxy_url, "https": proxy_url}

        flow.fetch_token(
            authorization_response=str(request.url),
            https_required=False,
            verify=False,  # 跳过 SSL 证书验证
            proxies=proxies  # 显式传入代理
        )

        credentials = flow.credentials
        # 用当前请求的 URL 换取 tokens 并且包含 state
        # 兼容 HTTP/HTTPS 状态下的 OAuth 验证
        flow.fetch_token(authorization_response=str(request.url),
                         )
        
        credentials = flow.credentials
        
        # 将 credentials 序列化为 JSON 字符串
        # 注意：credentials.scopes 是 frozenset 类型，必须转为 list 才能 JSON 序列化
        # Note: credentials.scopes is a frozenset, must convert to list for JSON serialization
        creds_data = {
            'token': credentials.token,
            'refresh_token': credentials.refresh_token,
            'token_uri': credentials.token_uri,
            'client_id': credentials.client_id,
            'client_secret': credentials.client_secret,
            'scopes': list(credentials.scopes) if credentials.scopes else []
        }
        
        # 将凭证存入加密的 Session 中，保持无状态化（不持久化在服务器）
        request.session['credentials'] = creds_data
        print("✅ Session 写入成功，creds_data 长度:", len(str(creds_data)))
        
        # 登录成功后直接 302 重定向回前端首页
        # 使用 Vite 代理后，cookie 在同域下生效，无需 HTMLResponse 中转
        return RedirectResponse(FRONTEND_URL)
    except Exception as e:
        # 失败时重定向回前端首页，附带错误信息（通过 query 参数）
        print("❌ callback 出错:", str(e))
        return RedirectResponse(f"{FRONTEND_URL}?login_error={str(e)}")


@app.get("/api/auth/user")
def get_user_status(request: Request):
    """
    获取当前用户登录状态
    """
    print("🔍 Session 内容:", request.session)
    creds_data = request.session.get('credentials')
    if not creds_data:
        return JSONResponse(status_code=401, content={"logged_in": False})
    
    # 返回部分安全的信息以确认已登录
    return {
        "logged_in": True,
        "scopes": creds_data.get("scopes", []),
        "has_refresh_token": bool(creds_data.get("refresh_token"))
    }


@app.post("/api/auth/logout")
def logout(request: Request):
    """
    登出并清除 Session 缓存
    """
    request.session.clear()
    return {"status": "success", "message": "Logged out successfully"}


@app.get("/api/emails/list")
def get_emails(request: Request):
    """
    安全读取最近 7 天的未读邮件（最多 50 封），并使用 Gemini Agent 进行分类和简短的中文摘要
    数据仅在此请求的内存中处理，不存储于日志或数据库，保障用户隐私
    """
    creds_data = request.session.get('credentials')
    if not creds_data:
        raise HTTPException(status_code=401, detail="Not authenticated. Please log in.")
        
    try:
        gmail_service = GmailService(creds_data)
        # 获取最近 7 天内的最多 50 封未读邮件
        unread_emails = gmail_service.get_unread_emails(max_results=50, days_ago=7)
        
        if not unread_emails:
            return {"emails": []}
            
        # 调用 Gemini Agent 进行结构化分析（中文摘要 + 自动分类）
        analyzed_emails = agent.analyze_emails(unread_emails)
        return {"emails": analyzed_emails}
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to fetch and analyze emails: {str(e)}")


class BatchActionRequest(BaseModel):
    action: str  # "mark_read" | "archive" | "delete"
    msg_ids: list


@app.post("/api/emails/action")
def email_action(request: Request, body: BatchActionRequest):
    """
    对选定邮件进行批量动作，如一键已读、一键归档或一键垃圾桶
    """
    creds_data = request.session.get('credentials')
    if not creds_data:
        raise HTTPException(status_code=401, detail="Not authenticated. Please log in.")
        
    try:
        gmail_service = GmailService(creds_data)
        result = gmail_service.execute_batch_action(body.action, body.msg_ids)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Failed to execute batch action: {str(e)}")


@app.get("/api/health")
def health_check():
    return {"status": "ok", "service": "Gmail Smart Cleaner Backend"}


if __name__ == "__main__":
    uvicorn.run("main:app", host="127.0.0.1", port=8000, reload=True)

