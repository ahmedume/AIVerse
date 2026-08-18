# src/app/routers/export_router.py
# Purpose: DOCX/PDF export endpoint.
# Exports: router

from fastapi import APIRouter

router = APIRouter(prefix="", tags=["export"])