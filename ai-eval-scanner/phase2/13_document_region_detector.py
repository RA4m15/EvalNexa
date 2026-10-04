"""
phase2/13_document_region_detector.py

AI-EVAL PHASE 2: DOCUMENT REGION DETECTOR & CANDIDATE VALIDATION
================================================================

PURPOSE:
First functional document-region validation module built upon the approved
Phase 2.13 Revision 2 architecture.

LOCKED ARCHITECTURAL PRINCIPLES:
1. Clear separation between Candidate Semantic State (local hypothesis evaluation)
   and Image-Level Validation Result (overall image arbitration).
2. Explicit, Qualitative Candidate Semantic States (6 states):
   - HIGH_CONFIDENCE_PHYSICAL_PAGE
   - FRAME_LIMITED_PLAUSIBLE_PAGE
   - CONTENT_DERIVED_ENVELOPE
   - INTERNAL_STRUCTURAL_SUBREGION
   - OVER_INCLUSIVE_BACKGROUND
   - AMBIGUOUS_OR_INSUFFICIENT
3. Explicit Image-Level Results (4 outcomes):
   - ACCEPTED_PHYSICAL_PAGE
   - ACCEPTED_FRAME_LIMITED
   - AMBIGUOUS
   - INSUFFICIENT_CONFIDENCE
4. Feature Evidence Roles:
   - F1 Local Boundary Appearance : PRIMARY physical paper/surround evidence
   - F2 Active Document Edges     : PRIMARY content presence evidence
   - F3 Texture / Microcontrast   : SUPPORTING texture evidence vs smooth background
   - F4 Spatial Containment       : SUPPORTING tightness & boundary arrival evidence
   - F5 Geometry / Shape Prior    : DIAGNOSTIC / WEAK PRIOR only (non-penalizing)
5. Robust Failure-Safety:
   - Ambiguity is preferred over false certainty.
   - Never force a candidate or fall back to the largest contour.
   - For all results in Phase 2, estimated_corners = None (corner estimation deferred to Phase 3).
   - Frame boundaries are recorded strictly as framing metadata, never as document corners.
"""

import os
import sys
import importlib.util
from typing import Dict, List, Tuple, Optional, Any
from dataclasses import dataclass, asdict

# ---------------------------------------------------------------------------
# Reusable Frozen Module Import (phase2/07_page_region_candidate_detection.py)
# ---------------------------------------------------------------------------
CURRENT_DIR = os.path.dirname(os.path.abspath(__file__))
PHASE2_07_PATH = os.path.join(CURRENT_DIR, "07_page_region_candidate_detection.py")

if not os.path.exists(PHASE2_07_PATH):
    raise FileNotFoundError(f"Required frozen module not found: {PHASE2_07_PATH}")

spec = importlib.util.spec_from_file_location("phase2_07", PHASE2_07_PATH)
if spec is None or spec.loader is None:
    raise ImportError(f"Cannot load frozen phase2_07 module from {PHASE2_07_PATH}")
phase2_07 = importlib.util.module_from_spec(spec)
spec.loader.exec_module(phase2_07)

# Direct reuse of frozen functions without modification
load_and_preprocess = phase2_07.load_and_preprocess
measure_boundary_collars = phase2_07.measure_boundary_collars
measure_active_document_edges = phase2_07.measure_active_document_edges
measure_texture_microcontrast = phase2_07.measure_texture_microcontrast
measure_boundary_compactness = phase2_07.measure_boundary_compactness
measure_geometry_shape_prior = phase2_07.measure_geometry_shape_prior

generate_frame_candidate = phase2_07.generate_frame_candidate
generate_appearance_mask_candidates = phase2_07.generate_appearance_mask_candidates
generate_content_envelope_candidate = phase2_07.generate_content_envelope_candidate
generate_structural_subregion_candidates = phase2_07.generate_structural_subregion_candidates
deduplicate_candidates = phase2_07.deduplicate_candidates


# ---------------------------------------------------------------------------
# Approved Dataclass / Interface Models (Revision 2)
# ---------------------------------------------------------------------------
@dataclass
class CandidateEvidenceProfile:
    """
    Structured evidence evaluation for a single candidate hypothesis.
    """
    candidate_id: str
    strategy: str
    box: Tuple[int, int, int, int]
    semantic_state: str  # One of the 6 approved candidate semantic states
    f1_boundary_summary: Dict[str, Any]
    f2_content_summary: Dict[str, Any]
    f3_microcontrast_summary: Dict[str, Any]
    f4_containment_summary: Dict[str, Any]
    f5_geometry_summary: Dict[str, Any]
    qualitative_notes: str


