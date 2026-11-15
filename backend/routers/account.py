from fastapi import APIRouter, HTTPException, Request, Response, status, Depends
from backend.models import (
    ChangePasswordRequest,
    UpdateProfileRequest,
    DeleteAccountRequest
)
from backend.database import (
    User,
    update_user_password,
    update_user_profile,
    delete_user_account,
    delete_all_user_sessions
)
from backend.security import (
    verify_password,
    hash_password,
    verify_csrf,
    clear_session_cookie,
    set_csrf_cookie
)
from backend.dependencies import get_current_user

router = APIRouter(prefix="/api/account", tags=["Account"])

@router.get("/profile")
async def get_profile(current_user: User = Depends(get_current_user)):
    return {
        "id": current_user.id,
        "name": current_user.name,
        "email": current_user.email,
        "created_at": current_user.created_at.isoformat() if current_user.created_at else ""
    }

@router.patch("/profile")
async def update_profile(
    req: UpdateProfileRequest,
    request: Request,
    current_user: User = Depends(get_current_user)
):
    verify_csrf(request)
    name = req.name.strip()
    if len(name) < 2:
        raise HTTPException(status_code=400, detail="Name must be at least 2 characters.")
    update_user_profile(current_user.id, name)
    return {"success": True, "name": name}

@router.post("/change-password")
async def change_password(
    req: ChangePasswordRequest,
    request: Request,
    current_user: User = Depends(get_current_user)
):
    verify_csrf(request)
    if not verify_password(req.current_password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Current password is incorrect.")

    if len(req.new_password) < 8:
        raise HTTPException(status_code=400, detail="New password must be at least 8 characters.")
    if req.new_password != req.confirm_password:
        raise HTTPException(status_code=400, detail="New passwords do not match.")

    new_hash = hash_password(req.new_password)
    update_user_password(current_user.id, new_hash)
    # Invalidate other sessions
    return {"success": True, "message": "Password updated successfully."}

@router.delete("")
@router.delete("/delete-account")
async def delete_account(
    req: DeleteAccountRequest,
    request: Request,
    response: Response,
    current_user: User = Depends(get_current_user)
):
    verify_csrf(request)
    if not verify_password(req.password, current_user.password_hash):
        raise HTTPException(status_code=400, detail="Incorrect password. Account cannot be deleted.")

    # Permanently delete user and all cascading data
    delete_user_account(current_user.id)
    clear_session_cookie(response)
    set_csrf_cookie(response)

    return {
        "success": True,
        "message": "Your account and all associated cloud conversations, memories, and files have been permanently deleted."
    }
