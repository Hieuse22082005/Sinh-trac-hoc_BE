import os
import uuid
from fastapi import FastAPI, UploadFile, File, HTTPException
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
        # Đọc dữ liệu lộn xộn trực tiếp trên RAM
        file_bytes = await file.read()
        random_filename = f"{uuid.uuid4()}.enc"
        
        # Đẩy thẳng lên Supabase
        res = supabase.storage.from_("vault").upload(
            path=random_filename, 
            file=file_bytes, 
            file_options={"content-type": "text/plain"}
        )
        
        return {"status": "success", "filename": random_filename}
    except Exception as e:
        # Báo lỗi rõ ràng để không bị nhầm lẫn
        raise HTTPException(status_code=500, detail="Lỗi Supabase: Không tìm thấy Bucket 'vault' hoặc sai Service Key.")