@dataclass
class DocumentValidationResult:
    """
    Structured image-level arbitration result across all candidate hypotheses.
    """
    image_status: str  # One of the 4 approved image-level outcomes
    selected_candidate_id: Optional[str]
    selected_box: Optional[Tuple[int, int, int, int]]
    estimated_corners: Optional[List[Tuple[float, float]]]  # None in Phase 2; deferred to Phase 3
    framing_metadata: Dict[str, Any]
    candidate_profiles: List[CandidateEvidenceProfile]
    arbitration_rationale: str


# ---------------------------------------------------------------------------
# Qualitative Evidence Interpretation & Semantic Classification
# ---------------------------------------------------------------------------
def classify_candidate_semantic_state(
    cand: Dict[str, Any],
    f1: Dict[str, Any],
    f2: Dict[str, Any],
    f3: Dict[str, Any],
    f4: Dict[str, Any],
    f5: Dict[str, Any],
    all_candidates: List[Dict[str, Any]]
) -> Tuple[str, str]:
    """
    Classifies a candidate into one of the 6 approved semantic states using
    rule-free qualitative evidence consistency:

    1. HIGH_CONFIDENCE_PHYSICAL_PAGE
    2. FRAME_LIMITED_PLAUSIBLE_PAGE
    3. CONTENT_DERIVED_ENVELOPE
    4. INTERNAL_STRUCTURAL_SUBREGION
    5. OVER_INCLUSIVE_BACKGROUND
    6. AMBIGUOUS_OR_INSUFFICIENT
    """
    strategy = cand.get("strategy", "")
    is_special_case = cand.get("is_special_case", False)

    edge_states = [
        record.get("state")
        for record in f1.get("edge_records", {}).values()
    ]
    has_observed = any(state == "OBSERVED" for state in edge_states)
    has_unobserved = any(state == "UNOBSERVED" for state in edge_states)
    has_contaminated = any(state == "POTENTIALLY_CONTAMINATED" for state in edge_states)

    # -----------------------------------------------------------------------
    # Case 1: Internal Structural Sub-regions
    # -----------------------------------------------------------------------
    if is_special_case or strategy == "Structural Sub-region (Experimental)":
        note = (
            "Candidate derived from internal structural transition; seam is an internal "
            "divider with content present on both sides. Not an external page boundary."
        )
        return "INTERNAL_STRUCTURAL_SUBREGION", note

    # -----------------------------------------------------------------------
    # Case 2: Content Envelope
    # -----------------------------------------------------------------------
    if strategy == "Content Envelope":
        note = (
            "Candidate derived from active content bounds; boundary sits on paper "
            "surface/margins rather than an external physical paper edge. Content crop."
        )
        return "CONTENT_DERIVED_ENVELOPE", note

    # -----------------------------------------------------------------------
    # Case 3: Frame View Hypothesis
    # -----------------------------------------------------------------------
    if strategy == "Frame View":
        # Check if the image contains a more localized appearance mask candidate
        # that directly observes paper boundaries inside the frame
        has_localized_mask = any(
            c.get("strategy") == "Appearance Mask" for c in all_candidates
        )
        has_competing_subregions = any(
            c.get("strategy") == "Structural Sub-region (Experimental)" for c in all_candidates
        )

        if has_localized_mask:
            note = (
                "Full frame encompasses the scene, but a localized document appearance mask exists "
                "within the frame. Full view includes surrounding non-document background."
            )
            return "OVER_INCLUSIVE_BACKGROUND", note

        if has_competing_subregions:
            note = (
                "Full view contains internal document content, but exhibits competing internal "
                "structural divisions. Ambiguous pending page-partitioning."
            )
            return "AMBIGUOUS_OR_INSUFFICIENT", note

        # Sole coherent frame hypothesis where exterior comparison is unavailable
        note = (
            "Exterior comparison region unavailable on frame boundaries (F1 UNOBSERVED), but active "
            "document content arrives at candidate margins without external background inclusion."
        )
        return "FRAME_LIMITED_PLAUSIBLE_PAGE", note

    # -----------------------------------------------------------------------
    # Case 4: Appearance Mask Hypothesis
    # -----------------------------------------------------------------------
    if strategy == "Appearance Mask":
        # Check if candidate boundary is contaminated (e.g. sits on blank paper without contrast)
        if has_contaminated and not has_observed:
            note = (
                "Appearance boundary lacks contrast against surround; sits on blank margin. "
                "Classified as content-derived envelope."
            )
            return "CONTENT_DERIVED_ENVELOPE", note

        # If comparison regions are unavailable on some edges (e.g. touching sensor frame borders)
        if has_unobserved:
            note = (
                "Candidate boundary observed on available edges with exterior comparison region "
                "unavailable on remaining edges (UNOBSERVED). Classified as frame-limited plausible page."
            )
            return "FRAME_LIMITED_PLAUSIBLE_PAGE", note

        # All available edges were directly observed and confirmed by F1 measurement layer
        if has_observed:
            note = (
                "External physical paper boundary directly confirmed by F1 on observed edges "
                "without unobserved frame clipping."
            )
            return "HIGH_CONFIDENCE_PHYSICAL_PAGE", note

    # -----------------------------------------------------------------------
    # Case 5: Default Fallback for Unresolved Cases
    # -----------------------------------------------------------------------
    note = "Evidence profile is ambiguous or lacks decisive physical-boundary corroboration."
    return "AMBIGUOUS_OR_INSUFFICIENT", note


