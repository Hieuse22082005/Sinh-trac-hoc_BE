import os
from supabase import create_client, Client
from dotenv import load_dotenv

# Đọc file .env
load_dotenv()
url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")

# Khởi tạo kết nối Supabase và xuất ra để các file khác dùng ké
supabase: Client = create_client(url, key)