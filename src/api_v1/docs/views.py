import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBasic, HTTPBasicCredentials
from fastapi.openapi.docs import get_swagger_ui_html
from fastapi.openapi.utils import get_openapi

from core.config import settings


def create_docs_router(app):
    router = APIRouter(tags=["docs"])

    security = HTTPBasic()

    def get_current_username(credentials: HTTPBasicCredentials = Depends(security)):
        correct_username = secrets.compare_digest(credentials.username, settings.docs.username)
        correct_password = secrets.compare_digest(credentials.password, settings.docs.password)
        if not (correct_username and correct_password):
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Incorrect username or password",
                headers={"WWW-Authenticate": "Basic"},
            )
        return credentials.username

    @router.get("/docs")
    async def get_documentation(username: str = Depends(get_current_username)):
        return get_swagger_ui_html(openapi_url="/openapi.json", title="docs")

    @router.get("/openapi.json")
    async def openapi(username: str = Depends(get_current_username)):
        return get_openapi(title="FastAPI", version="0.1.0", routes=app.routes)

    return router
