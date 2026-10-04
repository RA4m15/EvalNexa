"""
AI-EVAL Phase 2: Candidate Validation Audit (Investigation Only)
Script: phase2/12_candidate_validation_audit.py

PURPOSE:
Investigation-only candidate validation audit using frozen F1–F5 raw feature
functions and existing candidate-generation strategies across the 5 calibration
images.

IMPORTANT:
- This is NOT a detector or scoring engine.
- Contains NO weights, thresholds, ranking formulas, accept/reject logic,
  or machine-learning classification.
- Reuses existing functions directly from phase2/07_page_region_candidate_detection.py.
- Does NOT modify any existing Phase 2 files.
"""

import sys
from pathlib import Path
import importlib

# Ensure UTF-8 stdout on Windows console
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8")

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

# Dynamically import phase2/07_page_region_candidate_detection.py
p7 = importlib.import_module("phase2.07_page_region_candidate_detection")


def run_candidate_validation_audit():
    print("=" * 80)
    print("AI-EVAL PHASE 2: CANDIDATE VALIDATION AUDIT")
    print("=" * 80)
    print("Status       : INVESTIGATION ONLY — NOT A DETECTOR OR SCORING ENGINE")
    print("Scope        : 5 calibration images across 4 candidate-generation strategies")
    print("Constraints  : No weights, no ranking, no thresholds, no candidate rejection")
    print("=" * 80)

    # Collect evaluated candidates across all 5 calibration images
    all_cases = []

    for fname in p7.CALIBRATION_IMAGES:
        fpath = str(WORKSPACE_ROOT / p7.IMAGES_DIR / fname)
        res = p7.process_image_candidates(fpath)
        img_w = res["precomputed"]["width"]
        img_h = res["precomputed"]["height"]

        for cand in res["evaluated_candidates"]:
            cid = cand["id"]
            strat = cand["strategy"]
            box = cand["box"]
            f1 = cand["boundary"]
            f2 = cand["edge_meas"]
            f3 = cand["texture"]
            f4 = cand["compactness"]
            f5 = cand["geometry"]

            # Qualitative descriptive classifications (NO numerical thresholds used)
            # F1 qualitative label
            if f1["observed_edge_count"] > 0 and f1["contaminated_edge_count"] == 0:
                f1_desc = f"PRESENT ({f1['observed_edge_count']}/4 observed edges)"
            elif f1["unobserved_edge_count"] == 4:
                f1_desc = "UNOBSERVED (all 4 edges on frame border)"
            elif f1["contaminated_edge_count"] > 0:
                f1_desc = f"CONTAMINATED ({f1['contaminated_edge_count']}/4 NO_CONTRAST / inner paper seam)"
            else:
                f1_desc = f"MIXED ({f1['observed_edge_count']} obs, {f1['unobserved_edge_count']} unobs)"

            # F2 qualitative label
            f2_desc = f"PRESENT (density: {f2['edge_density']*100:.2f}%, {f2['edge_pixel_count']} stroke px)"

            # F3 qualitative label
            f3_desc = f"PRESENT (P50: {f3['p50_var']:.1f}, P90: {f3['p90_var']:.1f})"

            # F4 qualitative label
            db = f4["dead_borders"]
            f4_desc = (f"DIAGNOSTIC ONLY (fill: {f4['fill_ratio']*100:.1f}%, "
                       f"dead borders: T:{db['top_dead_border_px']} B:{db['bottom_dead_border_px']} "
                       f"L:{db['left_dead_border_px']} R:{db['right_dead_border_px']} px)")

            # F5 qualitative label
            f5_desc = (f"DIAGNOSTIC ONLY (AR: {f5['aspect_ratio_h_over_w']:.2f}, "
                       f"contact: {f5['number_of_frame_touching_sides']}/4)")

            all_cases.append({
                "image": fname,
                "dims": (img_w, img_h),
                "cand_id": cid,
                "strategy": strat,
                "box": box,
                "f1": f1,
                "f2": f2,
                "f3": f3,
                "f4": f4,
                "f5": f5,
                "f1_desc": f1_desc,
                "f2_desc": f2_desc,
                "f3_desc": f3_desc,
                "f4_desc": f4_desc,
                "f5_desc": f5_desc,
            })

    # =========================================================================
    # PER-CANDIDATE DETAILED EVIDENCE PROFILES
    # =========================================================================
    print("\n" + "=" * 80)
    print("DETAILED RAW EVIDENCE PROFILES PER CANDIDATE (N = 12 EVALUATIONS)")
    print("=" * 80)

    for idx, c in enumerate(all_cases, 1):
        f1, f2, f3, f4, f5 = c["f1"], c["f2"], c["f3"], c["f4"], c["f5"]
        db = f4["dead_borders"]
        occ = f4["occupancy_structure"]
        e_recs = f1["edge_records"]

        print(f"\n[{idx:02d}] Image: {c['image']} ({c['dims'][0]}x{c['dims'][1]} px)")
        print(f"     Candidate : {c['cand_id']} ({c['strategy']}) | Box: {c['box']}")
        print("     F1 (Local Boundary Appearance):")
        print(f"       Observed edges: {f1['observed_edge_count']}/4 | Unobserved: {f1['unobserved_edge_count']}/4 | Contaminated: {f1['contaminated_edge_count']}/4")
        for s in ["TOP", "BOTTOM", "LEFT", "RIGHT"]:
            e = e_recs[s]
            d_b = f"{e['delta_brightness']:+.1f}" if e['delta_brightness'] is not None else "None"
            d_s = f"{e['delta_saturation']:+.1f}" if e['delta_saturation'] is not None else "None"
            c_reason = f" ({e['contamination_reason']})" if e['contamination_reason'] else ""
            print(f"       {s:<6}: state={e['state']:<24} | delta_B={d_b:<6} | delta_S={d_s:<6} | seam_grad={e['boundary_gradient_mag']:5.1f}{c_reason}")
        print("     F2 (Active Document Edges):")
        print(f"       edge_density={f2['edge_density']*100:.2f}% | edge_pixel_count={f2['edge_pixel_count']} px")
        print(f"       active_row_frac={f2['active_row_fraction']:.2f} | active_col_frac={f2['active_col_fraction']:.2f}")
        print(f"       row_dist: Gini={f2['row_dist']['gini']:.3f}, COV={f2['row_dist']['cov']:.2f} | col_dist: Gini={f2['col_dist']['gini']:.3f}, COV={f2['col_dist']['cov']:.2f}")
        print("     F3 (Texture / Microcontrast):")
        print(f"       mean_var={f3['mean_var']:.1f}, std_var={f3['std_var']:.1f} | P50={f3['p50_var']:.1f}, P75={f3['p75_var']:.1f}, P90={f3['p90_var']:.1f}, P95={f3['p95_var']:.1f}")
        print("     F4 (Boundary Compactness / Content Containment):")
        print(f"       fill_ratio={f4['fill_ratio']*100:.1f}% | dead_borders(T,B,L,R)=({db['top_dead_border_px']}, {db['bottom_dead_border_px']}, {db['left_dead_border_px']}, {db['right_dead_border_px']}) px")
        print(f"       occupancy: row_bands={occ['num_active_row_bands']}, longest_row_run={occ['longest_active_row_run']} px, active_row_span={occ['active_row_span']} px")
        print("     F5 (Geometry / Shape Prior):")
        print(f"       aspect_ratio={f5['aspect_ratio_h_over_w']:.3f} (h/w) | dimensions={f5['candidate_width']}x{f5['candidate_height']} px | area_fraction={f5['area_fraction_of_image']*100:.1f}%")
        print(f"       frame_contact={f5['number_of_frame_touching_sides']}/4 | margins(T,B,L,R)=({f5['margin_to_top']}, {f5['margin_to_bottom']}, {f5['margin_to_left']}, {f5['margin_to_right']}) px")

    # =========================================================================
    # SECTION 1 — CANDIDATE EVIDENCE MATRIX
    # =========================================================================
    print("\n" + "=" * 80)
    print("SECTION 1 — CANDIDATE EVIDENCE MATRIX")
    print("=" * 80)
    print(f"{'Image & Candidate':<30} | {'F1 Boundary':<18} | {'F2 Content':<14} | {'F3 Micro':<14} | {'F4 Containment':<16} | {'F5 Geometry':<16} | {'Main Limitation'}")
    print("-" * 135)

    limitations = {
        ("answer_sheet.jpg", "cand_frame_full"): "4/4 unobserved collars (frame-limited; captures two structural blocks)",
        ("answer_sheet.jpg", "cand_sub_top"): "Wide landscape AR (0.79); bottom boundary is printed/shaded divider",
        ("answer_sheet.jpg", "cand_sub_bottom"): "Extreme landscape AR (0.54); top boundary is printed/shaded divider",
        ("answer_sheet_2.png", "cand_app_mask_1"): "None (strong physical boundary evidence on all 4 edges)",
        ("answer_sheet_2.png", "cand_content_envelope"): "F1 collar sits on blank margin (NO_CONTRAST artifact)",
        ("answer_sheet_2.png", "cand_frame_full"): "Large dead borders (119-142 px); P50 collapses to 4.9 (desk bleed)",
        ("answer_sheet_3.jpg", "cand_app_mask_1"): "Weak contrast on Left edge (+3.1 B); 3/4 edges strongly observed",
        ("answer_sheet_3.jpg", "cand_content_envelope"): "F1 collar sits on blank margin (NO_CONTRAST artifact)",
        ("answer_sheet_3.jpg", "cand_frame_full"): "Large dead borders (62-175 px); P50 collapses to 7.0 (desk bleed)",
        ("answer_sheet_4.jpg", "cand_app_mask_1"): "Top and Bottom unobserved (document extends outside camera frame)",
        ("answer_sheet_4.jpg", "cand_frame_full"): "Lateral dead borders (150-165 px); includes left/right desk background",
        ("answer_sheet_5.jpg", "cand_frame_full"): "4/4 unobserved collars (frame-limited; tightly framed sheet)",
    }

    for c in all_cases:
        key = (c["image"], c["cand_id"])
        lim = limitations.get(key, "Candidate-generation artifact")
        f1_summary = f"Obs:{c['f1']['observed_edge_count']}/4 Unobs:{c['f1']['unobserved_edge_count']}/4"
        if c['f1']['contaminated_edge_count'] > 0:
            f1_summary += f" Contam:{c['f1']['contaminated_edge_count']}"
        f2_summary = f"{c['f2']['edge_density']*100:.1f}% ({c['f2']['edge_pixel_count']//1000}k px)"
        f3_summary = f"P50:{c['f3']['p50_var']:.0f} P90:{c['f3']['p90_var']:.0f}"
        f4_summary = f"Fill:{c['f4']['fill_ratio']*100:.0f}%"
        db = c['f4']['dead_borders']
        max_db = max(db['top_dead_border_px'], db['bottom_dead_border_px'], db['left_dead_border_px'], db['right_dead_border_px'])
        if max_db > 0:
            f4_summary += f" Dead:{max_db}px"
        f5_summary = f"AR:{c['f5']['aspect_ratio_h_over_w']:.2f} Cont:{c['f5']['number_of_frame_touching_sides']}/4"
        cand_label = f"{c['image'][:14]} {c['cand_id']}"
        print(f"{cand_label:<30} | {f1_summary:<18} | {f2_summary:<14} | {f3_summary:<14} | {f4_summary:<16} | {f5_summary:<16} | {lim}")

    # =========================================================================
    # SECTION 2 — CROSS-CANDIDATE COMPARISON
    # =========================================================================
    print("\n" + "=" * 80)
    print("SECTION 2 — CROSS-CANDIDATE COMPARISON")
    print("=" * 80)
    print(
        "A. Known / Strong Document Candidate (e.g. cand_app_mask_1 on answer_sheet_2 & 3):\n"
        "   - F1 Evidence : 3 to 4 OBSERVED edges with high contrast (Delta B = +33 to +46, Delta S = +18 to +21).\n"
        "   - F2 Evidence : High edge density (5.0% - 5.9%), row Gini 0.35, uniform column coverage.\n"
        "   - F3 Evidence : Elevated median variance (P50 = 61.7 - 441.7), strong P90 (2000 - 4000).\n"
        "   - F4 Evidence : Dead borders = 0 px, boundary activity present on all 4 sides.\n"
        "   - F5 Evidence : Frame contact = 0/4 (isolated on desk), aspect ratio 1.28 - 1.37.\n"
        "   - Profile Summary: STRONG PHYSICAL-BOUNDARY EVIDENCE + CONSISTENT INTERNAL CONTENT.\n"
        "\n"
        "B. Tightly Framed Candidate (e.g. cand_frame_full on answer_sheet_5):\n"
        "   - F1 Evidence : 0/4 observed, 4/4 UNOBSERVED (outer collar lies outside image).\n"
        "   - F2 Evidence : Strong edge density (4.92%, 94k pixels), active row/col fraction = 1.000.\n"
        "   - F3 Evidence : High variance throughout (P50 = 92.7, P90 = 2620.3) with no background collapse.\n"
        "   - F4 Evidence : Dead borders = 0 px, boundary band activity present on all 4 candidate sides.\n"
        "   - F5 Evidence : Frame contact = 4/4, frame margins = 0 px, aspect ratio = 1.33.\n"
        "   - Profile Summary: FRAME-LIMITED EVIDENCE (No exterior contrast observable, but content is valid).\n"
        "\n"
        "C. Content-Derived Candidate (e.g. cand_content_envelope on answer_sheet_2 & 3):\n"
        "   - F1 Evidence : 0/4 observed, 4/4 POTENTIALLY_CONTAMINATED (NO_CONTRAST: Delta B ~ 0.0).\n"
        "   - F2 Evidence : Captures 100% of handwriting/text (identical pixel count to full page).\n"
        "   - F3 Evidence : High variance (P50 = 56 - 330), identical content microcontrast.\n"
        "   - F4 Evidence : Dead borders = 33-42 px on all sides (exact reflection of padding buffer).\n"
        "   - F5 Evidence : Frame contact = 0/4, plausible aspect ratio (1.26 - 1.35).\n"
        "   - Profile Summary: CONTENT-DERIVED EVIDENCE (Fails paper boundary check due to blank margin padding).\n"
        "\n"
        "D. Internal Structural / Printed Candidate (e.g. cand_sub_top / cand_sub_bottom on answer_sheet.jpg):\n"
        "   - F1 Evidence : 1 OBSERVED internal seam with massive gradient (137.8) and Delta B = 73.0;\n"
        "                   remaining 3 edges are UNOBSERVED (frame-touching).\n"
        "   - F2 Evidence : Dense text in both halves (6.7% and 4.3%), active rows > 0.82.\n"
        "   - F3 Evidence : Top P50 = 107.1, Bottom P50 = 54.3 (both indicate active writing).\n"
        "   - F4 Evidence : cand_sub_top has 30 px bottom dead border; cand_sub_bottom has 0 px dead borders.\n"
        "   - F5 Evidence : Proportions deviate sharply from standard sheets (AR = 0.79 and 0.54, wide landscape).\n"
        "   - Profile Summary: AMBIGUOUS BOUNDARY EVIDENCE (Internal divider simulates paper edge).\n"
        "\n"
        "E. Full-Frame Candidate on Non-Tight Scene (e.g. cand_frame_full on answer_sheet_2 & 3):\n"
        "   - F1 Evidence : 4/4 UNOBSERVED (cannot see desk outside image frame).\n"
        "   - F2 Evidence : Captures 100% of edge pixels, but density is diluted (3.3% - 3.8%).\n"
        "   - F3 Evidence : P50 collapses to near zero (4.9 - 7.0), exposing massive smooth desk inclusion.\n"
        "   - F4 Evidence : Massive dead borders (119 - 175 px) on all 4 sides; fill ratio collapses to 66%.\n"
        "   - F5 Evidence : Frame contact = 4/4, frame margins = 0 px.\n"
        "   - Profile Summary: OVER-INCLUSIVE EVIDENCE (Includes surrounding non-document desk surface)."
    )

    # =========================================================================
    # SECTION 3 — RELIABLE EVIDENCE PATTERNS
    # =========================================================================
    print("=" * 80)
    print("SECTION 3 — RELIABLE EVIDENCE PATTERNS (EMPIRICAL CALIBRATION OBSERVATIONS)")
    print("=" * 80)
    print(
        "1. Isolated Paper Boundaries (Empirical pattern in this small cohort):\n"
        "   - Multiple observed physical-boundary collars were present in the strongest isolated-page calibration examples.\n"
        "   - These examples also exhibited minimal dead borders and zero frame contact in this cohort.\n"
        "   - Candidate signal, not yet a decision rule; requires broader validation.\n"
        "\n"
        "2. Desk Background Inclusion Detection:\n"
        "   - Low median variance coincided with large smooth-background inclusion in the observed full-frame calibration examples.\n"
        "   - Substantial dead borders also coincided with candidate expansion into surrounding background in calibration images.\n"
        "   - This empirical pattern separates these observed calibration examples, but requires broader validation.\n"
        "\n"
        "3. Tightly Framed Document Behavior:\n"
        "   - Tightly framed calibration examples retained supporting content/containment evidence despite F1 being UNOBSERVED.\n"
        "   - In these calibration examples:\n"
        "     (a) dead borders remained minimal along frame-touching boundaries,\n"
        "     (b) boundary bands retained active edge-pixel coverage up to the margins,\n"
        "     (c) P50 provides supporting evidence of local grayscale activity; it does not independently establish paper or ink."
    )

    # =========================================================================
    # SECTION 4 — AMBIGUOUS / MISLEADING PATTERNS
    # =========================================================================
    print("=" * 80)
    print("SECTION 4 — AMBIGUOUS / MISLEADING PATTERNS")
    print("=" * 80)
    print(
        "1. Content Envelope Margin Misclassification:\n"
        "   - A candidate placed around writing with 30-40 px padding (cand_content_envelope) is placed\n"
        "     on blank paper. F1 evaluates paper-vs-paper and reports NO_CONTRAST (CONTAMINATED).\n"
        "   - Misleading: Lacking boundary contrast does NOT mean the content is invalid;\n"
        "     it only means the candidate boundary does not match the physical paper edge.\n"
        "\n"
        "2. Internal Printed / Shaded Dividing Seams:\n"
        "   - In answer_sheet.jpg (y=607), an internal transition produces an intense gradient seam (137.8)\n"
        "     with a +73.0 brightness step, creating an apparent high-contrast edge.\n"
        "   - Misleading: Local gradient alone cannot distinguish an internal form divider from a paper edge.\n"
        "\n"
        "3. Aspect Ratio Elongation on Partial Captures:\n"
        "   - In answer_sheet_4.jpg, vertical frame cropping produces an aspect ratio of 1.92.\n"
        "   - Misleading: While atypical for full A4 pages, the candidate is a genuine physical document\n"
        "     whose top/bottom borders were cut off by camera positioning."
    )

    # =========================================================================
    # SECTION 5 — FEATURES RECOMMENDED FOR FUTURE VALIDATION
    # =========================================================================
    print("=" * 80)
    print("SECTION 5 — FEATURES RECOMMENDED FOR FUTURE VALIDATION")
    print("=" * 80)
    print(
        "Note: Candidate signals recommended for validation logic design; NOT yet decision rules or thresholds.\n"
        "\n"
        "1. Feature #1 (Local Boundary Appearance — Observed vs Unobserved vs Contaminated):\n"
        "   - Role: Candidate signal for physical paper edges when exterior pixels exist.\n"
        "   - Observation: Observed collar contrast (Delta B, Delta S) supported isolated document boundaries\n"
        "     in calibration examples. UNOBSERVED should be handled without automatic penalty when frame-clipped.\n"
        "\n"
        "2. Feature #2 (Active Document Edges — Density & Gini Concentration):\n"
        "   - Role: Supporting candidate evidence of document content presence.\n"
        "   - Observation: Active stroke presence across rows and columns differentiated written content from blank margins.\n"
        "\n"
        "3. Feature #3 (Texture / Microcontrast — Median P50 vs Background Bleed):\n"
        "   - Role: Corroboration of active content activity; candidate indicator for smooth background bleed.\n"
        "   - Observation: Low median variance coincided with candidate over-expansion into smooth surfaces in this cohort.\n"
        "\n"
        "4. Feature #4 (Spatial Containment — Dead Borders & Boundary Band Proximity):\n"
        "   - Role: Candidate signal for candidate tightness and boundary content arrival.\n"
        "   - Observation: Dead-border distances tracked background padding on full-frame candidates,\n"
        "     while boundary-band activity tracked frame-touching sheets."
    )

    # =========================================================================
    # SECTION 6 — FEATURES REMAINING DIAGNOSTIC
    # =========================================================================
    print("=" * 80)
    print("SECTION 6 — FEATURES REMAINING DIAGNOSTIC")
    print("=" * 80)
    print(
        "1. Feature #4 Fill Ratio: DIAGNOSTIC ONLY\n"
        "   - Heavily biased by candidate generation strategy (100% for masks, page coverage for frames).\n"
        "\n"
        "2. Feature #5 Aspect Ratio: DIAGNOSTIC / WEAK PRIOR ONLY\n"
        "   - Portrait answer sheets legitimately vary from 1.28 to 1.92+; forms may be landscape.\n"
        "   - Cannot be an acceptance filter without rejecting valid partial captures.\n"
        "\n"
        "3. Feature #5 Frame Contact & Frame Margins: DIAGNOSTIC ONLY\n"
        "   - Frame contact (0 to 4) is purely descriptive of camera framing.\n"
        "\n"
        "4. Feature #5 Shape Factor & Area Fraction: DIAGNOSTIC / REDUNDANT\n"
        "   - Mathematically redundant transforms of aspect ratio and margins."
    )

    # =========================================================================
    # SECTION 7 — OPEN EVIDENCE GAPS
    # =========================================================================
    print("=" * 80)
    print("SECTION 7 — OPEN EVIDENCE GAPS")
    print("=" * 80)
    print(
        "The calibration cohort remains small (5 calibration images + 30 uniform 224x224 crops).\n"
        "The following operational scenarios represent explicit open evidence gaps:\n"
        "\n"
        "1. More real photographs with visible desk/table backgrounds (varying wood, fabric, linoleum, granite).\n"
        "2. Tightly framed documents across diverse lighting and paper colors.\n"
        "3. Rotated documents (skewed or non-axis-aligned paper placement on desks).\n"
        "4. Landscape documents and wide-format questionnaire booklets.\n"
        "5. Partially occluded pages (hands, pens, binder clips, or shadows across paper edges).\n"
        "6. Multiple physical pages present simultaneously in the camera field of view.\n"
        "7. Folded, curled, or wrinkled answer sheets with non-planar surface curvature.\n"
        "8. Difficult lighting conditions (extreme uneven cast shadows, specular glare from phone flash).\n"
        "9. Completely blank answer sheets (sparse writing or header-only forms).\n"
        "10. Printed forms with heavy internal printed dividers, black header banners, or shaded tables."
    )

    print("\n" + "=" * 80)
    print("VALIDATION STATUS:")
    print("- No numerical validation threshold is frozen.")
    print("- No feature weight is frozen.")
    print("- No accept/reject rule is frozen.")
    print("- Current observations are calibration evidence only.")
    print("- Broader real-image validation is required before converting observations into decision rules.")
    print("=" * 80)

    print("\n" + "=" * 80)
    print("CANDIDATE VALIDATION AUDIT COMPLETE — READY FOR VALIDATION LOGIC DESIGN")
    print("=" * 80)


if __name__ == "__main__":
    run_candidate_validation_audit()
