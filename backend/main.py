import os
import uuid
from fastapi import FastAPI, UploadFile, File, HTTPException
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()
url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(url, key)

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

@app.post("/upload")
async def upload_encrypted_file(file: UploadFile = File(...)):
    try:
        file_bytes = await file.read()
        random_filename = f"{uuid.uuid4()}.enc"
        
        # 1. Đẩy file mã hóa lên Storage (Két sắt)
        supabase.storage.from_("vault").upload(
            path=random_filename, 
            file=file_bytes, 
            file_options={"content-type": "text/plain"}
        )
        
        # 2. Tự động ghi tên file vào bảng 'photos' trong Database
        supabase.table("photos").insert({"filename": random_filename}).execute()
        
        return {"status": "success", "filename": random_filename}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Lỗi hệ thống: {str(e)}")

@app.get("/download/{filename}")
async def download_encrypted_file(filename: str):
    try:
        # Lấy nội dung file từ Storage
        res = supabase.storage.from_("vault").download(filename)
        return Response(content=res, media_type="text/plain")
    except Exception as e:
        raise HTTPException(status_code=404, detail=f"Không tìm thấy file: {str(e)}")

# Thêm API MỚI: Lấy danh sách toàn bộ ảnh đã lưu
@app.get("/photos")
async def get_all_photos():
    try:
        # Mở sổ Database ra đọc xem có những file nào
        response = supabase.table("photos").select("filename").execute()
        # Trả về một mảng chứa tên các file
        filenames = [item['filename'] for item in response.data]
        return {"photos": filenames}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))