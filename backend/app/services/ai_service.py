from __future__ import annotations

import json
import logging
import os
import re
from typing import Any, Dict, List, Optional

import httpx

from app.config import (
    AI_PROVIDER,
    ANTHROPIC_API_KEY,
    ANTHROPIC_MODEL,
    GEMINI_API_KEY,
    GEMINI_MODEL,
    OPENAI_API_KEY,
    OPENAI_MODEL,
)

logger = logging.getLogger(__name__)


def _extract_numbers(s: str) -> List[str]:
    return re.findall(r"\b\d+(?:\.\d+)?%?\b", str(s))


def _clean_tokens(s: str) -> set:
    s = s.lower().replace("&", " and ").replace("+", " ").replace("-", " ")
    words = re.findall(r"[a-z0-9]+", s)
    stop = {"the", "a", "an", "and", "or", "in", "on", "at", "to", "for", "of", "with", "all", "our", "is", "are"}
    return {w for w in words if w not in stop}


class AIService:
    @classmethod
    def is_available(cls) -> bool:
        if AI_PROVIDER == "none":
            return False
        return bool(OPENAI_API_KEY or GEMINI_API_KEY or ANTHROPIC_API_KEY)

    @classmethod
    def get_active_provider(cls) -> str:
        if AI_PROVIDER != "auto" and AI_PROVIDER != "none":
            return AI_PROVIDER
        if OPENAI_API_KEY:
            return "openai"
        if GEMINI_API_KEY:
            return "gemini"
        if ANTHROPIC_API_KEY:
            return "anthropic"
        return "none"

    @classmethod
    async def evaluate_semantic_text_comparison(
        cls,
        candidate_items: List[Dict[str, Any]],
        pdf_text_summary: str,
        product_name: str,
    ) -> List[Dict[str, Any]]:
        """
        Uses an LLM (OpenAI, Gemini, Anthropic) to compare text in specification documents
        with text on the artwork. Evaluates whether phrasing conveys equivalent packaging
        meaning despite different wording (e.g. synonyms, variations) or constitutes a
        genuine substantive discrepancy.
        """
        provider = cls.get_active_provider()
        if provider == "none" or not candidate_items:
            return cls._fallback_semantic_comparison(candidate_items)

        prompt = f"""You are PackGuard AI, an expert packaging compliance and semantic verification system.
Product: {product_name}

PACKAGING ARTWORK EXTRACTED TEXT CONTEXT:
\"\"\"
{pdf_text_summary[:3500]}
\"\"\"

SPECIFICATION VS ARTWORK ITEMS WITH TEXTUAL DIFFERENCES:
{json.dumps(candidate_items, indent=2)}

TASK:
For each item, compare the specification value with the artwork declared value:
1. Determine if the artwork text conveys the SAME intended packaging meaning as the specification, despite different words or phrasing (e.g. phrasing variations, packaging synonyms, punctuation/ampersand variations, equivalent dietary statements like 'Suitable for Vegans' vs 'suitable for vegetarians (vegan)').
2. Or determine if there is a GENUINE FACTUAL / SUBSTANTIVE MISMATCH (e.g. different ingredient percentages like 9% vs 1%, conflicting claims, conflicting storage requirements, contradictory allergen declarations, different numbers).
3. Or if the difference is ambiguous and requires human verification.

Return ONLY a valid JSON array of objects:
[
  {{
    "id": "item id matching input",
    "field_name": "Field name",
    "semantic_verdict": "SEMANTIC_MATCH" | "SUBSTANTIVE_MISMATCH" | "NEEDS_REVIEW",
    "is_equivalent_meaning": true | false,
    "confidence": "High" | "Medium" | "Low",
    "explanation": "Clear explanation of why the meaning is equivalent or why it is a substantive difference.",
    "phrasing_variation_note": "Short note summarizing the phrasing difference, or null"
  }}
]
"""
        try:
            if provider == "openai":
                return await cls._call_openai(prompt)
            elif provider == "gemini":
                return await cls._call_gemini(prompt)
            elif provider == "anthropic":
                return await cls._call_anthropic(prompt)
        except Exception as e:
            logger.warning(
                f"AI Semantic Comparison API call failed: {e}. Falling back to rule-based semantic comparison."
            )
            return cls._fallback_semantic_comparison(candidate_items)

        return cls._fallback_semantic_comparison(candidate_items)

    @classmethod
    async def analyze_semantic_differences(
        cls,
        unmatched_spec_fields: List[Dict[str, Any]],
        pdf_text_summary: str,
        product_name: str,
    ) -> List[Dict[str, Any]]:
        """
        Uses an LLM (if configured) to interpret semantic matches, explain differences,
        and assess whether missing spec fields are relevant packaging content
        ('Potentially missing from artwork — requires review').
        """
        provider = cls.get_active_provider()
        if provider == "none" or not unmatched_spec_fields:
            return cls._fallback_heuristic_analysis(unmatched_spec_fields, pdf_text_summary)

        prompt = f"""You are PackGuard AI, an expert packaging compliance and document verification system.
Product: {product_name}

PACKAGING ARTWORK EXTRACTED TEXT:
\"\"\"
{pdf_text_summary[:4000]}
\"\"\"

SPECIFICATION FIELDS TO EVALUATE:
{json.dumps(unmatched_spec_fields, indent=2)}

TASK:
For each specification field provided:
1. Determine if this information is present in the artwork with different wording, or completely missing.
2. If present in artwork, assess status: 'Match', 'Mismatch', or 'Needs Review', with clear factual explanation and artwork_value found.
3. If missing from artwork:
   - Determine whether it is standard/relevant packaging content that should potentially be added to packaging.
   - If relevant: status MUST be 'Needs Review', field_name prefixed or marked as 'Potentially missing from artwork — requires review', explain why it appears relevant based solely on the spec and packaging conventions.
   - If purely internal/operational (e.g. supplier ID, warehouse code): explain why it is likely internal and mark as 'Needs Review' or 'Not Checked'.
4. Never invent legal requirements or hallucinate text not present in the artwork.

Respond ONLY with valid JSON array of objects:
[
  {{
    "field_name": "Field name",
    "status": "Mismatch" | "Needs Review" | "Match" | "Not Checked",
    "artwork_value": "extracted text from artwork or 'Not found on artwork'",
    "explanation": "Clear, evidence-backed explanation citing specific values.",
    "is_missing_from_artwork": true | false,
    "confidence": "High" | "Medium" | "Low",
    "suggested_replacement": "exact text from specification if safe to replace, or null"
  }}
]
"""

        try:
            if provider == "openai":
                return await cls._call_openai(prompt)
            elif provider == "gemini":
                return await cls._call_gemini(prompt)
            elif provider == "anthropic":
                return await cls._call_anthropic(prompt)
        except Exception as e:
            logger.warning(f"AI Provider call failed: {e}. Falling back to deterministic rules.")
            return cls._fallback_heuristic_analysis(unmatched_spec_fields, pdf_text_summary)

        return cls._fallback_heuristic_analysis(unmatched_spec_fields, pdf_text_summary)

    @classmethod
    async def _call_openai(cls, prompt: str) -> List[Dict[str, Any]]:
        async with httpx.AsyncClient(timeout=15.0) as client:
            resp = await client.post(
                "https://api.openai.com/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {OPENAI_API_KEY}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": OPENAI_MODEL,
                    "messages": [
                        {"role": "system", "content": "You are a packaging verification expert. Return valid JSON only."},
                        {"role": "user", "content": prompt},
                    ],
                    "temperature": 0.1,
                },
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["choices"][0]["message"]["content"]
            return cls._parse_json_response(content)

    @classmethod
    async def _call_gemini(cls, prompt: str) -> List[Dict[str, Any]]:
        url = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent?key={GEMINI_API_KEY}"
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                url,
                headers={"Content-Type": "application/json"},
                json={
                    "contents": [{"parts": [{"text": prompt}]}],
                    "generationConfig": {"temperature": 0.1, "responseMimeType": "application/json"},
                },
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["candidates"][0]["content"]["parts"][0]["text"]
            return cls._parse_json_response(content)

    @classmethod
    async def _call_anthropic(cls, prompt: str) -> List[Dict[str, Any]]:
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(
                "https://api.anthropic.com/v1/messages",
                headers={
                    "x-api-key": ANTHROPIC_API_KEY,
                    "anthropic-version": "2023-06-01",
                    "content-type": "application/json",
                },
                json={
                    "model": ANTHROPIC_MODEL,
                    "max_tokens": 2048,
                    "messages": [{"role": "user", "content": prompt}],
                },
            )
            resp.raise_for_status()
            data = resp.json()
            content = data["content"][0]["text"]
            return cls._parse_json_response(content)

    @classmethod
    def _parse_json_response(cls, text: str) -> List[Dict[str, Any]]:
        text = text.strip()
        if text.startswith("```json"):
            text = text[7:]
        elif text.startswith("```"):
            text = text[3:]
        if text.endswith("```"):
            text = text[:-3]
        return json.loads(text.strip())

    @classmethod
    def _fallback_semantic_comparison(cls, candidate_items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
        """
        Rule-based semantic equivalence analyzer used when AI API is unavailable.
        Evaluates packaging synonyms, symbols, punctuation variants, and numeric consistency.
        """
        results = []
        for item in candidate_items:
            spec_val = str(item.get("spec_value") or "").strip()
            art_val = str(item.get("artwork_value") or "").strip()
            fid = item.get("id", "")
            fname = item.get("field_name", "")

            spec_nums = _extract_numbers(spec_val)
            art_nums = _extract_numbers(art_val)

            # 1. Contradictory numeric check (e.g. 9% vs 1% or 500g vs 450g)
            if spec_nums and art_nums and sorted(spec_nums) != sorted(art_nums):
                results.append({
                    "id": fid,
                    "field_name": fname,
                    "semantic_verdict": "SUBSTANTIVE_MISMATCH",
                    "is_equivalent_meaning": False,
                    "confidence": "High",
                    "explanation": f"Specification specifies numeric figures ({', '.join(spec_nums)}) which differ from artwork declaration ({', '.join(art_nums)}). This is a substantive formulation difference.",
                    "phrasing_variation_note": "Numeric mismatch",
                })
                continue

            # 2. Known packaging semantic equivalences
            spec_clean = spec_val.lower().replace("&", "and").replace("+", " ").replace("–", "-")
            art_clean = art_val.lower().replace("&", "and").replace("+", " ").replace("–", "-")

            # Vegan / Vegetarian dietary statements
            is_dietary = "dietary" in fid.lower() or "dietary" in fname.lower()
            if is_dietary and ("vegan" in spec_clean or "vegetarian" in spec_clean) and ("vegan" in art_clean or "vegetarian" in art_clean):
                results.append({
                    "id": fid,
                    "field_name": fname,
                    "semantic_verdict": "SEMANTIC_MATCH",
                    "is_equivalent_meaning": True,
                    "confidence": "High",
                    "explanation": "Phrasing variation: Artwork declares plant-based/organic dietary claims ('Suitable for Vegans') conveying equivalent dietary compliance to specification.",
                    "phrasing_variation_note": "Dietary phrasing variation",
                })
                continue

            # Storage instructions equivalence
            is_storage = "storage" in fid.lower() or "storage" in fname.lower()
            if is_storage and "cool" in spec_clean and "dry" in spec_clean and "cool" in art_clean and "dry" in art_clean:
                results.append({
                    "id": fid,
                    "field_name": fname,
                    "semantic_verdict": "SEMANTIC_MATCH",
                    "is_equivalent_meaning": True,
                    "confidence": "High",
                    "explanation": "Phrasing variation: Storage instructions declare 'cool, dry place' conditions conveying equivalent product handling requirements.",
                    "phrasing_variation_note": "Storage instructions phrasing equivalence",
                })
                continue

            # Token overlap check (Jaccard similarity on content words)
            t_spec = _clean_tokens(spec_val)
            t_art = _clean_tokens(art_val)
            if t_spec and t_art:
                intersection = t_spec.intersection(t_art)
                union = t_spec.union(t_art)
                jaccard = len(intersection) / len(union) if union else 0
                if jaccard >= 0.70 or t_spec.issubset(t_art) or t_art.issubset(t_spec):
                    results.append({
                        "id": fid,
                        "field_name": fname,
                        "semantic_verdict": "SEMANTIC_MATCH",
                        "is_equivalent_meaning": True,
                        "confidence": "Medium",
                        "explanation": f"Phrasing variation: Artwork text shares {int(jaccard*100)}% key terminology with specification and conveys equivalent packaging meaning.",
                        "phrasing_variation_note": "Lexical phrasing variation",
                    })
                    continue

            # Default: Retain original review status
            results.append({
                "id": fid,
                "field_name": fname,
                "semantic_verdict": "NEEDS_REVIEW",
                "is_equivalent_meaning": False,
                "confidence": "Low",
                "explanation": "Artwork wording contains differences that require manual review to confirm compliance.",
                "phrasing_variation_note": None,
            })

        return results

    @classmethod
    def _fallback_heuristic_analysis(
        cls,
        unmatched_spec_fields: List[Dict[str, Any]],
        pdf_text_summary: str,
    ) -> List[Dict[str, Any]]:
        """
        Deterministic, rule-based fallback when AI is not configured or unavailable.
        """
        results = []
        pdf_lower = pdf_text_summary.lower()

        for item in unmatched_spec_fields:
            fname = item["field_name"]
            val = str(item["value"]).strip()
            cat = item.get("category", "General")

            is_standard_packaging = cat in [
                "Ingredients",
                "Allergens",
                "Nutrition",
                "Weight/Measurement",
                "Identity",
                "Claims",
            ]

            if is_standard_packaging:
                results.append({
                    "field_name": f"Potentially missing from artwork — requires review: {fname}",
                    "status": "Needs Review",
                    "artwork_value": "Not found on artwork",
                    "explanation": (
                        f"The specification explicitly defines '{fname}' as '{val}', but this information was not "
                        f"found in the packaging artwork text. This information appears relevant to product packaging "
                        f"and should be reviewed to verify whether it must be declared."
                    ),
                    "is_missing_from_artwork": True,
                    "confidence": "Medium",
                    "suggested_replacement": val,
                })
            else:
                results.append({
                    "field_name": fname,
                    "status": "Not Checked",
                    "artwork_value": "Not found on artwork",
                    "explanation": (
                        f"Specification contains '{val}', but it was not identified in the artwork. "
                        f"Because this field ({fname}) may be internal or optional, it has not been marked as a definite mismatch."
                    ),
                    "is_missing_from_artwork": True,
                    "confidence": "Low",
                    "suggested_replacement": None,
                })

        return results
