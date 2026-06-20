"""SQLAlchemy ORM 模型定义 - ORM 3.0 分层配置架构
包含四大物理层：凭证层、资产层、策略层、编排层 (已整合)
"""
from __future__ import annotations
from datetime import datetime, timezone
from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Integer, JSON, String, Text, Index
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column, relationship


class Base(DeclarativeBase):
    pass


class Tenant(Base):
    """租户 - 多租户隔离的根实体"""
    __tablename__ = "tenants"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True, unique=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    
    # 级联删除
    users: Mapped[list[User]] = relationship("User", back_populates="tenant", cascade="all, delete-orphan")
    providers: Mapped[list[UserProvider]] = relationship("UserProvider", back_populates="tenant", cascade="all, delete-orphan")
    model_assets: Mapped[list[UserModelAsset]] = relationship("UserModelAsset", back_populates="tenant", cascade="all, delete-orphan")
    presets: Mapped[list[ResearchPreset]] = relationship("ResearchPreset", back_populates="tenant", cascade="all, delete-orphan")
    sessions: Mapped[list[ResearchSession]] = relationship("ResearchSession", back_populates="tenant", cascade="all, delete-orphan")


class User(Base):
    """用户"""
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    email: Mapped[str] = mapped_column(String(255), nullable=False, unique=True, index=True)
    full_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    avatar_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    hashed_password: Mapped[str | None] = mapped_column(String(255), nullable=True)
    role: Mapped[str] = mapped_column(String(20), default="user", index=True)
    external_id: Mapped[str | None] = mapped_column(String(255), nullable=True, index=True)
    tenant_id: Mapped[str | None] = mapped_column(
        String(36), 
        ForeignKey("tenants.id", ondelete="CASCADE"), 
        nullable=True, 
        index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    
    tenant: Mapped[Tenant | None] = relationship("Tenant", back_populates="users")
    
    # 级联删除：删除用户时，自动清理属于该用户的所有配置与记录
    researches: Mapped[list[ResearchSession]] = relationship("ResearchSession", back_populates="user", cascade="all, delete-orphan")
    providers: Mapped[list[UserProvider]] = relationship("UserProvider", back_populates="user", cascade="all, delete-orphan")
    model_assets: Mapped[list[UserModelAsset]] = relationship("UserModelAsset", back_populates="user", cascade="all, delete-orphan")
    presets: Mapped[list[ResearchPreset]] = relationship("ResearchPreset", back_populates="user", cascade="all, delete-orphan")


class UserProvider(Base):
    """1. 凭证层 - 供应商连接信息"""
    __tablename__ = "user_providers"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    tenant_id: Mapped[str] = mapped_column(String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=False, index=True)
    
    category: Mapped[str] = mapped_column(String(50), nullable=False)           # "llm" / "search"
    provider_name: Mapped[str] = mapped_column(String(50), nullable=False)      # e.g., "openai", "tavily"
    encrypted_key: Mapped[str] = mapped_column(Text, nullable=False)
    base_url: Mapped[str | None] = mapped_column(String(500), nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc))

    user: Mapped[User] = relationship("User", back_populates="providers")
    tenant: Mapped[Tenant] = relationship("Tenant", back_populates="providers")
    assets: Mapped[list[UserModelAsset]] = relationship("UserModelAsset", back_populates="provider", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_user_providers_user_cat_name", "user_id", "category", "provider_name", unique=True),
    )


class UserModelAsset(Base):
    """2. 资产层 - 用户或系统注册的可选模型"""
    __tablename__ = "user_model_assets"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    tenant_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True)
    
    provider_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("user_providers.id", ondelete="CASCADE"), nullable=True)
    provider_name: Mapped[str] = mapped_column(String(50), nullable=False)      # e.g., "openai" (冗余存储方便查询)
    model_name: Mapped[str] = mapped_column(String(100), nullable=False)       # e.g., "gpt-4o"
    display_name: Mapped[str | None] = mapped_column(String(255), nullable=True)
    capabilities: Mapped[list | None] = mapped_column(JSON, nullable=True)     # e.g., ["vision", "tool_call"]
    
    is_system_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    
    user: Mapped[User | None] = relationship("User", back_populates="model_assets")
    tenant: Mapped[Tenant | None] = relationship("Tenant", back_populates="model_assets")
    provider: Mapped[UserProvider | None] = relationship("UserProvider", back_populates="assets")

    __table_args__ = (
        # 系统默认模型全局唯一，用户自定义模型按用户唯一
        Index("ix_model_assets_user_prov_model", "user_id", "provider_name", "model_name", unique=True),
    )


