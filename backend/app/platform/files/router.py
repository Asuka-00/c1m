"""文件上传接口（品牌图片等）。归属为平台（tenant_id 为空）或租户；文件按 id 公开访问，以便登录页渲染品牌。"""

import uuid
from datetime import timedelta
from typing import Annotated, Any, Literal

from fastapi import APIRouter, File, Header, HTTPException, Query, UploadFile
from fastapi.responses import FileResponse

from app.core import error_codes as ec
from app.core.config import settings
from app.core.deps import SessionDep
from app.core.models import Message
from app.core.spec.errors import coded
from app.platform.auth.deps import CurrentUser, TokenPayloadDep, get_current_tenant
from app.platform.files.models import UploadedFile
from app.platform.files.schemas import FileUploadPublic
from app.platform.files.service import cleanup_unreferenced, upload_dir
from app.platform.rbac.service import has_permissions

router = APIRouter(prefix="/files", tags=["files"])

# 允许的上传类型 -> 存储扩展名
IMAGE_TYPES = {
    "image/png": ".png",
    "image/jpeg": ".jpg",
    "image/svg+xml": ".svg",
    "image/webp": ".webp",
    "image/x-icon": ".ico",
    "image/vnd.microsoft.icon": ".ico",
}
CHUNK = 64 * 1024


@router.post("/upload", response_model=FileUploadPublic)
async def upload_file(
    session: SessionDep,
    current_user: CurrentUser,
    token_data: TokenPayloadDep,
    file: Annotated[UploadFile, File()],
    scope: Annotated[Literal["tenant", "platform"], Query()] = "tenant",
    x_tenant_id: Annotated[uuid.UUID | None, Header()] = None,
) -> Any:
    """Upload an image (png/jpg/svg/webp/ico, max MAX_UPLOAD_BYTES).
    scope=tenant (default): owned by the current tenant, needs tenant config:write.
    scope=platform: platform-owned, needs platform config:write."""
    tenant_id: uuid.UUID | None = None
    if scope == "platform":
        if not has_permissions(current_user, "config:write"):
            raise coded(403, ec.PERMISSION_DENIED, "Not enough permissions")
    else:
        ctx = get_current_tenant(session, current_user, token_data, x_tenant_id)
        if not ctx.can("config:write"):
            raise coded(403, ec.PERMISSION_DENIED, "Not enough permissions")
        tenant_id = ctx.id
    ext = IMAGE_TYPES.get((file.content_type or "").lower())
    if not ext:
        raise coded(415, ec.UNSUPPORTED_FILE_TYPE, "Unsupported file type")
    fid = uuid.uuid4()
    stored = f"{fid.hex}{ext}"
    dest = upload_dir() / stored
    size = 0
    try:
        with dest.open("wb") as out:
            while chunk := await file.read(CHUNK):
                size += len(chunk)
                if size > settings.MAX_UPLOAD_BYTES:
                    raise coded(413, ec.FILE_TOO_LARGE, "File too large")
                out.write(chunk)
    except HTTPException:
        dest.unlink(missing_ok=True)
        raise
    if size == 0:
        dest.unlink(missing_ok=True)
        raise coded(400, ec.EMPTY_FILE, "Empty file")
    rec = UploadedFile(
        id=fid,
        tenant_id=tenant_id,
        uploaded_by=current_user.id,
        filename=(file.filename or stored)[:255],
        stored_name=stored,
        content_type=file.content_type or "application/octet-stream",
        size=size,
    )
    session.add(rec)
    session.commit()
    return FileUploadPublic(
        id=fid,
        url=f"{settings.API_V1_STR}/files/{fid}",
        filename=rec.filename,
        content_type=rec.content_type,
        size=size,
        tenant_id=tenant_id,
    )


@router.post("/cleanup", response_model=Message)
def cleanup_files(
    session: SessionDep,
    current_user: CurrentUser,
    older_than_hours: Annotated[float, Query(ge=1)] = 24,
    dry_run: bool = False,
) -> Any:
    """Platform admins: delete uploads no config references, older than the grace
    period (default 24h, min 1h so in-progress uploads survive)."""
    if not has_permissions(current_user, "config:write"):
        raise coded(403, ec.PERMISSION_DENIED, "Not enough permissions")
    victims = cleanup_unreferenced(
        session, timedelta(hours=older_than_hours), dry_run=dry_run
    )
    verb = "Would delete" if dry_run else "Deleted"
    return Message(message=f"{verb} {len(victims)} unreferenced file(s)")


@router.get("/{file_id}")
def get_file(session: SessionDep, file_id: uuid.UUID) -> FileResponse:
    """Public download (branding assets). SVGs are sent with a CSP sandbox."""
    rec = session.get(UploadedFile, file_id)
    path = upload_dir() / rec.stored_name if rec else None
    if not rec or not path or not path.is_file():
        raise coded(404, ec.FILE_NOT_FOUND, "File not found")
    return FileResponse(
        path,
        media_type=rec.content_type,
        headers={
            "Cache-Control": "public, max-age=86400, immutable",
            "Content-Security-Policy": "default-src 'none'; style-src 'unsafe-inline'; sandbox",
            "X-Content-Type-Options": "nosniff",
        },
    )
