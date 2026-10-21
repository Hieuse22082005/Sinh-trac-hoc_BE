import os
import uuid
import shutil
import traceback
from fastapi import APIRouter, UploadFile, File, Form, HTTPException, Response
from core.database import supabase

router = APIRouter()

# TẠO THƯ MỤC "vault_storage" TRÊN Ổ CỨNG ĐỂ CHỨA VIDEO/ẢNH KHỦNG
STORAGE_DIR = "vault_storage"
os.makedirs(STORAGE_DIR, exist_ok=True)

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

        # 1. LƯU FILE THẲNG VÀO Ổ CỨNG (Siêu tốc, cân mọi dung lượng)
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # 2. Lưu thông tin dạng chữ vào Bảng Database Supabase
        is_priv_bool = is_private.lower() == 'true'
        data = {
            "filename": filename,
            "is_private": is_priv_bool,
            "thumbnail": thumbnail,
            "wallet_address": wallet_address # <--- ĐÁNH DẤU CHỦ SỞ HỮU
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

        # Đọc file mã hóa từ ổ cứng siêu tốc
        with open(file_path, "rb") as f:
            content = f.read()

        return Response(content=content, media_type="text/plain")
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/photos")
async def get_all_photos(wallet_address: str): # <--- BẮT BUỘC PHẢI CÓ ĐỊA CHỈ VÍ MỚI CHO XEM
    try:
        # CHỈ TRẢ VỀ NHỮNG FILE CỦA ĐÚNG VÍ NÀY
        response = supabase.table("photos").select("filename, is_private, thumbnail").eq("wallet_address", wallet_address).execute()
        return {"photos": response.data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/delete/{filename}")
async def delete_file(filename: str):
    try:
        # Xóa file vật lý trên ổ cứng
        file_path = os.path.join(STORAGE_DIR, filename)
        if os.path.exists(file_path):
            os.remove(file_path)

        # Xóa dữ liệu trên Supabase Database
        supabase.table("photos").delete().eq("filename", filename).execute()
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))