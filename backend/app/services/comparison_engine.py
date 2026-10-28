"""Deterministic comparison of the content-sheet reference against extracted artwork text.

Rules enforced here:
  * No LLM, no guessing. Every status comes from explicit string/number comparison.
  * A missing extraction is never treated as proof that something is absent from the artwork.
  * A MATCH against a reference that the workbook marks Draft / unapproved is still a MATCH of the
    text, but it is annotated (review_reason) so it cannot be read as an approval.
"""
from __future__ import annotations

import logging
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Optional

from app.config import settings
from app.models import Evidence, Finding, FindingStatus, ReferenceExtraction, ReferenceField, SourceRef, Status
from app.services.excel_extractor import is_empty_value
from app.services.pdf_extractor import ArtworkData, PageData
from app.services.text_utils import (
    clean,
    collapse,
    find_phrase,
    list_diff,
    norm,
    ratio,
    snippet,
    split_top_level,
    word_diff,
)

log = logging.getLogger(__name__)

G_ID, G_ING, G_CLAIM, G_NUT, G_OTHER = (
    "Identity & weight",
    "Ingredients & allergens",
    "Claims & copy",
    "Nutrition facts",
    "Other",
)
_HEADINGS = re.compile(
    r"(INGREDIENTS|ALLERGEN INFORMATION|ALLERGENS|DIETARY INFORMATION|STORAGE)\s*:", re.I
)
_MASS = {
    "mcg": Decimal("0.000001"),
    "µg": Decimal("0.000001"),
    "ug": Decimal("0.000001"),
    "mg": Decimal("0.001"),
    "g": Decimal(1),
    "kg": Decimal(1000),
}


@dataclass
class Hit:
    page: PageData
    matched: str
    snippet: str
    bboxes: list
    source: str  # text_layer | ocr
    conf: Optional[float] = None


@dataclass
class Section:
    page: PageData
    body: str
    bbox: tuple
    fallback: bool = False


def _num(s: str) -> Optional[Decimal]:
    try:
        return Decimal(s.replace(",", "").strip())
    except InvalidOperation:
        return None


def parse_amount(s: Optional[str]):
    """'15g' -> (Decimal(15), 'g'); '166' -> (Decimal(166), ''); unparsable -> None."""
    if s is None:
        return None
    m = re.fullmatch(r"\s*([\d.,]+)\s*(mcg|µg|ug|mg|kg|g|kcal|kj|ml|l|oz|lb)?\s*", clean(s), re.I)
    if not m:
        return None
    n = _num(m.group(1))
    return None if n is None else (n, (m.group(2) or "").lower())


def amounts_equal(a, b) -> Optional[bool]:
    """True/False when comparable, None when units differ and cannot be converted unambiguously."""
    (na, ua), (nb, ub) = a, b
    if ua == ub:
        return na == nb
    if ua in _MASS and ub in _MASS:
        return na * _MASS[ua] == nb * _MASS[ub]
    return None


def parse_pct(s: Optional[str]) -> Optional[Decimal]:
    """'2.2%*' -> Decimal('2.2'); '—' / '' -> None (no %DV declared)."""
    if s is None:
        return None
    t = clean(s).replace("*", "").replace("%", "").strip()
    return _num(t) if t not in ("", "—", "-", "–") else None


