"""Auditor — large image uploads (FinOps: rightsizing). Stub for BOLT-04."""

from __future__ import annotations

from . import Auditor, Category, Finding
from ..session import Session


class LargeImageUploads:
    name = "large_image_uploads"
    title = "Large image uploads"
    category = Category.RIGHTSIZING

    def run(self, session: Session) -> list[Finding]:
        return []
