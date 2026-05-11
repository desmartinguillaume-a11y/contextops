"""Auditor — large image uploads (FinOps: rightsizing)."""
from __future__ import annotations

import hashlib
import logging

from . import Category, Finding
from ..pricing import Pricing
from ..session import Session

log = logging.getLogger(__name__)

IMAGE_THRESHOLD = 50_000  # base64 chars


class LargeImageUploads:
    name = "large_image_uploads"
    title = "Large image uploads"
    category = Category.RIGHTSIZING

    def run(self, session: Session) -> list[Finding]:
        pricing = Pricing.for_model(session.model)
        findings: list[Finding] = []

        # hash → list of (turn_index, data_len) for duplicate detection
        seen: dict[str, list[tuple[int, int]]] = {}

        for turn in session.turns:
            try:
                raw = turn.raw or {}
                content = raw.get("message", {}).get("content") or []
                if not isinstance(content, list):
                    continue
                for block in content:
                    if not isinstance(block, dict):
                        continue
                    if block.get("type") != "image":
                        continue
                    source = block.get("source") or {}
                    if source.get("type") != "base64":
                        continue
                    data = source.get("data")
                    if not isinstance(data, str):
                        log.debug(
                            "large_image_uploads: non-string data field in turn %s",
                            turn.index,
                        )
                        continue
                    data_len = len(data)
                    data_hash = hashlib.md5(
                        data.encode(), usedforsecurity=False
                    ).hexdigest()

                    seen.setdefault(data_hash, []).append((turn.index, data_len))

                    if data_len > IMAGE_THRESHOLD:
                        tokens = max(1, data_len // 4)
                        dollars = pricing.dollars(input_tokens=tokens)
                        findings.append(
                            Finding(
                                auditor=self.name,
                                title=self.title,
                                category=self.category,
                                wasted_tokens=tokens,
                                wasted_dollars=dollars,
                                recommendation=(
                                    f"Turn {turn.index} contains a base64 image "
                                    f"of [bold]{data_len:,} chars[/bold] "
                                    f"(~{tokens:,} tokens, ${dollars:.4f}). "
                                    f"Large images inflate context on every refill."
                                ),
                                methodology=(
                                    "Scanned turn.raw message content for base64 "
                                    f"image blocks exceeding {IMAGE_THRESHOLD:,} chars."
                                ),
                                evidence=[
                                    f"turn {turn.index}: {data_len:,} chars, "
                                    f"~{tokens:,} tokens, "
                                    f"id={data[:40]!r}"
                                ],
                                fix_hint=(
                                    "Resize the screenshot to under 512px on the "
                                    "longest side, or use the Files API instead of "
                                    "base64 inline upload."
                                ),
                            )
                        )
            except Exception:
                log.debug(
                    "large_image_uploads: error processing turn %s",
                    getattr(turn, "index", "?"),
                    exc_info=True,
                )

        # Duplicate detection: emit one finding per hash seen in ≥2 turns
        for data_hash, occurrences in seen.items():
            if len(occurrences) < 2:
                continue
            turn_indices = [idx for idx, _ in occurrences]
            # Use data_len from first occurrence for token estimate
            data_len = occurrences[0][1]
            # wasted tokens = (count - 1) redundant copies
            redundant_copies = len(occurrences) - 1
            tokens = max(1, data_len // 4) * redundant_copies
            dollars = pricing.dollars(input_tokens=tokens)
            findings.append(
                Finding(
                    auditor=self.name,
                    title=self.title,
                    category=self.category,
                    wasted_tokens=tokens,
                    wasted_dollars=dollars,
                    recommendation=(
                        f"The same image appears in [bold]{len(occurrences)} turns[/bold] "
                        f"({', '.join(str(i) for i in turn_indices)}). "
                        f"Each copy costs ~{max(1, data_len // 4):,} tokens."
                    ),
                    methodology=(
                        "Compared MD5 hashes of base64 image data across all turns; "
                        "flagged hashes seen in 2+ distinct turns."
                    ),
                    evidence=[f"turn {idx}" for idx in turn_indices],
                    fix_hint=(
                        f"This image was sent in {len(occurrences)} turns. "
                        f"Send it once, or reference the Files API URI across turns."
                    ),
                )
            )

        findings.sort(key=lambda f: f.wasted_tokens, reverse=True)
        return findings
