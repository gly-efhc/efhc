"""Admin router entrypoint.

Single place that wires admin routers into one aiogram Router.
"""

from __future__ import annotations

from aiogram import Router
from app.bot.handlers.admin.admin_ads_handlers import (
    router as admin_ads_router,
)
from app.bot.handlers.admin.admin_hub_handlers import (
    router as admin_hub_router,
)
from app.bot.handlers.admin.admin_main_handlers import (
    router as admin_main_router,
)
from app.bot.handlers.admin.admin_panels_handlers import (
    router as admin_panels_router,
)
from app.bot.handlers.admin.admin_referrals_handlers import (
    router as admin_referrals_router,
)
from app.bot.handlers.admin.admin_stats_handlers import (
    router as admin_stats_router,
)
from app.bot.handlers.admin.admin_tasks_handlers import (
    router as admin_tasks_router,
)
from app.bot.handlers.admin.admin_users_handlers import (
    router as admin_users_router,
)
from app.bot.handlers.admin.admin_withdrawals_handlers import (
    router as admin_withdrawals_router,
)

router = Router()
router.include_router(admin_main_router)
router.include_router(admin_users_router)
router.include_router(admin_panels_router)
router.include_router(admin_hub_router)
router.include_router(admin_tasks_router)
router.include_router(admin_referrals_router)
router.include_router(admin_withdrawals_router)
router.include_router(admin_stats_router)
router.include_router(admin_ads_router)
