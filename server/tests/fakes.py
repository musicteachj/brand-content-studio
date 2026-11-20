"""Deterministic test doubles — no network, no cost.

`FakeVectorStore` partitions chunks by workspace namespace (so isolation is
structural, exactly like Chroma's per-workspace collections) and ranks queries
by lexical token overlap, which is stable and good enough to prove retrieval
behavior without real embeddings. `FakeGenerationService` yields canned tokens
so the SSE route can be tested without calling Claude, and settles each ledger line
from a fixed token count.
"""
from __future__ import annotations

import copy
import re
from collections.abc import AsyncGenerator
from typing import Any

from app.config import settings
from app.models.common import BrandColor, BrandFonts
from app.models.workspace import BrandExtractResponse
from app.rag.vector_store import Chunk, RetrievedChunk
from app.services.ai_meter import MeteredLine

FAKE_INPUT_TOKENS = 1_000
FAKE_OUTPUT_TOKENS = 200


async def settle_fake_usage(line: MeteredLine) -> None:
    await line.settle_usage(
        model=settings.ai_model, input_tokens=FAKE_INPUT_TOKENS, output_tokens=FAKE_OUTPUT_TOKENS
    )

_WORD = re.compile(r"[a-z0-9]+")


def _tokens(text: str) -> set[str]:
    return set(_WORD.findall(text.lower()))


class FakeVectorStore:
    """In-memory VectorStore: {namespace: {chunk_id: Chunk}}."""

    def __init__(self) -> None:
        self._data: dict[str, dict[str, Chunk]] = {}

    async def upsert_chunks(self, workspace_id: str, chunks: list[Chunk]) -> int:
        ns = self._data.setdefault(workspace_id, {})
        for c in chunks:
            ns[c["id"]] = c
        return len(chunks)

    async def query(self, workspace_id: str, query: str, k: int = 6) -> list[RetrievedChunk]:
        ns = self._data.get(workspace_id, {})
        q = _tokens(query)
        scored: list[RetrievedChunk] = []
        for c in ns.values():
            overlap = len(q & _tokens(c["text"]))
            denom = (len(q) or 1)
            scored.append(
                {"id": c["id"], "text": c["text"], "score": overlap / denom, "metadata": c["metadata"]}
            )
        scored.sort(key=lambda r: r["score"], reverse=True)
        return [r for r in scored if r["score"] > 0][:k]

    async def get_by_kinds(
        self, workspace_id: str, kinds: list[str], limit: int = 8
    ) -> list[RetrievedChunk]:
        ns = self._data.get(workspace_id, {})
        out: list[RetrievedChunk] = []
        for c in ns.values():
            if c["metadata"].get("asset_kind") in kinds:
                out.append({"id": c["id"], "text": c["text"], "score": 1.0, "metadata": c["metadata"]})
            if len(out) >= limit:
                break
        return out

    async def delete_workspace(self, workspace_id: str) -> None:
        self._data.pop(workspace_id, None)

    async def delete_asset(self, workspace_id: str, asset_id: str) -> None:
        ns = self._data.get(workspace_id, {})
        for cid in [cid for cid, c in ns.items() if c["metadata"].get("asset_id") == asset_id]:
            ns.pop(cid, None)

    async def health(self) -> bool:
        return True


