from fastapi import FastAPI
from contextlib import asynccontextmanager

from database import close_mongodb_connection, connect_to_mongodb
from routers.api import router as api_router
from routers.frontend import router as frontend_router
from routers.ws import router as ws_router

@asynccontextmanager
async def lifespan(app: FastAPI):
    await connect_to_mongodb()
    yield
    await close_mongodb_connection()


app = FastAPI(lifespan=lifespan)

app.include_router(frontend_router)
app.include_router(api_router)
app.include_router(ws_router)