class ResearchPreset(Base):
    """3. 策略层 - 研究风格与全局业务参数蓝图 (已整合编排层配置)"""
    __tablename__ = "research_presets"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    tenant_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("tenants.id", ondelete="CASCADE"), nullable=True, index=True)
    
    name: Mapped[str] = mapped_column(String(50), nullable=False)               # e.g., "消费决策"
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # 核心配置：存储所有节点的执行配置
    # 结构示例: {"stages": {"understanding": {"asset_id": "...", "temperature": 0.1}, ...}, "business": {...}}
    nodes_config: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    
    is_system_default: Mapped[bool] = mapped_column(Boolean, default=False)
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)           # 是否为该用户的默认预设
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)             # 用户是否在 UI 中启用了该预设
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))

    user: Mapped[User | None] = relationship("User", back_populates="presets")
    tenant: Mapped[Tenant | None] = relationship("Tenant", back_populates="presets")
    sessions: Mapped[list[ResearchSession]] = relationship("ResearchSession", back_populates="preset")


class ResearchSession(Base):
    """研究会话 (容器级) - 对应 LangGraph 的 thread_id
    管理整个聊天的生命周期、参与者及全局配置
    """
    __tablename__ = "research_sessions"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)          # thread_id
    user_id: Mapped[str | None] = mapped_column(
        String(36), 
        ForeignKey("users.id", ondelete="CASCADE"), 
        nullable=True, 
        index=True
    )
    tenant_id: Mapped[str | None] = mapped_column(
        String(36), 
        ForeignKey("tenants.id", ondelete="CASCADE"), 
        nullable=True, 
        index=True
    )
    
    # 会话元数据
    title: Mapped[str | None] = mapped_column(Text, nullable=True)          # 会话标题 (默认取第一次提问)
    preset_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("research_presets.id", ondelete="SET NULL"), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True) # active, archived
    total_duration_seconds: Mapped[int] = mapped_column(Integer, default=0) # 整个会话的总研究时长汇总
    
    # 时间戳
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), index=True)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), 
        default=lambda: datetime.now(timezone.utc), 
        onupdate=lambda: datetime.now(timezone.utc)
    )

    user: Mapped[User | None] = relationship("User", back_populates="researches")
    tenant: Mapped[Tenant | None] = relationship("Tenant", back_populates="sessions")
    preset: Mapped[ResearchPreset | None] = relationship("ResearchPreset", back_populates="sessions")
    tasks: Mapped[list[ResearchTask]] = relationship("ResearchTask", back_populates="session", cascade="all, delete-orphan", order_by="ResearchTask.ordinal")


    __table_args__ = (
        Index("ix_research_sessions_user_created", "user_id", "created_at"),
    )


class ResearchTask(Base):
    """研究任务 (交互级) - 承载单次研究的输入与产出
    包括初始研究和所有的 Follow-up
    """
    __tablename__ = "research_tasks"
    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    session_id: Mapped[str] = mapped_column(
        String(36), 
        ForeignKey("research_sessions.id", ondelete="CASCADE"), 
        nullable=False, 
        index=True
    )
    ordinal: Mapped[int] = mapped_column(Integer, default=0, index=True)    # 线性序号 (0, 1, 2...)
    
    # 输入与配置快照
    query: Mapped[Text] = mapped_column(Text, nullable=False)
    intent_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    run_config_snapshot: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    
    # LLM 生成的结构化研究结论摘要 (归档时写入, 用于追问上下文投喂)
    research_conclusion: Mapped[str | None] = mapped_column(Text, nullable=True)
    
    # 任务状态
    status: Mapped[str] = mapped_column(String(20), default="running", index=True) # running, completed, failed
    pending_approval: Mapped[bool] = mapped_column(Boolean, default=False)  # 是否正在等待用户确认 (v3.0)
    breakpoint_type: Mapped[str | None] = mapped_column(String(20), nullable=True) # dimensions, sources (v3.0)

    # 研究产出与指标 (从原 Research 表迁移而来)
    summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    dimensions: Mapped[list | None] = mapped_column(JSON, nullable=True)
    claims: Mapped[list | None] = mapped_column(JSON, nullable=True)
    sources: Mapped[list | None] = mapped_column(JSON, nullable=True)        # 结构化源信息
    thought_steps: Mapped[list | None] = mapped_column(JSON, nullable=True)
    
    # 统计指标
    claims_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    verified_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    overall_confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    source_count: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_seconds: Mapped[int | None] = mapped_column(Integer, nullable=True)
    warnings: Mapped[list | None] = mapped_column(JSON, nullable=True)
    error_log: Mapped[list | None] = mapped_column(JSON, nullable=True)

    # 时间戳
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(timezone.utc))
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), default=lambda: datetime.now(timezone.utc), onupdate=lambda: datetime.now(timezone.utc)
    )
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)

    session: Mapped[ResearchSession] = relationship("ResearchSession", back_populates="tasks")