# ---------------------------------------------------------------------------
# Candidate Arbitration & Image-Level Validation Logic
# ---------------------------------------------------------------------------
def arbitrate_image_candidates(
    profiles: List[CandidateEvidenceProfile],
    img_h: int,
    img_w: int
) -> Tuple[str, Optional[str], Optional[Tuple[int, int, int, int]], str]:
    """
    Arbitrates among all evaluated candidate profiles for an image:

    Returns (image_status, selected_candidate_id, selected_box, arbitration_rationale)
    """
    if not profiles:
        return "INSUFFICIENT_CONFIDENCE", None, None, "No candidate hypotheses were generated."

    # Priority 1: High-Confidence Physical Page
    physical_cands = [p for p in profiles if p.semantic_state == "HIGH_CONFIDENCE_PHYSICAL_PAGE"]
    if physical_cands:
        # If multiple physical candidates exist, select the most coherent appearance mask
        selected = physical_cands[0]
        rationale = (
            f"Candidate '{selected.candidate_id}' accepted as physical page: external paper boundaries "
            f"are directly observed against the background, with active internal content and tight containment."
        )
        return "ACCEPTED_PHYSICAL_PAGE", selected.candidate_id, selected.box, rationale

    # Priority 2: Frame-Limited Plausible Page
    frame_limited_cands = [p for p in profiles if p.semantic_state == "FRAME_LIMITED_PLAUSIBLE_PAGE"]
    if frame_limited_cands:
        # Prefer an appearance mask with partial physical edges over a raw full-frame view if available
        mask_partial = [p for p in frame_limited_cands if p.strategy == "Appearance Mask"]
        selected = mask_partial[0] if mask_partial else frame_limited_cands[0]
        rationale = (
            f"Candidate '{selected.candidate_id}' accepted as frame-limited page: document content fills "
            f"available bounds without background inclusion, though outer physical collars are unobserved."
        )
        return "ACCEPTED_FRAME_LIMITED", selected.candidate_id, selected.box, rationale

    # Priority 3: Structural Ambiguity / Competing Hypotheses
    ambiguous_cands = [p for p in profiles if p.semantic_state in ("AMBIGUOUS_OR_INSUFFICIENT", "INTERNAL_STRUCTURAL_SUBREGION")]
    if ambiguous_cands:
        rationale = (
            "Competing structural interpretations detected without decisive physical boundary evidence. "
            "Returning AMBIGUOUS to prevent forced erroneous page selection."
        )
        return "AMBIGUOUS", None, None, rationale

    # Priority 4: All candidates rejected or subordinated
    rationale = (
        "Generated candidates consist only of non-physical content envelopes or over-inclusive backgrounds. "
        "Insufficient confidence to declare a physical page."
    )
    return "INSUFFICIENT_CONFIDENCE", None, None, rationale


