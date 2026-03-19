from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter()


@router.get("/")
async def get_frontend():
    with open("index.html", "r", encoding="utf-8") as f:
        return HTMLResponse(f.read())
