"""
认证服务模块 (Authentication Service Module)

该模块提供用户认证相关的核心功能,包括:
1. 默认管理员账户的创建和管理
2. 用户登录验证和 JWT token 生成
3. 用户登出和 token 撤销
4. token 有效性验证

安全特性:
- 密码加密存储(使用bcrypt)
- JWT token 验证
- token 撤销机制(防止已登出的 token 被重用)

依赖模块:
- security.py: 密码哈希和 token 生成
- models.py: User 和 RevokedToken 模型
- config.py: 默认管理员配置
"""
from __future__ import annotations

from datetime import datetime

from sqlalchemy.orm import Session

from config import settings
from models import RevokedToken, User
from services.security import create_token, hash_password, verify_password


def ensure_default_admin(db: Session) -> None:
    """
    确保系统中存在默认管理员账户
    
    如果数据库中不存在默认管理员账户,则创建一个。
    该函数通常在应用启动时调用,以确保至少有一个管理员账户可用。
    
    Args:
        db: SQLAlchemy 数据库会话对象,用于查询和操作用户数据
        
    Returns:
        None
        
    Note:
        - 如果已存在同名管理员账户,则直接返回,不做任何操作
        - 新创建的管理员账户使用配置文件中的默认凭据
        - 密码会通过 bcrypt 进行哈希加密后存储
    """
    admin = db.query(User).filter(User.username == settings.DEFAULT_ADMIN_USERNAME).first()
    if admin:
        return
    db.add(
        User(
            username=settings.DEFAULT_ADMIN_USERNAME,
            nickname=settings.DEFAULT_ADMIN_NICKNAME,
            password_hash=hash_password(settings.DEFAULT_ADMIN_PASSWORD),
            role="admin",
            is_active=True,
        )
    )
    db.commit()


def login(db: Session, username: str, password: str) -> dict:
    """
    用户登录验证并生成 JWT token
    
    验证用户名和密码的正确性,检查账户是否处于激活状态。
    验证通过后生成包含用户信息的 JWT token。
    
    Args:
        db: SQLAlchemy 数据库会话对象,用于查询用户信息
        username: 用户登录名,用于身份验证
        password: 用户密码,明文形式,会与数据库中存储的哈希值进行比对
        
    Returns:
        dict: 包含以下键值的字典:
            - token (str): JWT 访问令牌,用于后续请求的身份验证
            - user (dict): 用户信息字典,包含:
                - id: 用户唯一标识符
                - username: 用户名
                - nickname: 用户昵称
                - role: 用户角色(如 admin, user 等)
                
    Raises:
        ValueError: 当用户名不存在、密码错误或账户未激活时抛出,
                   错误信息为"用户名或密码错误"
                   
    Security:
        - 密码验证使用 bcrypt 算法进行安全比对
        - Token  payload 包含用户 ID、用户名和角色信息
        - 不返回敏感信息如密码哈希值
    """
    user = db.query(User).filter(User.username == username).first()
    if not user or not verify_password(password, user.password_hash) or not user.is_active:
        raise ValueError("用户名或密码错误")
    token = create_token({"sub": user.id, "username": user.username, "role": user.role})
    return {
        "token": token,
        "user": {
            "id": user.id,
            "username": user.username,
            "nickname": user.nickname,
            "role": user.role,
        },
    }


def logout(db: Session, token_payload: dict) -> None:
    """
    用户登出并将当前 token 加入撤销列表
    
    将用户的 JWT token 添加到撤销列表中,使其失效。
    即使 token 尚未过期,被撤销的 token 也无法再通过验证。
    
    Args:
        db: SQLAlchemy 数据库会话对象,用于保存撤销的 token 记录
        token_payload: JWT token 的解析后的载荷字典,必须包含:
            - jti (str): JWT ID,token 的唯一标识符
            - exp (int/float): token 的过期时间戳(Unix timestamp)
            
    Returns:
        None
        
    Note:
        - 撤销记录会保存到数据库的 revoked_tokens 表中
        - 记录的过期时间与原 token 保持一致,便于定期清理过期记录
        - 这是实现 token 即时失效的关键机制
    """
    db.add(
        RevokedToken(
            token_id=token_payload["jti"],
            expires_at=datetime.utcfromtimestamp(token_payload["exp"]),
        )
    )
    db.commit()


def is_token_revoked(db: Session, token_payload: dict) -> bool:
    """
    检查 token 是否已被撤销
    
    查询数据库中的撤销列表,判断指定的 token 是否已被用户主动登出或系统撤销。
    
    Args:
        db: SQLAlchemy 数据库会话对象,用于查询撤销的 token 记录
        token_payload: JWT token 的解析后的载荷字典,必须包含:
            - jti (str): JWT ID,token 的唯一标识符
            
    Returns:
        bool: token 的撤销状态
            - True: token 已被撤销,不应再被接受
            - False: token 未被撤销,可以继续使用(仍需验证其他条件如过期时间)
            
    Usage:
        通常在 JWT 中间件或装饰器中调用此函数,在验证 token 签名和过期时间后,
        进一步检查 token 是否已被撤销,以实现完整的 token 验证流程。
    """
    token = db.query(RevokedToken).filter(RevokedToken.token_id == token_payload["jti"]).first()
    return token is not None