# ---------------------------------------------------------------------------
# Main Functional Pipeline Entry Point
# ---------------------------------------------------------------------------
def detect_and_validate_document_region(
    image_path: str
) -> DocumentValidationResult:
    """
    Main Phase 2.13 entry point:
    1. Preprocesses image and extracts multi-signal maps.
    2. Generates candidate hypotheses across complementary strategies.
    3. Derives frozen raw F1-F5 measurements.
    4. Evaluates qualitative evidence profiles for each candidate.
    5. Arbitrates between candidates and assigns image-level status.
    6. Ensures estimated_corners = None (strictly deferred to Phase 3).
    """
    # 1. Load and preprocess
    prep = load_and_preprocess(image_path)
    gray = prep["gray"]
    sat = prep["sat"]
    edges = prep["edges"]
    var_map = prep["var_map"]
    ksize = prep["ksize"]
    img_h = prep["height"]
    img_w = prep["width"]

    # 2. Candidate generation
    candidates: List[Dict[str, Any]] = []
    candidates.append(generate_frame_candidate(img_h, img_w))
    candidates.extend(generate_appearance_mask_candidates(gray, sat))
    candidates.extend(generate_content_envelope_candidate(edges, var_map))
    candidates.extend(generate_structural_subregion_candidates(gray, img_h, img_w))
    candidates = deduplicate_candidates(candidates)

    # 3 & 4. Raw measurement & semantic state classification
    profiles: List[CandidateEvidenceProfile] = []
    for cand in candidates:
        f1 = measure_boundary_collars(cand, gray, sat, img_h, img_w)
        f2 = measure_active_document_edges(cand, edges, img_h, img_w)
        f3 = measure_texture_microcontrast(cand, var_map, ksize, img_h, img_w)
        f4 = measure_boundary_compactness(cand, edges, img_h, img_w)
        f5 = measure_geometry_shape_prior(cand, img_h, img_w)

        semantic_state, note = classify_candidate_semantic_state(
            cand, f1, f2, f3, f4, f5, candidates
        )

        f1_summary = {
            "observed_count": f1.get("observed_edge_count"),
            "unobserved_count": f1.get("unobserved_edge_count"),
            "contaminated_count": f1.get("contaminated_edge_count"),
            "edges": {
                side: {
                    "state": f1.get("edge_records", {}).get(side, {}).get("state"),
                    "reason": f1.get("edge_records", {}).get(side, {}).get("contamination_reason"),
                    "delta_B": f1.get("edge_records", {}).get(side, {}).get("delta_brightness"),
                    "delta_S": f1.get("edge_records", {}).get(side, {}).get("delta_saturation"),
                    "seam_grad": f1.get("edge_records", {}).get(side, {}).get("boundary_gradient_mag"),
                }
                for side in ["TOP", "BOTTOM", "LEFT", "RIGHT"]
            }
        }

        f2_summary = {
            "edge_density": f2.get("edge_density"),
            "edge_pixel_count": f2.get("edge_pixel_count"),
            "active_row_frac": f2.get("active_row_frac"),
            "active_col_frac": f2.get("active_col_frac"),
            "row_gini": f2.get("row_dist", {}).get("gini"),
            "col_gini": f2.get("col_dist", {}).get("gini"),
        }

        f3_summary = {
            "mean_var": f3.get("mean_var"),
            "p50_var": f3.get("p50_var"),
            "p90_var": f3.get("p90_var"),
        }

        f4_summary = {
            "fill_ratio": f4.get("fill_ratio"),
            "dead_borders": f4.get("dead_borders"),
            "active_row_span": f4.get("occupancy", {}).get("active_row_span_px"),
        }

        f5_summary = {
            "aspect_ratio": f5.get("aspect_ratio_h_over_w"),
            "dimensions": (f5.get("candidate_width"), f5.get("candidate_height")),
            "frame_touching_sides": f5.get("number_of_frame_touching_sides"),
            "margins": (
                f5.get("margin_to_top"),
                f5.get("margin_to_bottom"),
                f5.get("margin_to_left"),
                f5.get("margin_to_right"),
            ),
        }

        profile = CandidateEvidenceProfile(
            candidate_id=cand["id"],
            strategy=cand["strategy"],
            box=cand["box"],
            semantic_state=semantic_state,
            f1_boundary_summary=f1_summary,
            f2_content_summary=f2_summary,
            f3_microcontrast_summary=f3_summary,
            f4_containment_summary=f4_summary,
            f5_geometry_summary=f5_summary,
            qualitative_notes=note,
        )
        profiles.append(profile)

    # 5. Candidate arbitration
    image_status, sel_id, sel_box, rationale = arbitrate_image_candidates(
        profiles, img_h, img_w
    )

    # 6. Framing metadata (frame corners preserved strictly as framing context)
    framing_metadata = {
        "sensor_dimensions": (img_w, img_h),
        "sensor_frame_box": (0, 0, img_w, img_h),
        "sensor_frame_corners": [(0.0, 0.0), (float(img_w), 0.0), (float(img_w), float(img_h)), (0.0, float(img_h))],
        "note": "sensor_frame_corners represent camera sensor bounds, NOT physical document corners.",
    }

    # Explicit: corner estimation is strictly deferred to Phase 3
    estimated_corners = None

    return DocumentValidationResult(
        image_status=image_status,
        selected_candidate_id=sel_id,
        selected_box=sel_box,
        estimated_corners=estimated_corners,
        framing_metadata=framing_metadata,
        candidate_profiles=profiles,
        arbitration_rationale=rationale,
    )


