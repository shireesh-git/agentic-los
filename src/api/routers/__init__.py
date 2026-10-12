"""HTTP routers, one per business area."""

from src.api.routers import (
    admin, analytics, approvals, cam, cases, challenges, chat, companies, diagnostics, documents, external, final_cam, investigations, los, observations, onboarding, reassessment, repayment, stress_test, system,
)

ALL_ROUTERS = [
    system.router,
    companies.router,
    onboarding.router,
    cases.router,
    cam.router,
    observations.router,
    investigations.router,
    challenges.router,
    repayment.router,
    stress_test.router,
    reassessment.router,
    final_cam.router,
    approvals.router,
    documents.router,
    analytics.router,
    external.router,
    chat.router,
    admin.router,
    diagnostics.router,
    los.router,
]
