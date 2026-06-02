"""模块导读：本文件位于 app/api/routers/users.py，属于API 路由层。

主要职责：把 HTTP 请求转换成服务层调用，并把结果整理成前端可以直接使用的响应。
阅读建议：先看模块顶部导入，理解它依赖哪些服务或外部组件；再看公开类和函数，顺着调用链理解数据如何流转。"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.time_utils import to_shanghai_iso
from app.domain.models import User, UserAuditLog
from app.services.common import page, success
from app.services.dependencies import require_admin
from app.services.security import hash_password

router = APIRouter(tags=["users"])
ALLOWED_USER_ROLES = {"admin", "user"}


class UserPayload(BaseModel):
    """UserPayload 请求模型：描述前端提交到接口的字段，FastAPI 会用它完成参数校验和类型转换。"""
    username: str
    nickname: str = ""
    password: str | None = None
    role: str = "user"
    is_active: bool = True


def _validate_user_role(role: str) -> None:
    """校验用户角色，避免写入未知权限值。"""

    if role not in ALLOWED_USER_ROLES:
        raise HTTPException(status_code=400, detail="用户角色不合法")


def _has_other_active_admin(db: Session, user_id: str) -> bool:
    """判断目标用户之外是否还存在其它活跃管理员。"""

    return (
        db.query(User)
        .filter(
            User.id != user_id,
            User.role == "admin",
            User.is_active.is_(True),
        )
        .first()
        is not None
    )


def _ensure_last_admin_not_removed(db: Session, row: User, next_role: str, next_active: bool) -> None:
    """禁止把系统最后一个活跃管理员删除、禁用或降级。"""

    if row.role == "admin" and row.is_active and (next_role != "admin" or not next_active):
        if not _has_other_active_admin(db, row.id):
            raise HTTPException(status_code=400, detail="不能禁用或降级最后一个活跃管理员")


def _user_audit_snapshot(row: User, password_changed: bool = False) -> dict:
    """生成用户审计快照，不包含密码明文或哈希。"""

    return {
        "username": row.username,
        "nickname": row.nickname,
        "role": row.role,
        "isActive": row.is_active,
        "passwordChanged": password_changed,
    }


def _add_user_audit_log(
    db: Session,
    action: str,
    target: User,
    old_value: dict,
    new_value: dict,
    operator: User,
) -> None:
    """写入用户管理审计日志，供后台追溯高风险操作。"""

    db.add(
        UserAuditLog(
            action=action,
            target_user_id=target.id,
            target_username=target.username,
            old_value=old_value,
            new_value=new_value,
            changed_by=operator.id,
        )
    )


def _serialize_user_audit_log(row: UserAuditLog) -> dict:
    """把用户审计 ORM 记录转换为前端友好的字段。"""

    return {
        "id": row.id,
        "action": row.action,
        "targetUserId": row.target_user_id,
        "targetUsername": row.target_username,
        "oldValue": row.old_value or {},
        "newValue": row.new_value or {},
        "changedBy": row.changed_by,
        "createdAt": to_shanghai_iso(row.created_at),
    }


@router.get("/users")
def list_users(
    pageNo: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1),
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """list_users 函数：查询一组数据并整理成列表或分页结果，通常直接服务于前端列表页。"""
    query = db.query(User).order_by(User.created_at.desc())
    total = query.count()
    rows = query.offset((pageNo - 1) * pageSize).limit(pageSize).all()
    items = [
        {
            "id": row.id,
            "username": row.username,
            "nickname": row.nickname,
            "role": row.role,
            "isActive": row.is_active,
        }
        for row in rows
    ]
    return success(page(items, total, pageNo, pageSize))


@router.post("/users")
def create_user(payload: UserPayload, db: Session = Depends(get_db), operator: User = Depends(require_admin)):
    """create_user 函数：创建新的业务记录，负责组织入库字段并返回创建后的结果。"""
    _validate_user_role(payload.role)
    if not payload.password:
        raise HTTPException(status_code=400, detail="创建用户必须设置初始密码")
    if db.query(User).filter(User.username == payload.username).first():
        raise HTTPException(status_code=400, detail="用户名已存在")
    row = User(
        username=payload.username,
        nickname=payload.nickname,
        password_hash=hash_password(payload.password),
        role=payload.role,
        is_active=payload.is_active,
    )
    db.add(row)
    db.flush()
    _add_user_audit_log(db, "create", row, {}, _user_audit_snapshot(row, password_changed=True), operator)
    db.commit()
    db.refresh(row)
    return success({"id": row.id})


@router.get("/users/audit")
def list_user_audit_logs(
    pageNo: int = Query(1, ge=1),
    pageSize: int = Query(20, ge=1, le=100),
    targetUserId: str | None = None,
    action: str | None = None,
    db: Session = Depends(get_db),
    _: User = Depends(require_admin),
):
    """分页查询后台用户管理审计日志。"""

    query = db.query(UserAuditLog)
    if targetUserId:
        query = query.filter(UserAuditLog.target_user_id == targetUserId)
    if action:
        query = query.filter(UserAuditLog.action == action)
    total = query.count()
    rows = (
        query.order_by(UserAuditLog.created_at.desc(), UserAuditLog.id.desc())
        .offset((pageNo - 1) * pageSize)
        .limit(pageSize)
        .all()
    )
    return success(page([_serialize_user_audit_log(row) for row in rows], total, pageNo, pageSize))


@router.put("/users/{user_id}")
def update_user(user_id: str, payload: UserPayload, db: Session = Depends(get_db), operator: User = Depends(require_admin)):
    """update_user 函数：更新已有业务记录，只修改调用方明确传入的字段。"""
    _validate_user_role(payload.role)
    row = db.query(User).filter(User.id == user_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="用户不存在")
    _ensure_last_admin_not_removed(db, row, payload.role, payload.is_active)
    old_value = _user_audit_snapshot(row)
    password_changed = bool(payload.password)
    row.nickname = payload.nickname
    row.role = payload.role
    row.is_active = payload.is_active
    if payload.password:
        row.password_hash = hash_password(payload.password)
    _add_user_audit_log(db, "update", row, old_value, _user_audit_snapshot(row, password_changed), operator)
    db.commit()
    return success({"id": row.id})


@router.delete("/users/{user_id}")
def delete_user(user_id: str, db: Session = Depends(get_db), operator: User = Depends(require_admin)):
    """delete_user 函数：删除业务记录，并在需要时同步清理关联资源或缓存。"""
    row = db.query(User).filter(User.id == user_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="用户不存在")
    _ensure_last_admin_not_removed(db, row, "deleted", False)
    old_value = _user_audit_snapshot(row)
    _add_user_audit_log(db, "delete", row, old_value, {}, operator)
    db.delete(row)
    db.commit()
    return success()
