from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

# Nhập khẩu cái "Trạm trung chuyển" API mà ta vừa tạo
from routers import vault_api

app = FastAPI()

# Cấu hình chống chặn tường lửa CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], 
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Gắn toàn bộ các API đã viết ở file kia vào ứng dụng chính
app.include_router(vault_api.router)