class ComparisonEngine:
    def __init__(self, ref: ReferenceExtraction, art: ArtworkData):
        self.ref = ref
        self.art = art
        self.status_text = ref.status.text
        self.approved = ref.status.approved
        self._panel_cache = "unset"

    # ------------------------------------------------------------------ public
    def run(self) -> list[Finding]:
        checks = [
            self.check_identity,
            self.check_brand,
            self.check_net_weight,
            self.check_upc,
            self.check_ingredients,
            self.check_allergens,
            self.check_dietary,
            self.check_storage,
            self.check_marketing,
            self.check_claims,
            self.check_servings,
            self.check_nutrients,
            self.check_footnote,
            self.check_extra_nutrition,
            self.check_dieline_text,
            self.check_not_checked,
        ]
        out: list[Finding] = []
        for fn in checks:
            try:
                out.extend(fn())
            except Exception:
                log.exception("check %s failed", fn.__name__)
                out.append(
                    Finding(
                        id=f"error.{fn.__name__}",
                        field_name=fn.__name__.replace("check_", "").replace("_", " ").title(),
                        group=G_OTHER,
                        status=FindingStatus.NEEDS_REVIEW,
                        explanation="This check could not be completed because of an internal processing error.",
                        review_reason="Check failed; review this item manually.",
                    )
                )
        seen: set = set()
        for f in out:  # guarantee unique ids
            base, n = f.id, 2
            while f.id in seen:
                f.id, n = f"{base}.{n}", n + 1
            seen.add(f.id)
        return out

    # ------------------------------------------------------------------ helpers
    def _f(self, key: str) -> Optional[ReferenceField]:
        fld = self.ref.fields.get(key)
        return fld if fld and not is_empty_value(fld.value) else None

    def _finding(
        self,
        id,
        field,
        group,
        status,
        ref: Optional[ReferenceField] = None,
        *,
        ref_value=None,
        ref_source: Optional[SourceRef] = None,
        artwork_value=None,
        evidence=None,
        explanation="",
        review_reason=None,
        limitations=None,
    ) -> Finding:
        evidence = evidence or []
        reasons = [review_reason] if review_reason else []
        expl = explanation
        if ref is not None:
            ref_value = ref.value if ref_value is None else ref_value
            ref_source = ref_source or ref.source
        if status == Status.MATCH and self.approved is not True:
            who = self.status_text or "of unknown approval status"
            reasons.append(f"The reference sheet is “{who}”; this agreement is not an approval.")
        if status == Status.MATCH and ref is not None and ref.flagged:
            reasons.append("The workbook flags this reference value for verification (see reference note).")
        
        status_enum = FindingStatus.from_any(status)

        return Finding(
            id=id,
            field_name=field,
            group=group,
            status=status_enum,
            reference_value=ref_value,
            reference_source=ref_source,
            reference_status=self.status_text,
            reference_approved=self.approved,
            reference_note=(ref.note if ref else None),
            reference_flagged=bool(ref and ref.flagged),
            artwork_value=collapse(artwork_value) if artwork_value else artwork_value,
            evidence=evidence,
            explanation=expl.strip(),
            review_reason=" ".join(reasons) or None,
            limitations=limitations or [],
        )

    def _missing_ref(self, id, field, group, what) -> Finding:
        return self._finding(
            id,
            field,
            group,
            Status.NEEDS_REVIEW,
            explanation=f"No {what} could be identified in the content sheet, so there is nothing reliable to compare against.",
            review_reason="Reference value missing or not recognised in the workbook.",
        )

    def _ev(
        self,
        page: PageData,
        matched: str,
        text: Optional[str] = None,
        *,
        label=None,
        bboxes=None,
        source=None,
        conf=None,
        snip=None,
    ) -> Evidence:
        return Evidence(
            page=page.number,
            snippet=snip if snip is not None else collapse(matched)[:420],
            bboxes=[list(map(float, b)) for b in (bboxes or [])],
            source=source or ("ocr" if page.text_source == "ocr" else "text_layer"),
            ocr_confidence=conf if conf is not None else (page.ocr_confidence if page.text_source == "ocr" else None),
            label=label,
        )

    def _block_bbox(self, page: PageData, matched: str) -> list:
        for b in page.blocks:
            if find_phrase(b.text, matched):
                return [b.bbox]
        return []

    def _reliable(self, page: PageData) -> tuple[bool, Optional[str]]:
        if page.text_source == "ocr" and (page.ocr_confidence or 0) < settings.ocr_min_confidence:
            return False, f"Page {page.number} text came from OCR with low mean confidence ({page.ocr_confidence:.0f}/100)."
        return True, None

    def _ocr_note(self, page: PageData) -> list[str]:
        return (
            [f"Page {page.number} text comes from OCR (mean confidence {page.ocr_confidence:.0f}/100)."]
            if page.text_source == "ocr"
            else []
        )

    def _find(self, phrase: str, *, ocr: bool = False) -> Optional[Hit]:
        for page in self.art.pages:
            if page.text_source == "none":
                continue
            span = find_phrase(page.text, phrase)
            if span:
                matched = page.text[span[0]:span[1]]
                bbs = self.art.locate(page.number, collapse(matched)) or self._block_bbox(page, matched)
                return Hit(
                    page,
                    matched,
                    snippet(page.text, *span),
                    bbs,
                    "ocr" if page.text_source == "ocr" else "text_layer",
                    page.ocr_confidence if page.text_source == "ocr" else None,
                )
        return self._find_ocr(phrase) if ocr else None

    def _find_ocr(self, phrase: str) -> Optional[Hit]:
        toks = [t for t in re.split(r"\s+", clean(phrase).lower()) if t]
        toks = [re.sub(r"[^\w]", "", t) for t in toks]
        toks = [t for t in toks if t]
        if not toks:
            return None
        for page in self.art.pages:
            if page.text_source == "ocr":
                continue  # already searched as page text
            res = self.art.ocr(page.number)
            if res.error or not res.words:
                continue
            wt = [re.sub(r"[^\w]", "", w.text.lower()) for w in res.words]
            n = len(toks)
            for i in range(len(wt) - n + 1):
                if wt[i:i + n] == toks:
                    ws = res.words[i:i + n]
                    conf = sum(w.conf for w in ws) / n
                    bb = [
                        min(w.bbox[0] for w in ws),
                        min(w.bbox[1] for w in ws),
                        max(w.bbox[2] for w in ws),
                        max(w.bbox[3] for w in ws),
                    ]
                    ctx = " ".join(w.text for w in res.words[max(0, i - 3):i + n + 3])
                    return Hit(page, " ".join(w.text for w in ws), ctx, [bb], "ocr", conf)
        return None

    def _ocr_unavailable_reason(self) -> Optional[str]:
        for p in self.art.pages:
            if p.text_source == "ocr":
                continue
            r = self.art.ocr(p.number)
            if r.error:
                return r.error
        return None

    def _section(self, heading: str) -> Optional[Section]:
        pat = re.compile(heading, re.I)
        for page in self.art.pages:
            for b in page.blocks:
                m = pat.search(b.text)
                if m:
                    body = b.text[m.end():]
                    n = _HEADINGS.search(body)
                    if n:
                        body = body[:n.start()]
                    return Section(page, collapse(body), b.bbox)
        for page in self.art.pages:  # fallback: page text (less precise)
            m = pat.search(page.text)
            if m:
                body = page.text[m.end():]
                n = _HEADINGS.search(body)
                body = body[:n.start()] if n else body[:600]
                return Section(page, collapse(body), (), fallback=True)
        return None

    def _best_block(self, text: str, min_ratio: float = 0.55):
        best, br = None, 0.0
        for page in self.art.pages:
            for b in page.blocks:
                if len(norm(b.text)) < 8:
                    continue
                r = ratio(text, b.text)
                if r > br:
                    best, br = (page, b), r
        return (best, br) if best and br >= min_ratio else (None, br)

    @staticmethod
    def _strip_heading(t: str) -> str:
        return re.sub(
            r"^\s*(ingredients|allergen information|allergens?|dietary information)\s*:\s*", "", t, flags=re.I
        )

    # ------------------------------------------------------------------ generic text-field comparison
    def _compare_text(
        self, id, field, group, key, heading: Optional[str] = None, *, strip_star=False, as_list=False
    ) -> list[Finding]:
        ref = self._f(key)
        if not ref:
            return [self._missing_ref(id, field, group, field.lower())]
        r_txt = self._strip_heading(ref.value)
        if strip_star:
            r_txt = r_txt.lstrip("* ").strip()
        lims: list[str] = []
        page = bbs = None
        art_txt = ""
        how = ""
        if heading:
            sec = self._section(heading)
            if sec:
                page, art_txt, bbs = sec.page, sec.body, [sec.bbox] if sec.bbox else []
                how = "section"
                if sec.fallback:
                    lims.append("Section boundaries were estimated from page text; verify full text on the artwork.")
        if page is None:
            hit = self._find(r_txt.lstrip("* "))
            if hit:
                page, art_txt, bbs, how = hit.page, hit.matched, hit.bboxes, "exact"
            else:
                got, br = self._best_block(r_txt)
                if got:
                    page, blk = got
                    art_txt, bbs, how = blk.text, [blk.bbox], "block"
        if page is None:
            reason = self._ocr_unavailable_reason()
            return [
                self._finding(
                    id,
                    field,
                    group,
                    Status.NEEDS_REVIEW,
                    ref,
                    explanation="No matching text was found in the artwork text layer. This does not prove the text is absent: it may be outlined, in an image, or extracted differently.",
                    review_reason="Artwork text could not be located reliably.",
                    limitations=["Text embedded in images or converted to outlines cannot be read without OCR."]
                    + ([reason] if reason else []),
                )
            ]
        a_txt = self._strip_heading(art_txt)
        if strip_star:
            a_txt = a_txt.lstrip("* ").strip()
        ok, why = self._reliable(page)
        lims += self._ocr_note(page)
        ev = [self._ev(page, collapse(a_txt), label=f"{field} text", bboxes=bbs)]
        same = norm(r_txt) == norm(a_txt)
        if same and ok:
            case_only = clean(collapse(r_txt)) != clean(collapse(a_txt))
            return [
                self._finding(
                    id,
                    field,
                    group,
                    Status.MATCH,
                    ref,
                    artwork_value=collapse(a_txt),
                    evidence=ev,
                    explanation=f"The reference text and the artwork text are identical on page {page.number}"
                    + (" (differences in capitalisation and whitespace ignored)." if case_only else "."),
                    limitations=lims,
                )
            ]
        if same and not ok:
            return [
                self._finding(
                    id,
                    field,
                    group,
                    Status.NEEDS_REVIEW,
                    ref,
                    artwork_value=collapse(a_txt),
                    evidence=ev,
                    explanation="Text agrees, but it was read by low-confidence OCR.",
                    review_reason=why,
                    limitations=lims,
                )
            ]
        if as_list:
            diffs, order_only = list_diff(split_top_level(r_txt), split_top_level(a_txt))
            if order_only:
                diffs = ["Same items in a different order: " + "; ".join(diffs)]
        else:
            diffs = word_diff(r_txt, a_txt)
        if how == "block" and ratio(r_txt, a_txt) < 0.55:
            return [
                self._finding(
                    id,
                    field,
                    group,
                    Status.NEEDS_REVIEW,
                    ref,
                    artwork_value=collapse(a_txt),
                    evidence=ev,
                    explanation="Only a weakly similar block of artwork text was found, so a reliable comparison is not possible.",
                    review_reason="Low text similarity; matching artwork text may not have been identified.",
                    limitations=lims,
                )
            ]
        expl = f"The artwork text on page {page.number} differs from the reference: " + "; ".join(diffs) + "."
        if ref.flagged:
            expl += " The workbook itself flags this reference value for verification, so difference may lie in reference rather than artwork."
        if self.approved is not True:
            expl += f" The reference is “{self.status_text or 'of unknown approval status'}”."
        return [
            self._finding(
                id,
                field,
                group,
                Status.MISMATCH,
                ref,
                artwork_value=collapse(a_txt),
                evidence=ev,
                explanation=expl,
                review_reason=("Low-confidence OCR text; verify manually." if not ok else None),
                limitations=lims,
            )
        ]

    # ------------------------------------------------------------------ identity / weight
    def check_identity(self) -> list[Finding]:
        out: list[Finding] = []
        legal, pname = self._f("legal_name"), self._f("product_name")
        for key, ref, fid, fname in (
            ("legal_name", legal, "identity.statement", "Statement of Identity"),
            ("product_name", pname, "identity.product_name", "Product Name"),
        ):
            if not ref:
                out.append(self._missing_ref(fid, fname, G_ID, fname.lower()))
                continue
            if key == "legal_name":
                parts = [p for p in (collapse(x) for x in re.split(r"[—–|:]|\s-\s", ref.value)) if p]
            else:
                parts = [w for w in ref.value.split() if w]
            found, missing = [], []
            for p in parts:
                h = self._find(p)
                (found if h else missing).append((p, h))
            if missing:
                out.append(
                    self._finding(
                        fid,
                        fname,
                        G_ID,
                        Status.NEEDS_REVIEW,
                        ref,
                        artwork_value=(", ".join(p for p, _ in found) or None),
                        evidence=[self._ev(h.page, h.matched, bboxes=h.bboxes, snip=h.snippet) for _, h in found if h],
                        explanation=f"Not found in the text layer: {', '.join('“'+p+'”' for p, _ in missing)}. Absence from the text layer does not prove it is absent from the artwork (it may be a graphic).",
                        review_reason="Part of the name could not be located in artwork text.",
                        limitations=["Logos and stylised lettering are often images, not text."],
                    )
                )
                continue
            ok = all(self._reliable(h.page)[0] for _, h in found)
            ev = [self._ev(h.page, h.matched, bboxes=h.bboxes, snip=h.snippet, label=p) for p, h in found]
            art_val = " + ".join(h.matched.upper() if key == "legal_name" else h.matched for _, h in found)
            out.append(
                self._finding(
                    fid,
                    fname,
                    G_ID,
                    Status.MATCH if ok else Status.NEEDS_REVIEW,
                    ref,
                    artwork_value=art_val,
                    evidence=ev,
                    explanation=(
                        "Each element of the reference ("
                        + ", ".join("“" + p + "”" for p, _ in found)
                        + ") was found in the artwork text, as separate text elements; they were not found as one contiguous phrase."
                        if len(found) > 1
                        else f"“{found[0][0]}” was found in the artwork text."
                    ),
                    review_reason=None if ok else "Found only via low-confidence OCR.",
                    limitations=["Only the text layer is compared; visual size and placement of the name are not evaluated."],
                )
            )
        return out

    def check_brand(self) -> list[Finding]:
        ref = self._f("brand")
        if not ref:
            return [self._missing_ref("identity.brand", "Brand", G_ID, "brand")]
        h = self._find(ref.value, ocr=True)
        if not h:
            return [
                self._finding(
                    "identity.brand",
                    "Brand",
                    G_ID,
                    Status.NEEDS_REVIEW,
                    ref,
                    explanation="The brand name was not found in the artwork text or OCR. Logos are usually graphics, so this does not prove the brand is missing.",
                    review_reason="Brand not located in text.",
                    limitations=["Brand logos are not visually verified."],
                )
            ]
        ok = h.source == "text_layer" or (h.conf or 0) >= settings.ocr_min_confidence
        return [
            self._finding(
                "identity.brand",
                "Brand",
                G_ID,
                Status.MATCH if ok else Status.NEEDS_REVIEW,
                ref,
                artwork_value=h.matched,
                evidence=[self._ev(h.page, h.matched, bboxes=h.bboxes, snip=h.snippet, source=h.source, conf=h.conf)],
                explanation=f"The brand name appears in artwork text on page {h.page.number}.",
                review_reason=None if ok else "Found only via low-confidence OCR.",
                limitations=[
                    "The text match may come from a secondary mention (e.g. a producer line); brand logo graphic itself is not verified."
                ],
            )
        ]

    def _weights_labelled(self):
        out = []
        for page in self.art.pages:
            for m in re.finditer(
                r"net\s*(?:wt|weight|contents?)\.?\s*:?\s*(\d+(?:[.,]\d+)?)\s*(kg|g|ml|l|oz|lb)\b", page.text, re.I
            ):
                out.append((page, m))
        return out

    def check_net_weight(self) -> list[Finding]:
        fid, fname = "identity.net_weight", "Net Weight"
        ref = self._f("net_weight")
        if not ref:
            return [self._missing_ref(fid, fname, G_ID, "net weight")]
        ra = parse_amount(ref.value.replace(" ", ""))
        if not ra:
            # Try parsing first part if multi-unit like "12 oz (340g)"
            m_multi = re.search(r"(\d+(?:\.\d+)?)\s*(kg|g|ml|l|oz|lb)\b", ref.value, re.I)
            if m_multi:
                ra = parse_amount(m_multi.group(0))
            if not ra:
                return [
                    self._finding(
                        fid,
                        fname,
                        G_ID,
                        Status.NEEDS_REVIEW,
                        ref,
                        explanation="The reference net weight is not in a recognised numeric format.",
                        review_reason="Reference value could not be parsed.",
                    )
                ]
        lab = self._weights_labelled()
        if lab:
            page, m = lab[0]
            aa = parse_amount(m.group(1) + m.group(2))
            eq = amounts_equal(ra, aa) if aa else None
            ev = [
                self._ev(
                    page,
                    m.group(0),
                    bboxes=self.art.locate(page.number, collapse(m.group(0))) or self._block_bbox(page, m.group(0)),
                    label="labelled net weight",
                )
            ]
            if eq is None:
                return [
                    self._finding(
                        fid,
                        fname,
                        G_ID,
                        Status.NEEDS_REVIEW,
                        ref,
                        artwork_value=m.group(0),
                        evidence=ev,
                        explanation="Units differ and cannot be converted unambiguously.",
                        review_reason="Unit mismatch.",
                    )
                ]
            st = Status.MATCH if eq else Status.MISMATCH
            return [
                self._finding(
                    fid,
                    fname,
                    G_ID,
                    st,
                    ref,
                    artwork_value=collapse(m.group(0)),
                    evidence=ev,
                    explanation=(
                        "The labelled net weight on the artwork equals the reference."
                        if eq
                        else f"The labelled net weight on the artwork ({collapse(m.group(0))}) differs from the reference ({ref.value})."
                    ),
                )
            ]
        # no labelled declaration: look for reference value as a standalone weight statement
        standalone = []
        for page in self.art.pages:
            for b in page.blocks:
                t = collapse(b.text)
                m = re.fullmatch(r"(\d+(?:[.,]\d+)?)\s*(kg|g|ml|l|oz|lb)", t, re.I)
                if m:
                    standalone.append((page, b, t, parse_amount(m.group(1) + m.group(2))))
        hits = [s for s in standalone if s[3] and amounts_equal(ra, s[3])]
        if hits:
            page, b, t, _ = hits[0]
            return [
                self._finding(
                    fid,
                    fname,
                    G_ID,
                    Status.MATCH,
                    ref,
                    artwork_value=t,
                    evidence=[self._ev(page, t, bboxes=[b.bbox], label="standalone weight statement")],
                    explanation=f"A standalone weight statement equal to the reference ({ref.value}) was found on page {page.number}.",
                    limitations=[
                        "No “Net Wt” label was found next to it; other weight-like figures on artwork were not treated as net weight."
                    ],
                )
            ]
        cand = ", ".join(sorted({s[2] for s in standalone})) or "none"
        return [
            self._finding(
                fid,
                fname,
                G_ID,
                Status.NEEDS_REVIEW,
                ref,
                explanation=f"No labelled net-weight declaration and no standalone weight equal to {ref.value} was found. Other standalone weight-like text: {cand}. Without a net-weight label the system cannot tell whether any of these is the declared net weight.",
                review_reason="Net weight could not be identified reliably on the artwork.",
            )
        ]

    def check_upc(self) -> list[Finding]:
        ref = self._f("upc")
        if not ref:
            return []
        digits = re.sub(r"\D", "", ref.value)
        if not digits:
            return []
        runs = re.compile(r"\d(?:[ \-]?\d){7,}")

        def scan(text: str):
            for m in runs.finditer(text):
                if re.sub(r"\D", "", m.group(0)) == digits:
                    return m
            return None

        lim = ["Only human-readable digits are checked. The barcode symbol is not decoded or graded."]
        for page in self.art.pages:
            m = scan(page.text)
            if m:
                return [
                    self._finding(
                        "identity.upc",
                        "UPC / barcode digits",
                        G_ID,
                        Status.MATCH,
                        ref,
                        artwork_value=collapse(m.group(0)),
                        evidence=[
                            self._ev(page, m.group(0), bboxes=self.art.locate(page.number, collapse(m.group(0))))
                        ],
                        explanation="The reference digits appear in the artwork text.",
                        limitations=lim,
                    )
                ]
        for page in self.art.pages:
            if page.text_source == "ocr":
                continue
            res = self.art.ocr(page.number)
            if res.error:
                lim.append(res.error)
                continue
            txt = " ".join(w.text for w in res.words)
            m = scan(txt)
            if m:
                conf = res.mean_conf
                ok = (conf or 0) >= settings.ocr_min_confidence
                return [
                    self._finding(
                        "identity.upc",
                        "UPC / barcode digits",
                        G_ID,
                        Status.MATCH if ok else Status.NEEDS_REVIEW,
                        ref,
                        artwork_value=collapse(m.group(0)),
                        evidence=[self._ev(page, m.group(0), source="ocr", conf=conf)],
                        explanation="The reference digits were found by OCR.",
                        limitations=lim,
                    )
                ]
        return [
            self._finding(
                "identity.upc",
                "UPC / barcode digits",
                G_ID,
                Status.NEEDS_REVIEW,
                ref,
                explanation="The reference UPC digits were not found in the text layer or by OCR. The barcode digits are probably part of a graphic; this does not prove they are wrong.",
                review_reason="Barcode digits could not be read; verify the barcode manually.",
                limitations=lim,
            )
        ]

    # ------------------------------------------------------------------ text fields
    def check_ingredients(self):
        return self._compare_text(
            "text.ingredients", "Ingredients", G_ING, "ingredients", r"INGREDIENTS\s*:", as_list=True
        )

    def check_allergens(self):
        return self._compare_text(
            "text.allergens", "Allergen information", G_ING, "allergens", r"ALLERGEN(?:S| INFORMATION)\s*:"
        )

    def check_storage(self):
        return self._compare_text("text.storage", "Storage instructions", G_CLAIM, "storage")

    def check_footnote(self):
        return self._compare_text(
            "nutrition.footnote",
            "Nutrition panel % Daily Value statement",
            G_NUT,
            "nutrition_footnote",
            strip_star=True,
        )

    def check_marketing(self):
        return self._compare_text("text.marketing", "Marketing copy", G_CLAIM, "marketing_copy")

    def check_dietary(self) -> list[Finding]:
        fid, fname = "text.dietary", "Dietary information"
        ref = self._f("dietary")
        if not ref:
            return [self._missing_ref(fid, fname, G_CLAIM, "dietary information")]
        sentences = [s for s in re.split(r"(?<=[.!?])\s+", collapse(ref.value)) if s]
        sec = self._section(r"DIETARY INFORMATION\s*:")
        results, evs, arts = [], [], []
        for s in sentences:
            hit = self._find(s)
            if hit:
                results.append(("ok", s, hit.matched))
                arts.append(hit.matched)
                evs.append(self._ev(hit.page, hit.matched, bboxes=hit.bboxes, snip=hit.snippet))
                continue
            cands = []
            if sec:
                cands.append((sec.page, sec.body, [sec.bbox] if sec.bbox else []))
            for p in self.art.pages:
                cands += [(p, b.text, [b.bbox]) for b in p.blocks if len(norm(b.text)) > 12]
            best = max(cands, key=lambda c: ratio(s, self._strip_heading(c[1])), default=None)
            if best and ratio(s, self._strip_heading(best[1])) >= 0.6:
                a = collapse(self._strip_heading(best[1]))
                results.append(("diff", s, a))
                arts.append(a)
                evs.append(self._ev(best[0], a, bboxes=best[2]))
            else:
                results.append(("missing", s, None))
        diffs = [f"“{s}” → " + "; ".join(word_diff(s, a)) for k, s, a in results if k == "diff"]
        missing = [s for k, s, _ in results if k == "missing"]
        av = " | ".join(arts) or None
        if diffs:
            return [
                self._finding(
                    fid,
                    fname,
                    G_CLAIM,
                    Status.MISMATCH,
                    ref,
                    artwork_value=av,
                    evidence=evs,
                    explanation="Dietary wording differs between reference and artwork. "
                    + " ".join(diffs)
                    + (f" Not found at all: {', '.join('“'+m+'”' for m in missing)}." if missing else ""),
                )
            ]
        if missing:
            return [
                self._finding(
                    fid,
                    fname,
                    G_CLAIM,
                    Status.NEEDS_REVIEW,
                    ref,
                    artwork_value=av,
                    evidence=evs,
                    explanation=f"Not found in artwork text: {', '.join('“'+m+'”' for m in missing)}.",
                    review_reason="Dietary statement could not be located reliably.",
                )
            ]
        return [
            self._finding(
                fid,
                fname,
                G_CLAIM,
                Status.MATCH,
                ref,
                artwork_value=av,
                evidence=evs,
                explanation="All reference dietary statements were found verbatim in the artwork text.",
            )
        ]

    # ------------------------------------------------------------------ claims
    def check_claims(self) -> list[Finding]:
        ref = self._f("claims")
        if not ref:
            return [self._missing_ref("claims", "Claims & certifications", G_CLAIM, "claims")]
        parts = [p.strip() for p in re.split(r";", ref.value) if p.strip()] or [ref.value]
        out: list[Finding] = []
        for p in parts:
            base = re.sub(r"\(.*?\)", "", p)
            terms = [collapse(t) for t in re.split(r"/", base) if collapse(t)]
            terms = [re.sub(r"\s+mark$", "", t, flags=re.I) for t in terms]
            fid = "claims." + re.sub(r"[^a-z0-9]+", "_", p.lower()).strip("_")[:40]
            hit = None
            for t in terms:
                hit = self._find(t, ocr=True)
                if hit:
                    break
            sub = ref.model_copy(update={"value": p})
            lim = [
                "Claim presence is checked as text only; wording, size, placement and certification marks are not validated."
            ]
            if not hit:
                why = self._ocr_unavailable_reason()
                out.append(
                    self._finding(
                        fid,
                        f"Claim: {p}",
                        G_CLAIM,
                        Status.NEEDS_REVIEW,
                        sub,
                        explanation="Not found in artwork text layer or by OCR. Certification marks are often graphics, so this does not prove claim is absent.",
                        review_reason="Claim could not be located; verify visually.",
                        limitations=lim + ([why] if why else []),
                    )
                )
                continue
            ok = hit.source == "text_layer" or (hit.conf or 0) >= settings.ocr_min_confidence
            if hit.source == "ocr":
                lim.append(f"Found by OCR (word confidence {hit.conf:.0f}/100), not in text layer.")
            out.append(
                self._finding(
                    fid,
                    f"Claim: {p}",
                    G_CLAIM,
                    Status.MATCH if ok else Status.NEEDS_REVIEW,
                    sub,
                    artwork_value=hit.matched,
                    evidence=[
                        self._ev(
                            hit.page,
                            hit.matched,
                            bboxes=hit.bboxes,
                            snip=hit.snippet,
                            source=hit.source,
                            conf=hit.conf,
                        )
                    ],
                    explanation=f"“{hit.matched}” was found on page {hit.page.number}"
                    + (" by OCR." if hit.source == "ocr" else " in text layer."),
                    review_reason=None if ok else "Found only with low OCR confidence.",
                    limitations=lim,
                )
            )
        return out

    # ------------------------------------------------------------------ nutrition
    def _panel(self):
        if self._panel_cache != "unset":
            return self._panel_cache
        rx = re.compile(
            r"Nutrition\s+Facts\s+(\d+)\s+servings?\s+per\s+(?:container|package)(.*?)(?:general\s+nutrition\s+advice\.?|\Z)",
            re.I | re.S,
        )
        self._panel_cache = None
        for page in self.art.pages:
            m = rx.search(page.text)
            if m:
                self._panel_cache = (page, m)
                break
        return self._panel_cache

    def _no_panel(self, id, field, ref_value, ref_src, ref: Optional[ReferenceField] = None):
        return self._finding(
            id,
            field,
            G_NUT,
            Status.NEEDS_REVIEW,
            ref,
            ref_value=ref_value,
            ref_source=ref_src,
            explanation="No US “Nutrition Facts” panel (with “servings per container”) was found in artwork text, so this value cannot be compared.",
            review_reason="Artwork nutrition panel not located.",
            limitations=["The panel may be an image or outlined text."],
        )

    def check_servings(self) -> list[Finding]:
        out: list[Finding] = []
        panel = self._panel()
        ref = self._f("servings_per_container")
        if ref:
            if not panel:
                out.append(self._no_panel("nutrition.servings", "Servings per container", ref.value, ref.source, ref))
            else:
                page, m = panel
                ra, aa = parse_amount(ref.value), (Decimal(m.group(1)), "")
                st = Status.NEEDS_REVIEW if not ra else (Status.MATCH if amounts_equal(ra, aa) else Status.MISMATCH)
                txt = collapse(re.search(r"\d+\s+servings?\s+per\s+(?:container|package)", m.group(0), re.I).group(0))
                out.append(
                    self._finding(
                        "nutrition.servings",
                        "Servings per container",
                        G_NUT,
                        st,
                        ref,
                        artwork_value=m.group(1),
                        evidence=[self._ev(page, txt, bboxes=self.art.locate(page.number, txt))],
                        explanation=(
                            "Servings per container agree."
                            if st == Status.MATCH
                            else f"Reference says {ref.value}; artwork says {m.group(1)}."
                            if st == Status.MISMATCH
                            else "The reference value could not be parsed."
                        ),
                        review_reason=None if ra else "Reference value not numeric.",
                    )
                )
        ss = self._f("serving_size") or self.ref.fields.get("serving_size")
        if ss:
            if not panel:
                out.append(self._no_panel("nutrition.serving_size", "Serving size", ss.value, ss.source, ss))
            else:
                page, m = panel
                mm = re.search(r"Serving\s+size\s*[:\-]?\s*([^\n]+)", m.group(0), re.I)
                art = collapse(mm.group(1)) if mm and "amount per" not in mm.group(1).lower() else None
                ev = (
                    [self._ev(page, "Serving size " + art, bboxes=self.art.locate(page.number, "Serving size " + art))]
                    if art
                    else []
                )
                no_unit = art is not None and re.fullmatch(r"[\d.,]+", art) is not None
                if ss.flagged or parse_amount(ss.value) is None:
                    out.append(
                        self._finding(
                            "nutrition.serving_size",
                            "Serving size",
                            G_NUT,
                            Status.NEEDS_REVIEW,
                            ss,
                            artwork_value=art,
                            evidence=ev,
                            explanation="The reference serving size is itself marked as unreliable or is not a usable value"
                            + (f", and artwork text shows “{art}”" + (" with no unit" if no_unit else "") if art else "")
                            + ". A reliable comparison is not possible.",
                            review_reason="Reference serving size is uncertain; confirm it against the native art file.",
                            limitations=["Unit may be rendered as a graphic or outside extracted text."] if no_unit else [],
                        )
                    )
                else:
                    ra, aa = parse_amount(ss.value), parse_amount(art or "")
                    eq = amounts_equal(ra, aa) if (ra and aa) else None
                    st = Status.NEEDS_REVIEW if eq is None else (Status.MATCH if eq else Status.MISMATCH)
                    out.append(
                        self._finding(
                            "nutrition.serving_size",
                            "Serving size",
                            G_NUT,
                            st,
                            ss,
                            artwork_value=art,
                            evidence=ev,
                            explanation={
                                Status.MATCH: "Serving size agrees.",
                                Status.MISMATCH: f"Reference {ss.value} vs artwork {art}.",
                                Status.NEEDS_REVIEW: "Serving size could not be compared (missing or unit-less on one side).",
                            }[st],
                            review_reason=None if eq is not None else "Serving size not comparable.",
                        )
                    )
        return out

    def _nutrient_rx(self, label: str):
        amt = r"(?P<amt>[\d.,]+\s?(?:mcg|µg|mg|kcal|g)?)(?![A-Za-z])"
        pct = r"\s*(?P<pct>[\d.]+\s?%)?"
        if re.search(r"added\s+sugars?", label, re.I):
            return re.compile(r"Incl(?:udes|\.)?\s*(?P<amt>[\d.,]+\s?(?:mcg|mg|g))\s*Added\s+Sugars?" + pct, re.I)
        core = r"\s+".join(re.escape(w) for w in label.split())
        return re.compile(r"(?<![A-Za-z])" + core + r"\s*" + amt + pct, re.I)

    def check_nutrients(self) -> list[Finding]:
        out: list[Finding] = []
        panel = self._panel()
        for n in self.ref.nutrition:
            fid, fname = f"nutrition.{n.key}", n.label
            rv = " / ".join(x for x in (n.amount, n.daily_value) if x is not None) or None
            rsrc = n.amount_source or n.label_source
            if n.amount is None or parse_amount(n.amount) is None:
                out.append(
                    self._finding(
                        fid,
                        fname,
                        G_NUT,
                        Status.NEEDS_REVIEW,
                        ref_value=rv,
                        ref_source=rsrc,
                        explanation="The reference amount is missing or not in a recognised numeric format.",
                        review_reason="Reference value could not be parsed.",
                    )
                )
                continue
            if not panel:
                out.append(self._no_panel(fid, fname, rv, rsrc))
                continue
            page, pm = panel
            m = self._nutrient_rx(n.label).search(pm.group(0))
            if not m:
                out.append(
                    self._finding(
                        fid,
                        fname,
                        G_NUT,
                        Status.NEEDS_REVIEW,
                        ref_value=rv,
                        ref_source=rsrc,
                        explanation=f"“{n.label}” was not found in artwork Nutrition Facts panel text. This does not prove it is absent from the artwork.",
                        review_reason="Nutrient not located in artwork text.",
                    )
                )
                continue
            a_amt, a_pct = collapse(m.group("amt")), (collapse(m.group("pct")) if m.group("pct") else None)
            matched = collapse(m.group(0))
            ev = [
                self._ev(
                    page,
                    matched,
                    bboxes=self.art.locate(page.number, matched) or self._block_bbox(page, matched),
                    label=n.label,
                )
            ]
            aval = a_amt + (f" / {a_pct}" if a_pct else "")
            ra, aa = parse_amount(n.amount), parse_amount(a_amt)
            eq = amounts_equal(ra, aa) if aa else None
            rp, ap = parse_pct(n.daily_value), parse_pct(a_pct)
            pct_eq = rp == ap
            lims = []
            if n.daily_value and "*" in n.daily_value:
                lims.append(
                    "The reference %DV carries a trailing “*” whose meaning is not defined in workbook; only the number was compared."
                )
            if eq is None:
                st, ex, rr = (
                    Status.NEEDS_REVIEW,
                    f"Units differ ({n.amount} vs {a_amt}) and cannot be converted unambiguously.",
                    "Unit mismatch.",
                )
            elif eq and pct_eq:
                st, ex, rr = (
                    Status.MATCH,
                    "Amount and % Daily Value agree"
                    + (" (no % Daily Value declared on either side)." if rp is None else "."),
                    None,
                )
            else:
                bits = []
                if not eq:
                    bits.append(f"amount: reference {n.amount} vs artwork {a_amt}")
                if not pct_eq:
                    bits.append(f"% Daily Value: reference {n.daily_value or 'none'} vs artwork {a_pct or 'none'}")
                st, ex, rr = Status.MISMATCH, "Differs — " + "; ".join(bits) + ".", None
            out.append(
                self._finding(
                    fid,
                    fname,
                    G_NUT,
                    st,
                    ref_value=rv,
                    ref_source=rsrc,
                    artwork_value=aval,
                    evidence=ev,
                    explanation=ex,
                    review_reason=rr,
                    limitations=lims + self._ocr_note(page),
                )
            )
            f = out[-1]
            f.reference_status, f.reference_approved = self.status_text, self.approved
            if st == Status.MATCH and self.approved is not True:
                f.review_reason = f"The reference sheet is “{self.status_text or 'of unknown approval status'}”; this agreement is not an approval."
        return out

    # ------------------------------------------------------------------ additional observations
    def check_extra_nutrition(self) -> list[Finding]:
        evs = []
        for page in self.art.pages:
            despaced = re.sub(r"\s+", "", page.text)
            m = re.search(r"typicalvaluesper100g", despaced, re.I)
            if m:
                sp = re.search(
                    r"T\s*y\s*p\s*i\s*c\s*a\s*l\s+V\s*a\s*l\s*u\s*e\s*s\s+p\s*e\s*r\s*1\s*0\s*0\s*g", page.text, re.I
                )
                if sp:
                    t = collapse(page.text[sp.start():sp.end() + 120])
                    evs.append(self._ev(page, t, bboxes=self._block_bbox(page, "Typical") or [], label="per-100g table"))
            for km in re.finditer(r"\d+\s?kJ", page.text, re.I):
                evs.append(
                    self._ev(
                        page,
                        collapse(page.text[max(0, km.start() - 25):km.end() + 20]),
                        bboxes=self.art.locate(page.number, km.group(0)),
                        label="kJ/kcal figure",
                    )
                )
                break
        if not evs:
            return []
        return [
            self._finding(
                "nutrition.additional_declarations",
                "Additional nutrition declarations on artwork",
                G_NUT,
                Status.NEEDS_REVIEW,
                artwork_value="; ".join(e.label or "" for e in evs),
                evidence=evs,
                explanation="The artwork text contains nutrition information in other formats (e.g. per-100g table and/or kJ/kcal figures) in addition to the US Nutrition Facts panel. Content sheet has no reference values for these, so they were not compared.",
                review_reason="Unreferenced nutrition declarations present; confirm they are intended for this market/artwork.",
                limitations=["Text may be present in PDF but hidden, overlapped or on non-printing layer; layer visibility is not analysed."],
            )
        ]

    def check_dieline_text(self) -> list[Finding]:
        rx = re.compile(
            r"Art orientation|Copy free|Principal Display Panel|(?:Front|Back|Left|Right|Bottom) panel", re.I
        )
        evs, seen = [], set()
        for page in self.art.pages:
            for m in rx.finditer(page.text):
                k = m.group(0).lower()
                if k in seen:
                    continue
                seen.add(k)
                evs.append(
                    self._ev(
                        page,
                        m.group(0),
                        bboxes=self.art.locate(page.number, m.group(0)) or self._block_bbox(page, m.group(0)),
                        label="guide text",
                    )
                )
        if not evs:
            return []
        note = self.ref.status.note
        return [
            self._finding(
                "other.dieline_text",
                "Print-guide / dieline text in PDF",
                G_OTHER,
                Status.NEEDS_REVIEW,
                artwork_value=", ".join(sorted(seen)),
                evidence=evs[:8],
                explanation="The PDF text contains labels typical of a dieline proof (panel names, orientation notes). If this is a proof rather than release art, these are not label content, and final-art checks should be repeated on released file."
                + (f" Workbook note: {note}" if note else ""),
                review_reason="Confirm whether this PDF is final art or a dieline proof.",
                limitations=["Whether this text is on a non-printing layer is not analysed."],
            )
        ]

    def check_not_checked(self) -> list[Finding]:
        out = [
            self._finding(
                "scope.regulatory",
                "Regulatory compliance",
                G_OTHER,
                Status.NOT_CHECKED,
                explanation="Not performed. No regulatory rule source was provided, and PackGuard AI does not invent one. Agreement between sheet and artwork does not show legal compliance.",
            ),
            self._finding(
                "scope.visual",
                "Graphics, logos, barcode symbol, fonts and legibility",
                G_OTHER,
                Status.NOT_CHECKED,
                explanation="Not performed. Only text and numeric fields are compared; visual design, minimum type size, colours, logos and barcode quality are out of scope.",
            ),
        ]
        for key, fid, nm in (
            ("label_identifier", "scope.label_identifier", "Label identifier"),
            ("bpn", "scope.bpn", "BPN"),
        ):
            ref = self._f(key)
            if ref:
                out.append(
                    self._finding(
                        fid,
                        nm,
                        G_OTHER,
                        Status.NOT_CHECKED,
                        ref,
                        explanation="Internal identifier with no supported check against the artwork."
                        + (" The workbook marks it as assumed/unconfirmed." if ref.flagged else ""),
                    )
                )
        return out
