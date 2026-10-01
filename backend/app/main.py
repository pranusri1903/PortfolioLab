from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.api.routes import router
from app.config import get_settings
from app.errors import install_error_handlers

app = FastAPI(
    title="PortfolioLab API",
    version="0.1.0",
    description="Portfolio analytics. Sample data only; not investment advice.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=get_settings().cors_origins.split(","),
    allow_methods=["*"],
    allow_headers=["*"],
    expose_headers=["Content-Disposition"],
)
install_error_handlers(app)
app.include_router(router)
