import os
import uuid
import shutil
import traceback
import random
import smtplib
from email.mime.text import MIMEText
from datetime import datetime, timedelta
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Response, Query
from pydantic import BaseModel
from dotenv import load_dotenv
import urllib.request
import json
from webauthn import (
    generate_registration_options, verify_registration_response,
    generate_authentication_options, verify_authentication_response,
    options_to_json
)
from core.database import supabase
from webauthn.helpers import base64url_to_bytes
from webauthn.helpers.structs import PublicKeyCredentialDescriptor

# Tải biến môi trường từ file .env
load_dotenv()

router = APIRouter()

# ==========================================
# CẤU HÌNH HỆ THỐNG
# ==========================================
STORAGE_DIR = "vault_storage"
os.makedirs(STORAGE_DIR, exist_ok=True)

RP_NAME = "Ví Két Sắt"
RP_ID = "sinh-trac-hoc-fe.vercel.app"

ORIGIN = "https://sinh-trac-hoc-fe.vercel.app"
challenges_store = {}

class RegisterRequest(BaseModel):
    wallet_address: str
    vault_name: str = None

class VerifyRequest(BaseModel):
    wallet_address: str
    credential: dict

class OTPRequest(BaseModel):
    wallet_address: str

class OTPVerify(BaseModel):
    wallet_address: str
    otp_code: str
    new_device_id: str

# ==========================================
# API QUẢN LÝ KÉT SẮT VÀ FILE
# ==========================================

@router.post("/upload")
async def upload_file(
    file: UploadFile = File(...),
    is_private: str = Form("false"),
    thumbnail: str = Form(""), # Đây là mật khẩu cấp 2 đã băm
    wallet_address: str = Form(...) 
):
    try:
        # 1. Tạo tên file (Lưu vào thư mục mang tên địa chỉ ví cho dễ quản lý)
        filename = f"{uuid.uuid4()}.enc"
        
        # 2. Đọc dữ liệu file (Đây sẽ là chuỗi ký tự mã hóa vô nghĩa từ Frontend gửi lên)
        file_bytes = await file.read()

        # 3. ĐẨY THẲNG LÊN BUCKET "vault_images" CỦA SUPABASE
        supabase.storage.from_("vault_images").upload(
            path=filename,
            file=file_bytes,
            file_options={"content-type": "text/plain"} # Định dạng text vì ảnh đã bị mã hóa thành chuỗi
        )

        # 4. Lưu thông tin vào Database
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
async def delete_photo(filename: str, delete_pass: str = Query(...)):
    try:
        # 1. KIỂM TRA MẬT KHẨU (HÃY SỬA LẠI CHỮ "123456" THÀNH MẬT KHẨU CỦA BẠN)
        if delete_pass != "22082005":
            raise HTTPException(status_code=403, detail="Sai mật khẩu")
        
        # 2. Bắn lệnh xóa file vật lý trên Supabase Storage
        supabase.storage.from_("vault_images").remove([filename])
        
        # 3. Bắn lệnh xóa dữ liệu dòng đó trong Database
        supabase.table("photos").delete().eq("filename", filename).execute()
        
        return {"status": "success", "message": "Đã tiêu hủy"}
        
    except HTTPException as he:
        raise he # Nếu sai mật khẩu thì quăng lỗi 403 ra ngoài
    except Exception as e:
        print(f"=== LỖI SẬP SERVER KHI XÓA: {str(e)} ===")
        # Quăng lỗi 500 kèm chi tiết lỗi thật để Frontend biết
        raise HTTPException(status_code=500, detail=str(e))

# ==========================================
# API BẢO MẬT SINH TRẮC HỌC (FIDO2 / WEBAUTHN)
# ==========================================

@router.post("/webauthn/register/generate")
async def generate_register_options(req: RegisterRequest):
    try:
        display_name = req.vault_name if req.vault_name else req.wallet_address
        options = generate_registration_options(
            rp_id=RP_ID, 
            rp_name=RP_NAME,
            user_id=req.wallet_address.encode(), 
            user_name=display_name 
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
        
        # Đã đổi .insert() thành .update() và thêm .eq() để cập nhật đúng ví
        supabase.table("passkeys").update({
            "credential_id": verification.credential_id.hex(),
            "public_key": verification.credential_public_key.hex(),
            "sign_count": verification.sign_count
        }).eq("wallet_address", req.wallet_address).execute()
        
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=400, detail=str(e))
    