class FakeGenerationService:
    """Drop-in for GenerationService that yields canned tokens (no Claude call). Each call
    marks its ledger line started and settles it as if Claude reported `FAKE_INPUT_TOKENS`
    in and `FAKE_OUTPUT_TOKENS` out (4,000 micros at Sonnet 5.5 prices)."""

    REPLY = "Hempcrete sequesters carbon for the life of the building.\n\n#EmbodiedCarbon #Hempcrete"
    CARD_COPY = "Specify hempcrete early. It locks carbon in the walls for the life of the building."
    CARD_FIELDS = {
        "eyebrow": "MATERIAL NOTES",
        "headline": "Carbon, locked in the wall",
        "body": "Hempcrete sequesters carbon for the building's whole life.",
        "cta": "Read the field notes",
        "hashtag": "#EmbodiedCarbon",
        "suggested_keywords": ["hempcrete wall", "natural building material", "construction site"],
    }
    DOC_DRAFT = (
        "Recycled-denim insulation turns post-consumer jeans into a high-performance "
        "thermal envelope. It cuts embodied carbon, is safe to handle without gloves, "
        "and meets the same R-value targets as mineral wool."
    )
    DOC_SECTIONS = {
        "title": "Recycled-Denim Insulation",
        "eyebrow": "Product brief",
        "lede": "A high-performance insulation made from post-consumer denim, built for low-carbon construction.",
        "sections": [
            {
                "heading": "Why it matters",
                "body": "It diverts textile waste while cutting the embodied carbon of the wall assembly.",
                "bullets": ["Lower embodied carbon", "Safe to handle without PPE"],
            },
            {
                "heading": "Specifications",
                "body": "Performance matches conventional batts.",
                "bullets": ["R-value 3.7 per inch", "Class A fire rating"],
            },
        ],
        "footer": "Verdure Materials — build with what's already here.",
    }

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []
        self.card_field_calls: list[tuple[str, str]] = []
        self.doc_section_calls: list[tuple[str, str]] = []
        self.fill_calls: list[tuple[str, str]] = []

    async def _stream(self, text: str, line: MeteredLine) -> AsyncGenerator[str, None]:
        line.mark_started()
        for token in text.split(" "):
            yield token + " "
        await settle_fake_usage(line)

    async def stream_text(self, system: str, user: str, *, line: MeteredLine) -> AsyncGenerator[str, None]:
        self.calls.append((system, user))
        async for token in self._stream(self.REPLY, line):
            yield token

    async def stream_copy(self, system: str, user: str, *, line: MeteredLine) -> AsyncGenerator[str, None]:
        self.calls.append((system, user))
        async for token in self._stream(self.CARD_COPY, line):
            yield token

    async def extract_card_fields(self, system: str, user: str, *, line: MeteredLine) -> dict:
        self.card_field_calls.append((system, user))
        line.mark_started()
        await settle_fake_usage(line)
        return dict(self.CARD_FIELDS)

    async def stream_document(self, system: str, user: str, *, line: MeteredLine) -> AsyncGenerator[str, None]:
        self.calls.append((system, user))
        async for token in self._stream(self.DOC_DRAFT, line):
            yield token

    async def extract_document_sections(self, system: str, user: str, *, line: MeteredLine) -> dict:
        self.doc_section_calls.append((system, user))
        line.mark_started()
        await settle_fake_usage(line)
        return copy.deepcopy(self.DOC_SECTIONS)

    async def fill_template_values(
        self, system: str, user: str, tool: dict[str, Any], *, line: MeteredLine
    ) -> dict[str, Any]:
        self.fill_calls.append((system, user))
        line.mark_started()
        await settle_fake_usage(line)
        return {name: f"draft {name}" for name in tool["input_schema"]["properties"]}


class FakeBrandExtractService:
    """Drop-in for BrandExtractService (no vision call); settles like the generation fake."""

    NOTE = "Punchy hook, one tight line, earthy photography."

    def __init__(self) -> None:
        self.calls: list[str] = []

    async def propose(self, data: bytes, media_type: str, *, line: MeteredLine) -> BrandExtractResponse:
        self.calls.append("propose")
        line.mark_started()
        await settle_fake_usage(line)
        return BrandExtractResponse(
            colors=[BrandColor(name="Forest", hex="#1C3A2E", role="primary")],
            voice_summary="Calm, precise.",
            fonts=BrandFonts(heading="Fraunces", body="Inter", mono=None),
        )

    async def propose_exemplar_note(self, data: bytes, media_type: str, *, line: MeteredLine) -> str:
        self.calls.append("propose_exemplar_note")
        line.mark_started()
        await settle_fake_usage(line)
        return self.NOTE
