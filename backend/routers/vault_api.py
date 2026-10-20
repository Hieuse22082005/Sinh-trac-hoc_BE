import uuid
from fastapi import APIRouter, UploadFile, File, Form, HTTPException
from fastapi.responses import Response

# Nhập khẩu biến supabase từ file database.py của chúng ta
from core.database import supabase

# Tạo một "Trạm trung chuyển" API
router = APIRouter()

@router.post("/upload")
async def upload_encrypted_file(
    file: UploadFile = File(...),
    is_private: str = Form("false"),
    thumbnail: str = Form("")
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
            "thumbnail": thumbnail
        }).execute()
        
        return {"status": "success", "filename": random_filename}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("/download/{filename}")
async def download_encrypted_file(filename: str):
    try:
        res = supabase.storage.from_("vault").download(filename)
        return Response(content=res, media_type="text/plain")
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e))

@router.get("/photos")
async def get_all_photos():
    try:
        response = supabase.table("photos").select("filename, is_private, thumbnail").execute()
        return {"photos": response.data}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.delete("/delete/{filename}")
async def delete_file(filename: str):
    try:
        supabase.storage.from_("vault").remove([filename])
        supabase.table("photos").delete().eq("filename", filename).execute()
        return {"status": "success"}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))