@router.post("/webauthn/auth/generate")
async def generate_auth_options(req: RegisterRequest):
    try:
        db_passkeys = supabase.table("passkeys").select("credential_id").eq("wallet_address", req.wallet_address).execute()
        
        allow_credentials = []
        if db_passkeys.data:
            for pk in db_passkeys.data:
                allow_credentials.append(
                    PublicKeyCredentialDescriptor(
                        id=bytes.fromhex(pk["credential_id"])
                    )
                )

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
        db_passkey = supabase.table("passkeys").select("*").eq("wallet_address", req.wallet_address).execute()
        if not db_passkey.data: 
            raise Exception("Két sắt này chưa được liên kết khuôn mặt!")
        
        expected_challenge = challenges_store.pop(f"auth_{req.wallet_address}", None)
        if not expected_challenge:
            raise Exception("Phiên đăng nhập hết hạn. Vui lòng tải lại trang!")

        req_cred_id_hex = base64url_to_bytes(req.credential["id"]).hex()
        stored_cred = None
        for key in db_passkey.data:
            if key["credential_id"] == req_cred_id_hex:
                stored_cred = key
                break
                
        if not stored_cred:
            raise Exception("Thiết bị này không khớp với bất kỳ chữ ký nào trong Két!")

        verification = verify_authentication_response(
            credential=req.credential, 
            expected_challenge=expected_challenge,
            expected_rp_id=RP_ID, 
            expected_origin=ORIGIN,
            credential_public_key=bytes.fromhex(stored_cred["public_key"]),
            credential_current_sign_count=stored_cred["sign_count"]
        )
        
        supabase.table("passkeys").update({
            "sign_count": verification.new_sign_count
        }).eq("credential_id", stored_cred["credential_id"]).execute()

        return {"status": "success"}
    except Exception as e:
        import traceback
        print("=== LỖI XÁC THỰC WEBAUTHN ===")
        traceback.print_exc()
        raise HTTPException(status_code=400, detail=str(e))

# ==========================================
# API XÁC THỰC OTP VÀ QUẢN LÝ THIẾT BỊ
# ==========================================

@router.post("/request-otp")
async def request_otp(data: OTPRequest):
    # 1. Kiểm tra ví có email khôi phục không
    response = supabase.table('passkeys').select('recovery_email').eq('wallet_address', data.wallet_address).execute()
    
    if not response.data or not response.data[0].get('recovery_email'):
        raise HTTPException(status_code=400, detail="Két sắt chưa liên kết email bảo mật. Không thể khôi phục!")
    
    user_email = response.data[0]['recovery_email']
    
    # 2. Tạo mã OTP 6 số và thời gian hết hạn (5 phút)
    otp_code = str(random.randint(100000, 999999))
    expires_at = (datetime.utcnow() + timedelta(minutes=5)).isoformat()
    
    # 3. Lưu OTP vào cơ sở dữ liệu
    supabase.table('passkeys').update({
        "otp_code": otp_code,
        "otp_expires_at": expires_at
    }).eq('wallet_address', data.wallet_address).execute()
    
    # 4. Gửi Email bằng HTTP (Tránh Render chặn SMTP)
    try:
        # Thay link Google Apps Script (nếu bạn đã tạo ở bước trước) vào đây:
        GAS_WEBHOOK_URL = "https://script.google.com/macros/s/AKfycbwI5bPavKcD3WFjqD7POVyZHdhB96a1npR9Yzd8bOHWdt05SgAxh6L7WsMTfzGmMTWb/exec"
        
        payload = {
            "email": user_email,
            "subject": "🔒 Mã xác thực OTP Két sắt Hush",
            "html": f"<p>Mã xác thực OTP của bạn là: <b>{otp_code}</b>. Có hiệu lực 5 phút.</p>"
        }
        req = urllib.request.Request(
            GAS_WEBHOOK_URL,
            data=json.dumps(payload).encode('utf-8'),
            headers={'Content-Type': 'application/json'},
            method='POST'
        )
        with urllib.request.urlopen(req, timeout=10):
            pass 
    except Exception as e:
        print(f"=== LỖI GỬI EMAIL NHƯNG VẪN TIẾP TỤC: {e} ===")
        # Không raise 500 để Frontend không bị kẹt

    return {"message": "Mã OTP đã sẵn sàng."}

@router.post("/verify-otp")
async def verify_otp(data: OTPVerify):
    response = supabase.table('passkeys').select('otp_code', 'otp_expires_at').eq('wallet_address', data.wallet_address).execute()
    
    if not response.data:
        raise HTTPException(status_code=404, detail="Không tìm thấy Két sắt")
        
    vault = response.data[0]
    
    # Kiểm tra OTP và hạn sử dụng
    if not vault.get('otp_code') or vault['otp_code'] != data.otp_code:
        raise HTTPException(status_code=400, detail="Mã OTP không chính xác")
        
    # Xử lý múi giờ khi so sánh
    expires_at = datetime.fromisoformat(vault['otp_expires_at'].replace('Z', '+00:00')).replace(tzinfo=None)
    if expires_at < datetime.utcnow():
        raise HTTPException(status_code=400, detail="Mã OTP đã hết hạn")
        
    # Xác thực thành công -> Cập nhật thiết bị mới và xóa OTP cũ
    supabase.table('passkeys').update({
        "active_device_id": data.new_device_id,
        "otp_code": None,
        "otp_expires_at": None
    }).eq('wallet_address', data.wallet_address).execute()
    
    return {"status": "success", "message": "Xác thực thành công. Đã chuyển quyền sang thiết bị mới."}