from fastapi import APIRouter
from app.api.v1 import auth, users, companies, access_requests, reconciliation, file_mapping, tickets

router = APIRouter(prefix="/api/v1")

router.include_router(auth.router)
router.include_router(users.router)
router.include_router(companies.router)
router.include_router(access_requests.router)
router.include_router(reconciliation.router)
router.include_router(file_mapping.router)
router.include_router(tickets.router)
