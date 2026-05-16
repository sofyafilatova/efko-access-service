from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from app.core.config import settings
import logging
from app.routes.zones import router as zones_router
from app.routes.dev import router as dev_router
from app.routes.employees import router as employees_router
from app.routes.shifts import router as shifts_router
from app.routes.attendance import router as attendance_router
from app.routes.bookings import router as bookings_router
from app.routes.guest_passes import router as guest_passes_router
from app.routes.notifications import router as notifications_router
import asyncio
from app.core.rabbitmq import close as rabbitmq_close
from app.services.personnel_consumer import start_personnel_consumer
from app.services.shift_status_updater import run_shift_status_updater
from app.core.config import settings
from app.routes.requests import router as requests_router
from app.routes.web_employees import router as web_employees_router
from app.routes.web_shifts import router as web_shifts_router
from app.routes.access_rights import router as access_rights_router
from app.routes import web_employees, web_shifts, web_employee_status
from app.routes.web_employee_status import router as web_employee_status_router
from app.routes.web_notifications import router as web_notifications_router
from app.routes.attendance_web import router as attendance_web_router
from app.routes.web_bookings import router as web_bookings_router
from app.routes.web_schedules import router as web_schedules_router
from app.routes.web_broadcasts import router as web_broadcasts_router


print(f"DEBUG RABBITMQ_URL = {settings.rabbitmq_url}")

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("🚀 access-service starting...")
    
    # Запускаем фоновую задачу обновления статусов смен
    asyncio.create_task(run_shift_status_updater())
    
    asyncio.create_task(start_personnel_consumer())
    yield
    await rabbitmq_close()
    logger.info("🛑 access-service shutdown")

app = FastAPI(
    title="EFKO Access Control Service",
    version="1.0.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(zones_router, prefix="/api")
if settings.environment == "development":
    app.include_router(dev_router, prefix="/api")
app.include_router(employees_router, prefix="/api")
app.include_router(shifts_router, prefix="/api")
app.include_router(attendance_router, prefix="/api")
app.include_router(bookings_router, prefix="/api")
app.include_router(guest_passes_router, prefix="/api")
app.include_router(notifications_router, prefix="/api")
app.include_router(requests_router, prefix="/api")
app.include_router(web_employees_router, prefix="/api")
app.include_router(web_shifts_router, prefix="/api")
app.include_router(access_rights_router, prefix="/api")
app.include_router(web_notifications_router, prefix="/api")
app.include_router(attendance_web_router, prefix="/api")
app.include_router(web_bookings_router, prefix="/api")
app.include_router(web_schedules_router, prefix="/api")
app.include_router(web_broadcasts_router, prefix="/api")

# 👇 НОВЫЕ ПОДКЛЮЧЕНИЯ
app.include_router(web_employee_status_router, prefix="/api")

@app.get("/health")
async def health():
    return {"status": "ok"}

@app.get("/api")
async def root():
    return {"message": "EFKO Access Service API", "version": "1.0.0"}

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(
        app,
        host=settings.api_host,
        port=settings.api_port
    )