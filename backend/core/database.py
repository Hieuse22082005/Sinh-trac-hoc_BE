import os
import httpx
from supabase import create_client, Client, ClientOptions
from dotenv import load_dotenv

load_dotenv()
url: str = os.environ.get("SUPABASE_URL")
key: str = os.environ.get("SUPABASE_KEY")

# --- BÍ QUYẾT UP VIDEO NẶNG: Ép Supabase chờ 10 phút thay vì 5 giây mặc định ---
opts = ClientOptions(
    postgrest_client_timeout=600,
    storage_client_timeout=600
)
supabase: Client = create_client(url, key, options=opts)

# Cưỡng chế can thiệp thẳng vào lõi mạng
custom_timeout = httpx.Timeout(600.0)
if hasattr(supabase.storage, 'client'):
    supabase.storage.client.timeout = custom_timeout
elif hasattr(supabase.storage, '_client'):
    supabase.storage._client.timeout = custom_timeout