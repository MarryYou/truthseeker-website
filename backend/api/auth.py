"""API Router for authentication and identity management using official Logto SDK."""
from __future__ import annotations
import os
from typing import cast, Any
from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import RedirectResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from logto import LogtoClient, LogtoConfig

from backend.db.engine import get_db
from backend.db import crud
from backend.core.config import (
    LOGTO_ENDPOINT,
    LOGTO_CLIENT_ID,
    LOGTO_CLIENT_SECRET,
    LOGTO_API_RESOURCE,
    FRONTEND_URL
)
from backend.core.session import SessionManager, LogtoRedisStorage
from backend.core.logging import logger

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])

# 配置常量
COOKIE_NAME = "ts_session"
TEMP_AUTH_SESSION_COOKIE = "ts_auth_sid"
REDIRECT_URI = os.getenv("LOGTO_REDIRECT_URI", f"{FRONTEND_URL.rstrip('/')}/api/v1/auth/callback")
POST_LOGOUT_REDIRECT_URI = os.getenv("LOGTO_POST_LOGOUT_REDIRECT_URI", FRONTEND_URL)
LOGTO_SCOPES = ["openid", "profile", "email", "roles"]

class UserUpdate(BaseModel):
    name: str | None = None
    avatar: str | None = None

async def get_logto_client(request: Request):
    """依赖项：初始化 Logto 客户端"""
    # 尝试获取现有 Session ID，如果没有则为登录流程创建一个临时的
    session_id = request.cookies.get(COOKIE_NAME) or request.cookies.get(TEMP_AUTH_SESSION_COOKIE)
    cookie_source = "COOKIE_NAME" if request.cookies.get(COOKIE_NAME) else ("TEMP_COOKIE" if request.cookies.get(TEMP_AUTH_SESSION_COOKIE) else "NEW")
    
    if not session_id:
        session_id = SessionManager.generate_session_id()
    
    logger.debug("Logto Client Init | session_id={} | source={} | path={}", session_id, cookie_source, request.url.path)
    
    storage = LogtoRedisStorage(session_id)
    config = LogtoConfig(
        endpoint=LOGTO_ENDPOINT,
        appId=LOGTO_CLIENT_ID,
        appSecret=LOGTO_CLIENT_SECRET,
        resources=[LOGTO_API_RESOURCE] if LOGTO_API_RESOURCE else [],
        scopes=cast(Any, LOGTO_SCOPES)
    )
    return LogtoClient(config, storage), session_id

async def get_current_user(request: Request) -> dict:
    """依赖项：获取当前登录用户信息"""
    session_id = request.cookies.get(COOKIE_NAME)
    if not session_id:
        raise HTTPException(status_code=401, detail="Not authenticated")
    
    session_data = await SessionManager.get_session(session_id)
    if not session_data:
        raise HTTPException(status_code=401, detail="Session expired")
    
    return session_data

def RequireRole(role: str):
    async def role_checker(user_ctx: dict = Depends(get_current_user)):
        if user_ctx.get("role") != role:
            raise HTTPException(status_code=403, detail="Permission denied")
        return user_ctx
    return role_checker

@router.get("/login")
async def login(client_data: tuple = Depends(get_logto_client)):
    client, session_id = client_data
    # 调用官方 SDK 的 signIn 方法
    login_url = await client.signIn(redirectUri=REDIRECT_URI)
    
    response = RedirectResponse(login_url)
    # 存入临时 Cookie 以便在 callback 中找回 Logto 存储状态
    response.set_cookie(
        TEMP_AUTH_SESSION_COOKIE, 
        session_id, 
        httponly=True, 
        max_age=600, 
        path="/",
        samesite="lax"
    )
    return response

@router.get("/callback")
async def callback(
    request: Request,
    db: AsyncSession = Depends(get_db),
    client_data: tuple = Depends(get_logto_client)
):
    client, session_id = client_data
    try:
        # 调用官方 SDK 处理回调 (内部包含 state 校验和 token 交换)
        await client.handleSignInCallback(str(request.url))
        
        # 获取用户信息
        user_info = await client.fetchUserInfo()
        if not user_info:
            raise HTTPException(status_code=401, detail="Failed to fetch user info")

        # 同步数据
        external_id = user_info.sub
        email = user_info.email or f"{external_id[:8]}@logto.user"
        
        # 从自定义声明中提取角色 (假设 Logto 在 roles 字段返回)
        # 注意：SDK 的 fetchUserInfo 返回的是一个对象，声明在 .custom_data 或直接属性中
        # 实际上官方 SDK 会将额外声明放在额外的属性中
        roles = getattr(user_info, "roles", [])
        primary_role = "admin" if "admin" in roles else ("user" if roles else "user")

        stmt = select(crud.User).where(crud.User.external_id == external_id)
        user = (await db.execute(stmt)).scalar_one_or_none()
        
        if not user:
            tenant = await crud.get_or_create_tenant(db, external_id=f"tenant-{external_id[:8]}")
            user = await crud.create_user(
                db=db, email=email, external_id=external_id,
                tenant_id=tenant.id, full_name=user_info.name,
                avatar_url=user_info.picture, role=primary_role
            )
        else:
            user.role = primary_role
            if user_info.name:
                user.full_name = user_info.name
            if user_info.picture:
                user.avatar_url = user_info.picture
        
        await db.commit()
        await db.refresh(user)

        # 转化临时 Session 为正式 Session
        await SessionManager.create_session(user.id, user.role, user.tenant_id, session_id=session_id)

        response = RedirectResponse(FRONTEND_URL)
        response.set_cookie(
            COOKIE_NAME, 
            session_id, 
            httponly=True, 
            max_age=SessionManager.SESSION_EXPIRE_SECONDS, 
            path="/",
            samesite="lax"
        )
        response.delete_cookie(TEMP_AUTH_SESSION_COOKIE, path="/")
        return response

    except Exception as e:
        logger.error("Authentication failed: {}", e)
        raise HTTPException(status_code=401, detail=f"Authentication failed: {str(e)}") from e

@router.get("/logout")
async def logout(client_data: tuple = Depends(get_logto_client)):
    client, session_id = client_data
    await SessionManager.delete_session(session_id)
    
    # 调用官方 SDK 的 signOut 方法
    logout_url = await client.signOut(postLogoutRedirectUri=POST_LOGOUT_REDIRECT_URI)
    
    response = RedirectResponse(logout_url)
    response.delete_cookie(COOKIE_NAME, path="/")
    return response

@router.get("/me")
async def get_me(user_ctx: dict = Depends(get_current_user), db: AsyncSession = Depends(get_db)):
    user = await crud.get_user(db, user_id=user_ctx["user_id"])
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在，请重新登录")
    return {
        "id": user.id, "email": user.email, "role": user.role,
        "name": user.full_name, "avatar": user.avatar_url,
        "tenant_id": user.tenant_id
    }

@router.put("/me")
async def update_me(
    data: UserUpdate,
    user_ctx: dict = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    user = await crud.get_user(db, user_id=user_ctx["user_id"])
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if data.name is not None:
        user.full_name = data.name
    if data.avatar is not None:
        user.avatar_url = data.avatar
    await db.commit()
    return {"message": "Profile updated success"}
