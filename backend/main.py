import os
import uuid
from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.responses import Response
from fastapi.middleware.cors import CORSMiddleware
from supabase import create_client, Client
from dotenv import load_dotenv

load_dotenv()
url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")
supabase: Client = create_client(url, key)

app = FastAPI()
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_credentials=True, allow_methods=["*"], allow_headers=["*"])

@app.post("/upload")
async def upload_encrypted_file(
    file: UploadFile = File(...),
    is_private: str = Form("false"),
    thumbnail: str = Form("") # Nhận ảnh mờ
):
    try:
        file_bytes = await file.read()
        random_filename = f"{uuid.uuid4()}.enc"
        
        supabase.storage.from_("vault").upload(
            path=random_filename, file=file_bytes, file_options={"content-type": "text/plain"}
        )
        
        is_priv_bool = is_private.lower() == 'true'
        supabase.table("photos").insert({
            "filename": random_filename,
            "is_private": is_priv_bool,
            "thumbnail": thumbnail # Lưu ảnh mờ vào DB
        }).execute()
        
        return {"status": "success", "filename": random_filename}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/download/{filename}")
async def download_encrypted_file(filename: str):
    try:
        res = supabase.storage.from_("vault").download(filename)
        return Response(content=res, media_type="text/plain")
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

@app.get("/photos")
async def get_all_photos():
    try:
        # Đọc thêm cột thumbnail để gửi về cho Web
        response = supabase.table("photos").select("filename, is_private, thumbnail").execute()
        return {"photos": response.data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))