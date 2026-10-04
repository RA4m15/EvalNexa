"""
AI-EVAL Phase 2: Feature Role Freeze & Architectural Audit
Script: phase2/11_feature_role_audit.py

PURPOSE:
Investigation-only, reproducible audit documenting the finalized roles,
empirical evidence, operational limitations, mathematical redundancies,
and candidate-generation biases of Features F1–F5.

Synthesizes findings from:
1. The 5 full-page calibration cases (answer_sheet.jpg, answer_sheet_2.png,
   answer_sheet_3.jpg, answer_sheet_4.jpg, answer_sheet_5.jpg).
2. The 30 supplementary handwriting crops (images/dataset_samples/).

IMPORTANT GUARDRAILS:
- This is NOT a detector or scoring engine.
- Contains NO scoring weights, thresholds, ranking, or accept/reject logic.
- Leaves all previous Phase 2 code and data strictly unmodified.
"""

import sys
from pathlib import Path

# Ensure UTF-8 stdout on Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))


def run_feature_role_audit():
    report = []

    def p(text=""):
        report.append(text)
        print(text)

    p("=" * 80)
    p("AI-EVAL PHASE 2: FEATURE ROLE FREEZE & ARCHITECTURAL AUDIT")
    p("=" * 80)
    p("Status       : INVESTIGATION ONLY — NOT A DETECTOR OR SCORING ENGINE")
    p("Scope        : Features F1–F5 across 5 full-page calibration images and 30 handwriting crops")
    p("Constraints  : No weights, no ranking, no thresholds, no candidate rejection")
    p("=" * 80)

    # -------------------------------------------------------------------------
    # 1. Phase 2 Feature Role Freeze Overview
    # -------------------------------------------------------------------------
    p("\n" + "=" * 80)
    p("1. PHASE 2 FEATURE ROLE FREEZE OVERVIEW")
    p("=" * 80)
    p(
        "Phase 2 development established that candidate evaluation cannot rely on\n"
        "monolithic ad-hoc scores or uncalibrated weights. Features F1–F5 have been\n"
        "isolated into independent raw physical measurement layers. Their architectural\n"
        "roles are now formally frozen based on rigorous empirical audits."
    )

    # -------------------------------------------------------------------------
    # 2. F1–F5 Role Table
    # -------------------------------------------------------------------------
    p("\n" + "=" * 80)
    p("2. F1–F5 ROLE CLASSIFICATION TABLE")
    p("=" * 80)
    role_table = [
        ("F1: Local Boundary Appearance", "PRIMARY", "Physical paper-to-background edge contrast (4 independent collars)"),
        ("F2: Active Document Edges", "PRIMARY", "Document content presence, stroke frequency, and spatial dispersion"),
        ("F3: Texture / Microcontrast", "SUPPORTING", "Ink intensity, pen pressure, handwriting boldness, paper grain"),
        ("F4: Spatial Containment", "SUPPORTING", "Crop-local geometry, dead borders, blank margin preservation"),
        ("F5: Geometry / Shape Prior", "DIAGNOSTIC / WEAK PRIOR", "Candidate proportions and frame-contact relationship"),
    ]
    p(f"{'Feature':<34} | {'Role':<24} | {'Physical / Operational Meaning'}")
    p("-" * 80)
    for feat, role, meaning in role_table:
        p(f"{feat:<34} | {role:<24} | {meaning}")

    # -------------------------------------------------------------------------
    # 3. Evidence Supporting Each Role
    # -------------------------------------------------------------------------
    p("\n" + "=" * 80)
    p("3. EVIDENCE SUPPORTING EACH ROLE")
    p("=" * 80)
    p(
        "FEATURE #1 — Local Boundary Appearance [PRIMARY]:\n"
        "  - Direct physical measurement: 4 independent inner/outer collar strips (15 px).\n"
        "  - True isolated pages on desks (answer_sheet_2, answer_sheet_3) exhibit strong\n"
        "    observed step contrast: Delta Brightness = +33 to +46, Delta Saturation = +18 to +21.\n"
        "  - Tight candidate boundaries on blank paper correctly report POTENTIALLY_CONTAMINATED\n"
        "    (NO_CONTRAST: Delta Brightness ~ 0).\n"
        "  - Handwriting-only 224x224 crops report 100% UNOBSERVED (120/120 edges), proving\n"
        "    that F1 never fabricates artificial edge contrast when no exterior pixels exist.\n"
        "\n"
        "FEATURE #2 — Active Document Edges [PRIMARY]:\n"
        "  - Direct content presence measurement: Canny edge density and Gini concentration.\n"
        "  - Validated across 30 diverse handwriting samples:\n"
        "      * Edge density spans: 1.30% to 11.96% (Mean: 5.77%, Median: 5.64%, Std: 2.79%)\n"
        "      * Active row fraction spans: 0.393 to 1.000 (Mean: 0.821, Median: 0.884)\n"
        "      * Row edge Gini spans: 0.240 to 0.802 (Mean: 0.478, Median: 0.455)\n"
        "  - Captures genuine handwriting line structure and ruled spacing across 21 students.\n"
        "\n"
        "FEATURE #3 — Texture / Microcontrast [SUPPORTING]:\n"
        "  - Continuous energy measurement: Local grayscale variance in a resolution-scaled window.\n"
        "  - Validated across 30 diverse handwriting samples:\n"
        "      * Median variance (P50) spans: 2.0 to 374.5 (Mean: 73.0, Median: 34.1, Std: 85.3)\n"
        "      * P90 variance spans: 257.8 to 1370.6 (Mean: 690.3, Median: 644.4, Std: 273.3)\n"
        "  - Strongly corroborates active writing and detects background desk bleed (which collapses P50).\n"
        "\n"
        "FEATURE #4 — Boundary Compactness / Content Containment [SUPPORTING]:\n"
        "  - Candidate-local spatial descriptor: content bounding box, fill ratio, dead borders.\n"
        "  - Validated across 30 handwriting crops:\n"
        "      * Fill ratio spans: 61.7% to 100.0% (Mean: 87.4%, Median: 92.5%)\n"
        "      * Dead borders (top/bottom/left/right) span: 0 to 71 px\n"
        "  - Quantifies padding and margins without requiring content to touch every border.\n"
        "\n"
        "FEATURE #5 — Geometry / Shape Prior [DIAGNOSTIC / WEAK PRIOR]:\n"
        "  - Scale-independent geometric description: aspect ratio, diagonal, frame contact.\n"
        "  - Validated across full-page calibration cases: portrait aspect ratios span 1.28 to 1.92,\n"
        "    disproving rigid canonical A4 assumptions (1.414)."
    )

    # -------------------------------------------------------------------------
    # 4. Operational Limitations / Failure Modes
    # -------------------------------------------------------------------------
    p("\n" + "=" * 80)
    p("4. OPERATIONAL LIMITATIONS & FAILURE MODES")
    p("=" * 80)
    p(
        "F1 (Local Boundary Appearance):\n"
        "  - Failure Mode 1: When a document tightly fills the camera frame (answer_sheet, answer_sheet_5),\n"
        "    outer collars are clipped out of bounds, forcing state to UNOBSERVED.\n"
        "  - Failure Mode 2: High internal contrast transitions (e.g. printed section borders, table lines,\n"
        "    or shaded blocks) produce strong local gradient seams identical to physical paper edges.\n"
        "  - Rule: Must strictly preserve tripartite states: OBSERVED, UNOBSERVED, POTENTIALLY_CONTAMINATED.\n"
        "\n"
        "F2 (Active Document Edges):\n"
        "  - Failure Mode 1: Textured desk wood, linoleum, printed diagrams, and fabric weave also produce Canny edges.\n"
        "  - Failure Mode 2: Wide 9-fold spread (1.30% to 11.96%) means any single global edge threshold\n"
        "    will either reject faint student handwriting or accept non-document textured backgrounds.\n"
        "  - Rule: Cannot independently establish that a candidate is a document.\n"
        "\n"
        "F3 (Texture / Microcontrast):\n"
        "  - Failure Mode 1: Extreme natural variability (P50 varies 187-fold from 2.0 to 374.5) caused\n"
        "    by lighting, ballpoint pen vs pencil, and camera sensor sharpness.\n"
        "  - Failure Mode 2: Wood grain on desks can produce higher variance than clean paper handwriting.\n"
        "  - Rule: Must only support, never override, boundary and edge evidence.\n"
        "\n"
        "F4 (Boundary Compactness / Content Containment):\n"
        "  - Failure Mode 1: Artificial window dependence: on arbitrary crops (e.g. 224x224 patches),\n"
        "    dead borders reflect arbitrary cropping, not document margins.\n"
        "  - Failure Mode 2: Real blank answer sheets have wide margins; low fill ratio is not negative evidence.\n"
        "  - Rule: Measure spatial containment only; do not penalize blank margins.\n"
        "\n"
        "F5 (Geometry / Shape Prior):\n"
        "  - Failure Mode 1: Degenerates to a trivial constant on normalized crops (224x224 -> AR=1.0, Frame Contact=4/4).\n"
        "  - Failure Mode 2: Real answer sheets can be landscape, square, or elongated portrait (1.28 to 1.92+).\n"
        "  - Rule: Frame contact is purely descriptive; touching the frame is neither good nor bad."
    )

    # -------------------------------------------------------------------------
    # 5. Redundancy Notes
    # -------------------------------------------------------------------------
    p("\n" + "=" * 80)
    p("5. MATHEMATICAL & STRUCTURAL REDUNDANCY AUDIT")
    p("=" * 80)
    p(
        "1. F2 Edge Density vs F4 Occupancy Structure (Partially Overlapping):\n"
        "   Both project Canny edge maps onto 1D axes. F2 computes statistical dispersion (Gini, COV),\n"
        "   while F4 computes topological run-lengths and dead borders. Keep both raw; do not double-score.\n"
        "\n"
        "2. F3 Texture Variance vs F2 Edge Density (Partially Overlapping):\n"
        "   F2 measures zero-crossing density; F3 measures continuous gray variance. Correlated (R ~ 0.7),\n"
        "   but F3 detects solid wash/grain that lacks Canny edges.\n"
        "\n"
        "3. F4 Fill Ratio vs Candidate Generation Strategy (Highly Redundant):\n"
        "   Appearance-mask candidates have fill ratio = 100% by definition. Full-frame candidates have\n"
        "   fill ratio = page coverage. Fill ratio reflects candidate generation, not document quality.\n"
        "\n"
        "4. F4 Content BBox vs F5 Candidate Geometry (Partially Overlapping):\n"
        "   Identical for tight masks; widely divergent for full-frame candidates. The divergence is the\n"
        "   actual signal (indicating extraneous background inclusion).\n"
        "\n"
        "5. F5 Shape Factor vs Aspect Ratio (Mathematically Redundant):\n"
        "   Diagonal / Perimeter is an exact algebraic function of AR: sqrt(1 + AR^2) / (2 * (1 + AR)).\n"
        "   It adds zero independent information.\n"
        "\n"
        "6. F5 Area Fraction vs Frame Margins (Mathematically Redundant):\n"
        "   Area fraction equals ((W - M_L - M_R) * (H - M_T - M_B)) / (W * H). Redundant with margins."
    )

    # -------------------------------------------------------------------------
    # 6. Candidate-Generation Bias Notes
    # -------------------------------------------------------------------------
    p("\n" + "=" * 80)
    p("6. CANDIDATE-GENERATION BIAS AUDIT")
    p("=" * 80)
    p(
        "A. Frame View (cand_frame_full):\n"
        "   - Inherently captures 100% of image edges (favoring total edge counts).\n"
        "   - Forces F1 to 4/4 UNOBSERVED and F5 to 4/4 frame contacts.\n"
        "   - True page boundaries are exposed when F4 dead borders > 50 px.\n"
        "\n"
        "B. Appearance Mask (cand_app_mask_1):\n"
        "   - Maximizes F1 boundary contrast (+33 to +46) because the box was placed on paper edges.\n"
        "   - Artificially forces F4 fill ratio to 100% and dead borders to 0 px.\n"
        "\n"
        "C. Content Envelope (cand_content_envelope):\n"
        "   - Bounded by handwriting strokes + buffer padding.\n"
        "   - Boundary collar falls on internal blank paper, causing F1 to report POTENTIALLY_CONTAMINATED\n"
        "     (NO_CONTRAST) even when the document content is perfectly valid.\n"
        "\n"
        "D. Structural Sub-Region (cand_sub_top, cand_sub_bottom):\n"
        "   - Internal printed lines produce high gradient seams (137.8), simulating physical edges.\n"
        "   - Aspect ratios collapse to wide rectangles (0.54 to 0.79)."
    )

    # -------------------------------------------------------------------------
    # 7. Dataset Applicability Notes
    # -------------------------------------------------------------------------
    p("\n" + "=" * 80)
    p("7. DATASET APPLICABILITY NOTES")
    p("=" * 80)
    p(
        "A. Full-Page Calibration Images (5 images, 768x1024 to 1200x1700):\n"
        "   - Applicable for: Macro page detection, desk-to-paper boundary contrast (F1),\n"
        "     aspect ratio bounds (F5), frame contact diagnostics, and containment (F4).\n"
        "   - Insufficient for: Multi-student handwriting density distributions or partition calibration.\n"
        "\n"
        "B. Supplementary Handwriting Dataset (30 crops, 224x224 px, 21 students):\n"
        "   - Applicable for: Natural stroke density spread (F2), ink microcontrast variability (F3),\n"
        "     and active row-run stability (F4).\n"
        "   - NOT APPLICABLE FOR: Page boundary detection (F1) or macro page geometry (F5),\n"
        "     because crop edges are arbitrary patch cuts, not physical paper perimeters."
    )

    # -------------------------------------------------------------------------
    # 8. Explicit "DO NOT ASSUME" Rules
    # -------------------------------------------------------------------------
    p("\n" + "=" * 80)
    p("8. EXPLICIT ARCHITECTURAL 'DO NOT ASSUME' RULES")
    p("=" * 80)
    p(
        "1. DO NOT assume A4 paper (proportions vary from 1.28 to 1.92+ across real answer sheets).\n"
        "2. DO NOT assume portrait orientation (forms and answer sheets can be landscape or square).\n"
        "3. DO NOT assume rigid global edge density thresholds (handwriting density spans 1.30% to 11.96%).\n"
        "4. DO NOT assume rigid local variance thresholds (P50 microcontrast spans 2.0 to 374.5).\n"
        "5. DO NOT assume frame contact is negative or positive (answer_sheet_5 legitimately touches 4/4).\n"
        "6. DO NOT assume high fill ratio indicates document validity (appearance masks produce 100% artificially).\n"
        "7. DO NOT assume blank margins indicate invalid candidates (unwritten answer sheets are legitimate).\n"
        "8. DO NOT assume internal horizontal gradient seams are physical page boundaries (printed tables\n"
        "   and shaded question headers also generate massive step gradients)."
    )

    # -------------------------------------------------------------------------
    # 9. Final Architecture Recommendation for Next Detector Stage
    # -------------------------------------------------------------------------
    p("\n" + "=" * 80)
    p("9. FINAL ARCHITECTURE RECOMMENDATION FOR NEXT DETECTOR STAGE")
    p("=" * 80)
    p(
        "LEVEL 1: Document Region Detection\n"
        "  - Goal: Identify the physical bounding region of the document within the camera field of view.\n"
        "  - Feature Integration Hierarchy:\n"
        "      * Feature #1 (Local Boundary Appearance) : PRIMARY EVIDENCE (physical edge verification)\n"
        "      * Feature #2 (Active Document Edges)     : PRIMARY EVIDENCE (active content verification)\n"
        "      * Feature #3 (Texture / Microcontrast)   : SUPPORTING EVIDENCE (sharpness & ink confirmation)\n"
        "      * Feature #4 (Spatial Containment)       : SUPPORTING EVIDENCE (margin & padding diagnostics)\n"
        "      * Feature #5 (Geometry / Shape Prior)    : WEAK PRIOR (geometric plausibility & contact diagnostic)\n"
        "\n"
        "LEVEL 2: Page Partitioning\n"
        "  - Goal: Determine whether a valid document region contains one page, multiple physical pages,\n"
        "    or a single page with internal printed dividers/tables.\n"
        "  - Architectural Separation:\n"
        "      * Must remain an independent stage downstream from Level 1.\n"
        "      * An internal intensity transition (e.g. y=607 in answer_sheet.jpg) MUST NOT automatically\n"
        "        be classified as a physical page boundary.\n"
        "      * Requires explicit physical edge evidence (shadow/highlight pair, paper thickness, corner tabs),\n"
        "        layout continuity (question numbering continuation), or dedicated multi-page training data."
    )

    p("\n" + "=" * 80)
    p("FEATURE ROLE FREEZE COMPLETE — READY FOR CANDIDATE VALIDATION DESIGN")
    p("=" * 80)


if __name__ == "__main__":
    run_feature_role_audit()