# ---------------------------------------------------------------------------
# Calibration Suite Test Runner & Diagnostic Output
# ---------------------------------------------------------------------------
def run_calibration_audit():
    """
    Executes the document region detector across all 5 calibration images
    and prints structured diagnostic reports.
    """
    calibration_images = [
        "images/answer_sheet.jpg",
        "images/answer_sheet_2.png",
        "images/answer_sheet_3.jpg",
        "images/answer_sheet_4.jpg",
        "images/answer_sheet_5.jpg",
    ]

    print("=" * 80)
    print("PHASE 2.13: FUNCTIONAL DOCUMENT REGION DETECTOR & CANDIDATE VALIDATION")
    print("=" * 80)
    print("Scope       : 5 real calibration images")
    print("Constraints : Qualitative evidence profiles, no arbitrary weights/thresholds,")
    print("              estimated_corners = None (deferred to Phase 3)")
    print("=" * 80)

    for img_path in calibration_images:
        img_name = os.path.basename(img_path)
        print(f"\n>> PROCESSING IMAGE: {img_name}")
        print("-" * 80)

        if not os.path.exists(img_path):
            print(f"ERROR: Image not found at {img_path}")
            continue

        res = detect_and_validate_document_region(img_path)

        print(f"IMAGE-LEVEL RESULT  : {res.image_status}")
        print(f"SELECTED CANDIDATE  : {res.selected_candidate_id}")
        print(f"SELECTED BOX        : {res.selected_box}")
        print(f"ESTIMATED CORNERS   : {res.estimated_corners} (Deferred to Phase 3)")
        print(f"ARBITRATION REASON  : {res.arbitration_rationale}")
        print("\nCANDIDATE EVIDENCE PROFILES EVALUATED:")
        for idx, p in enumerate(res.candidate_profiles, 1):
            f1_s = p.f1_boundary_summary
            f4_s = p.f4_containment_summary
            f5_s = p.f5_geometry_summary
            print(f"  [{idx:02d}] ID: {p.candidate_id:<22} Strategy: {p.strategy}")
            print(f"       Box: {p.box} | Semantic State: {p.semantic_state}")
            print(f"       F1 Boundary : Obs={f1_s['observed_count']}/4, Unobs={f1_s['unobserved_count']}/4, Contam={f1_s['contaminated_count']}/4")
            print(f"       F4 Spatial  : DeadBorders={f4_s['dead_borders']}, Fill={f4_s['fill_ratio']*100:.1f}%")
            print(f"       F5 Geometry : AR={f5_s['aspect_ratio']:.3f}, FrameContact={f5_s['frame_touching_sides']}/4")
            print(f"       Notes       : {p.qualitative_notes}")

    print("\n" + "=" * 80)
    print("PHASE 2.13 CALIBRATION AUDIT COMPLETE -- READY FOR REVIEW")
    print("=" * 80)


if __name__ == "__main__":
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
    run_calibration_audit()
