import os
import uuid
import shutil
import traceback

from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Response
from pydantic import BaseModel
from webauthn import (
    generate_registration_options, verify_registration_response,
    generate_authentication_options, verify_authentication_response,
    options_to_json
)
from core.database import supabase
from webauthn.helpers import base64url_to_bytes
from webauthn.helpers.structs import PublicKeyCredentialDescriptor
router = APIRouter()

# ==========================================
# CẤU HÌNH HỆ THỐNG
# ==========================================
STORAGE_DIR = "vault_storage"
os.makedirs(STORAGE_DIR, exist_ok=True)

# Cấu hình Sinh trắc học (Sửa ORIGIN nếu React của bạn chạy cổng khác)
RP_ID = "sinh-trac-hoc-fe.vercel.app"
RP_NAME = "Ví Két Sắt"
ORIGIN = "https://sinh-trac-hoc-fe.vercel.app"
challenges_store = {}

class RegisterRequest(BaseModel):
    wallet_address: str
    vault_name: str = None
class VerifyRequest(BaseModel):
    wallet_address: str
    credential: dict

# ==========================================
# API QUẢN LÝ KÉT SẮT VÀ FILE
# ==========================================

@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    is_private: str = Form("false"),
    thumbnail: str = Form(""),
    wallet_address: str = Form(...) # <--- NHẬN ĐỊA CHỈ VÍ TỪ FRONTEND
):
    try:
        filename = f"{uuid.uuid4()}.enc"
        file_path = os.path.join(STORAGE_DIR, filename)

        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        is_priv_bool = is_private.lower() == 'true'
        data = {
            "filename": filename,
            "is_private": is_priv_bool,
            "thumbnail": thumbnail,
            "wallet_address": wallet_address
        }
        supabase.table("photos").insert(data).execute()

        return {"filename": filename, "status": "success"}

    except Exception as e:
        print("=== LỖI CHI TIẾT KHI UPLOAD ===")
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/download/{filename}")
async def download_encrypted_file(filename: str):
    try:
        file_path = os.path.join(STORAGE_DIR, filename)
        if not os.path.exists(file_path):
            raise Exception("File không tồn tại trên ổ cứng")

        with open(file_path, "rb") as f:
            content = f.read()

        return Response(content=content, media_type="text/plain")
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/photos")
async def get_all_photos(wallet_address: str):
    try:
        response = supabase.table("photos").select("filename, is_private, thumbnail").eq("wallet_address", wallet_address).execute()
        return {"photos": response.data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/delete/{filename}")
async def delete_file(filename: str):
    try:
        file_path = os.path.join(STORAGE_DIR, filename)
        if os.path.exists(file_path):
            os.remove(file_path)

        supabase.table("photos").delete().eq("filename", filename).execute()
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

# ==========================================
# API BẢO MẬT SINH TRẮC HỌC (FIDO2 / WEBAUTHN)
# ==========================================

@router.post("/webauthn/register/generate")
async def generate_register_options(req: RegisterRequest):
    try:
        # Nếu Frontend gửi tên lên, dùng tên đó. Nếu không, dùng mã băm làm phương án dự phòng.
        display_name = req.vault_name if req.vault_name else req.wallet_address
        
        options = generate_registration_options(
            rp_id=RP_ID, 
            rp_name=RP_NAME,
            user_id=req.wallet_address.encode(), 
            user_name=display_name # Báo cho Chrome biết tên tài khoản để hiển thị
        )
        challenges_store[f"reg_{req.wallet_address}"] = options.challenge
        return Response(content=options_to_json(options), media_type="application/json")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.post("/webauthn/register/verify")
async def verify_register(req: VerifyRequest):
    try:
        expected_challenge = challenges_store.pop(f"reg_{req.wallet_address}", None)
        verification = verify_registration_response(
            credential=req.credential, expected_challenge=expected_challenge,
            expected_rp_id=RP_ID, expected_origin=ORIGIN
        )
        # Lưu chữ ký sinh trắc học vào Database
        supabase.table("passkeys").insert({
            "credential_id": verification.credential_id.hex(),
            "wallet_address": req.wallet_address,
            "public_key": verification.credential_public_key.hex(),
            "sign_count": verification.sign_count
        }).execute()
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))

@router.post("/webauthn/auth/generate")
async def generate_auth_options(req: RegisterRequest):
    try:
        # 1. Tìm chính xác các chữ ký (credential_id) thuộc về Két sắt này trong DB
        db_passkeys = supabase.table("passkeys").select("credential_id").eq("wallet_address", req.wallet_address).execute()
        
        allow_credentials = []
        if db_passkeys.data:
            for pk in db_passkeys.data:
                allow_credentials.append(
                    PublicKeyCredentialDescriptor(
                        id=bytes.fromhex(pk["credential_id"])
                    )
                )

        # 2. Yêu cầu trình duyệt CHỈ DÙNG ĐÚNG chữ ký này (bỏ qua menu chọn dư thừa)
        options = generate_authentication_options(
            rp_id=RP_ID,
            allow_credentials=allow_credentials
        )
        
        challenges_store[f"auth_{req.wallet_address}"] = options.challenge
        return Response(content=options_to_json(options), media_type="application/json")
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
@router.post("/webauthn/auth/verify")
async def verify_auth(req: VerifyRequest):
    try:
        # Lấy tất cả chữ ký của Ví này từ Database
        db_passkey = supabase.table("passkeys").select("*").eq("wallet_address", req.wallet_address).execute()
        if not db_passkey.data: 
            raise Exception("Két sắt này chưa được liên kết khuôn mặt!")
        
        expected_challenge = challenges_store.pop(f"auth_{req.wallet_address}", None)
        if not expected_challenge:
            raise Exception("Phiên đăng nhập hết hạn. Vui lòng tải lại trang!")

        # --- FIX 1: TÌM ĐÚNG CHỮ KÝ MÀ TRÌNH DUYỆT ĐANG DÙNG ---
        req_cred_id_hex = base64url_to_bytes(req.credential["id"]).hex()
        stored_cred = None
        for key in db_passkey.data:
            if key["credential_id"] == req_cred_id_hex:
                stored_cred = key
                break
                
        if not stored_cred:
            raise Exception("Thiết bị này không khớp với bất kỳ chữ ký nào trong Két!")

        # --- FIX 2: XÁC MINH CHỮ KÝ ---
        verification = verify_authentication_response(
            credential=req.credential, 
            expected_challenge=expected_challenge,
            expected_rp_id=RP_ID, 
            expected_origin=ORIGIN,
            credential_public_key=bytes.fromhex(stored_cred["public_key"]),
            credential_current_sign_count=stored_cred["sign_count"]
        )
        
        # --- FIX 3: CẬP NHẬT BỘ ĐẾM BẢO MẬT (RẤT QUAN TRỌNG) ---
        supabase.table("passkeys").update({
            "sign_count": verification.new_sign_count
        }).eq("credential_id", stored_cred["credential_id"]).execute()

        return {"status": "success"}
    except Exception as e:
        import traceback
        print("=== LỖI XÁC THỰC WEBAUTHN ===")
        traceback.print_exc() # In chi tiết lỗi ra Terminal để dễ bắt bệnh
        raise HTTPException(status_code=400, detail=str(e))

        # ==========================================
# KHỞI ĐỘNG SERVER (CHẠY CỐ ĐỊNH Ở CỔNG 8000)
# ==========================================
        