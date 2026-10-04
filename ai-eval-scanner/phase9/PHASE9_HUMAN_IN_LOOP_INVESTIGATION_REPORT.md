# PHASE 9 — HUMAN-IN-THE-LOOP INVESTIGATION & ARCHITECTURAL SAFETY REPORT (POST-AUDIT CALIBRATED EDITION)

**Project:** `AI-EVAL-OpenCV` (Automated Exam Evaluation Pipeline)  
**Milestone:** Phase 9 — Human-in-the-Loop Investigation & Architecture (Audited & Calibrated)  
**Author:** Antigravity AI  
**Date:** October 2026  
**Status:** **INVESTIGATION COMPLETE — ARCHITECTURAL-INVESTIGATION LEVEL (PROPOSED / NOT FROZEN)**

---

> [!IMPORTANT]
> **INVESTIGATION MILESTONE DECLARATION**  
> Phase 9 is an **investigation and architectural evidence milestone**, NOT a production human review system, user interface, or database.  
> In strict compliance with pipeline governance:
> 1. Phases 2 through 7 remain frozen, intact, and untouched.
> 2. Phases 8.1 through 8.5 remain frozen, intact, and untouched.
> 3. No production human review UI or web frontend has been built.
> 4. No database, ORM, or backend storage system has been integrated.
> 5. No authentication or user-management subsystem has been created.
> 6. No production OCR/HTR classifier has been implemented.
> 7. No automated AI examination grading engine has been implemented.
> 8. No operational human review thresholds or gating policies are frozen.
> 9. All findings distinguish between **OBSERVED**, **INVESTIGATED**, **PROPOSED**, **FUTURE**, and **NOT VALIDATED**.

---

## 1. OBJECTIVE

The purpose of Phase 9 is:

$$\mathbf{Investigate\ and\ architect\ the\ Human-in-the-Loop\ (HITL)\ safety\ layer\ bridging\ the\ automated\ vision/readiness\ pipeline\ and\ downstream\ examination\ evaluation.}$$

### Core Operating Principle:
> **"Human-in-the-loop, not human-in-every-loop."**

The automated pipeline handles bulk processing of clean, high-contrast examination scripts. Human intervention must be reserved for ambiguous, low-confidence, borderline, or policy-critical cases, ensuring maximum examination throughput while ensuring that ambiguous student work is not evaluated without appropriate human verification.

---

## 2. FROZEN-PHASE PROTECTION STATEMENT

Prior to and during Phase 9 execution, all upstream pipeline milestones were maintained as strictly read-only:

| Phase / Subsystem | Frozen Status | Protection Boundary Enforced |
| :--- | :--- | :--- |
| **Phase 2 — Document Region Detection** | FROZEN | Rectification, quadrilateral detection, and crop contracts preserved |
| **Phase 3 — Scanner Intake Integration** | FROZEN | Scanner hardware profiles and intake integration preserved |
| **Phase 4 — Document Enhancement** | FROZEN | Baseline contrast enhancement preserved |
| **Phase 5 — Quality Assessment** | FROZEN | Acutance, exposure, and fatal defect detectors preserved |
| **Phase 6 — Intelligent Correction** | FROZEN | Shadow removal, contrast normalization, rollback engine preserved |
| **Phase 7 — Rescan Decision Engine** | FROZEN | 3-way routing (`CONTINUE`, `HUMAN_REVIEW`, `RESCAN_REQUIRED`) preserved |
| **Phases 8.1–8.5 — OCR Readiness & Representations**| FROZEN | Readiness contracts, multi-representation engine ($R_0, R_1, R_2$), telemetry preserved |

No upstream contracts, thresholds, or logic files were modified. Phase 9 consumes existing Phase 7 and Phase 8 outputs as read-only inputs.

---

## 3. EXISTING PIPELINE BOUNDARY

The pipeline prior to Phase 9 establishes the following sequential flow:

```text
Raw Camera / Scanner Capture
              ↓
   Phase 2 (Page Detection) & Phase 3 (Perspective Rectification)
              ↓
   Phase 5 (Quality Assessment Gate)
              ↓
   Phase 6 (Intelligent Defect Remediation with Rejection Rollback)
              ↓
   Phase 7 (Rescan Decision Engine: CONTINUE / HUMAN_REVIEW / RESCAN_REQUIRED)
              ↓ [CONTINUE path only]
   Phase 8.2 (Multi-Representation Bundle: R0, R1, R2 + Readiness Telemetry)
              ↓
   [FUTURE: OCR/HTR Neural Transcription Engine]
              ↓
   [FUTURE: Semantic Grading & Exam Evaluation Engine]
```

In the frozen architecture:
- **Phase 7** emits a `HUMAN_REVIEW` routing decision for physically captured pages with borderline quality, sparse/blank content, or correction rollbacks.
- **Phase 8.2** extracts readiness telemetry and flags `ORIENTATION_AMBIGUOUS`, `LINE_COLLISION_ENTANGLEMENT`, and `RULED_LINE_INTERFERENCE` without blocking pipeline flow.

However, prior to Phase 9, there was no architectural model defining **what human review means, where review should conceptually sit, what candidate triggers exist, how corrections are recorded without data loss, or how auditability is structured.**

---

## 4. HUMAN-REVIEW BOUNDARY CANDIDATES (PROPOSED ARCHITECTURE)

Based on architectural investigation, a **four-checkpoint architecture is proposed**:

```text
       [DOCUMENT INTAKE]
              │
              ▼
   ┌────────────────────────────────────────────────────────┐
   │ Checkpoint 1 (CP1): Physical Intake Gate               │ ──> Routed by Phase 7
   └────────────────────────────────────────────────────────┘
              │ (CONTINUE)
              ▼
   ┌────────────────────────────────────────────────────────┐
   │ Checkpoint 2 (CP2): Pre-Recognition Readiness Gate     │ ──> Flagged by Phase 8.2/8.4
   └────────────────────────────────────────────────────────┘
              │
              ▼
   [Future Neural OCR / HTR Recognition Engine]
              │
              ▼
   ┌────────────────────────────────────────────────────────┐
   │ Checkpoint 3 (CP3): Transcription & Recognition Gate   │ ──> Triggered by Decoder Conf.
   └────────────────────────────────────────────────────────┘
              │
              ▼
   [Future AI Examiner / Semantic Grading Engine]
              │
              ▼
   ┌────────────────────────────────────────────────────────┐
   │ Checkpoint 4 (CP4): Semantic Evaluation & Policy Gate  │ ──> Triggered by Grade Boundary
   └────────────────────────────────────────────────────────┘
              │
              ▼
       [FINAL GRADE REPORT]
```

### Architectural Classification of Checkpoints:

1. **Checkpoint 1 (CP1 — Physical Intake Review):**
   - **Classification:** **PROPOSED (CONSUMES FROZEN PHASE 7 ROUTING)**.
   - **Nature:** Page-level physical verification.
   - **Purpose:** Resolves ambiguous captures (sparse/blank sheets, unrecovered borderline shadows) before compute is expended on OCR.

2. **Checkpoint 2 (CP2 — Pre-Recognition Readiness Review):**
   - **Classification:** **PROPOSED (CONSUMES FROZEN PHASE 8 TELEMETRY)**.
   - **Nature:** Image-level geometry and layout orientation.
   - **Purpose:** Resolves symmetric layout rotation ambiguity (0° vs 180° inversion) and dense line collision before neural line-slicing fails.

3. **Checkpoint 3 (CP3 — Transcription Recognition Review):**
   - **Classification:** **PROPOSED (REQUIRES FUTURE OCR/HTR INTEGRATION)**.
   - **Nature:** Region-level text verification.
   - **Purpose:** Corrects cursive character ambiguities, token collisions, struck-through answers, and low-confidence words.

4. **Checkpoint 4 (CP4 — Semantic Evaluation & Policy Review):**
   - **Classification:** **PROPOSED (REQUIRES FUTURE EXAM EVALUATION ENGINE)**.
   - **Nature:** Question-level academic adjudication.
   - **Purpose:** Subject specialist reviews diagrams, multi-step math derivations, and scripts within policy-mandated margins of passing or scholarship cutoffs.

> [!NOTE]
> **BOUNDARY STATUS:**  
> The exact placement, number, and trigger sensitivity of human-review gates remain subject to future validation and empirical calibration in Phase 11.

---

## 5. HUMAN-REVIEW TRIGGER TAXONOMY (CANDIDATE TAXONOMY)

Triggers for human intervention are classified into five root categories. All triggers remain a **CANDIDATE TAXONOMY** (no production trigger thresholds are frozen):

| Trigger Category | Candidate Trigger Conditions (Qualitative) | Pipeline Checkpoint | Candidate Action | Evidence Status |
| :--- | :--- | :---: | :---: | :--- |
| **RECOGNITION_UNCERTAINTY** | Low character/word posterior confidence; high language model perplexity; multi-engine hypothesis disagreement; illegible cursive scribble | CP3 | `CORRECT` / `REJECT` | **OBSERVED IN CONTROLLED BENCHMARK** (Phase 8.3 & 8.5) |
| **LAYOUT_AMBIGUITY** | Dense line collision; ruled-line interference; insufficient line separation evidence; tabular grids; mixed printed/handwritten answer blocks | CP2 / CP3 | `CORRECT` | **OBSERVED IN CALIBRATION SCRIPTS** (Phase 8.2 & 8.4) |
| **CONTENT_AMBIGUITY** | Mathematical derivations; geometric diagrams; circuit schematics; crossed-out revisions with marginal rewrites; overwritten characters | CP3 / CP4 | `CORRECT` / `ESCALATE` | **INVESTIGATED** |
| **PIPELINE_AMBIGUITY** | Symmetric page layout with ambiguous reading orientation; Phase 6.5 correction rollback to borderline state; sparse/blank sheet detection | CP1 / CP2 | `ACCEPT` / `CORRECT` | **OBSERVED IN FROZEN PIPELINE** (Phase 7 & 8.2) |
| **POLICY_BOUNDARY** | Total script score within policy-mandated tolerance of pass/fail cutoff; contested question rubric | CP4 | `ESCALATE` | **PROPOSED POLICY REQUIREMENT** |

> [!IMPORTANT]
> **TRIGGER THRESHOLD STATUS (UNFROZEN):**  
> Numerical trigger values (such as character confidence floors, line collision ratios, or PVR levels) **remain uncalibrated and are NOT frozen in Phase 9**. All trigger boundaries belong to Phase 11 field calibration.

---

## 6. HUMAN REVIEW ACTION MODEL (INVESTIGATED / PROPOSED)

Phase 9 defines five discrete, non-overlapping candidate actions for human examiners:

```text
+-------------------+--------------------------------------------------------------------------------+
| Action            | Semantic Meaning & Intended Downstream Consequence                             |
+-------------------+--------------------------------------------------------------------------------+
| ACCEPT            | Examiner confirms AI hypothesis is correct without modification.               |
| CORRECT           | Examiner modifies transcription text or assigns corrected question mark.       |
| REJECT            | Examiner confirms content is genuinely illegible, blank, or invalid (0 marks). |
| UNCLEAR           | Examiner cannot decipher content; triggers secondary moderation.              |
| ESCALATE          | Policy boundary dispute, suspected tampering, or ungradable technical defect.  |
+-------------------+--------------------------------------------------------------------------------+
```

### Action Model Invariants:
1. **Zero Overwrite:** When `CORRECT` is chosen, the original AI hypothesis string and confidence score remain completely unmodified.
2. **Explicit Ambiguity Preservation:** When content is genuinely illegible or ambiguous, examiners select `UNCLEAR` or `REJECT`. Content must never be coerced into speculative text.
3. **Escalation Routing:** `ESCALATE` routes edge cases to senior academic or administrative authorities without silently defaulting to automated rejection.

---

## 7. NON-DESTRUCTIVE AI OUTPUT PRESERVATION MODEL (VALIDATED IN IN-MEMORY EXPERIMENT)

A fundamental architectural requirement of the safety layer is **zero data loss**:

$$\mathbf{Original\ Rectified\ Canvas\ \ne\ Preprocessed\ Image\ \ne\ AI\ Hypothesis\ \ne\ Human\ Correction}$$

Under no circumstances may a human correction overwrite or delete an automated AI prediction. Both must be preserved indefinitely in an immutable dual-state schema:

```text
┌────────────────────────────────────────────────────────────────────────┐
│                      CANONICAL EVALUATION RECORD                       │
├────────────────────────────────────────────────────────────────────────┤
│ 1. Immutable Master Image:                                             │
│    - raw_rectified_bgr (Frozen NumPy array buffer, writeable=False)    │
│    - ready_gray (Phase 8.2 prepared representation)                    │
│                                                                        │
│ 2. Immutable Original AI Hypothesis:                                   │
│    - recognized_text: "Dynamic prgrming memoizes subprblms..."         │
│    - confidence_score: 0.62                                            │
│    - detected_script_type: "CURSIVE_HANDWRITING"                       │
│    - model_version: "TrOCR-Base-HTR-v1"                                │
│                                                                        │
│ 3. Immutable Human Review Event (Optional, present if reviewed):       │
│    - event_id: "EVT_20261004_8819"                                     │
│    - examiner_id: "EXAM_MODERATOR_07" (Role: SENIOR_MODERATOR)         │
│    - action: CORRECT                                                   │
│    - human_corrected_text: "Dynamic programming memoizes subproblems"  │
│    - rationale_note: "Cursive condensed letters; verified from ink."   │
│    - review_latency_sec: 14.2                                          │
│    - timestamp_utc: "2026-10-04T01:42:15Z"                            │
│                                                                        │
│ 4. Canonical Accepted State:                                           │
│    - final_accepted_text: "Dynamic programming memoizes subproblems"   │
│    - was_human_reviewed: True                                          │
│    - decision_provenance: "HUMAN_CORRECTED"                            │
└────────────────────────────────────────────────────────────────────────┘
```

### Validation Scope & Boundaries:
- **VALIDATED (In Controlled In-Memory Experiment):**
  - Original AI hypothesis string and confidence score can be preserved immutably.
  - Human correction event can be stored separately without mutating the original AI state.
  - Final canonical outcome can reference the human result while retaining the AI prediction.
  - Original raw state remains fully recoverable from the record.
- **NOT YET VALIDATED (Future Subsystems):**
  - Production database persistence, ORM transaction rollback, distributed audit logging, concurrent reviewer synchronization, session failure recovery, and backend transaction integrity.

---

## 8. AUDIT-TRAIL REQUIREMENTS & RECONSTRUCTION (DEMONSTRATED SCHEMA)

Phase 9 investigated the fields required to ensure complete traceability. Experiment D demonstrated that the proposed serialized schema can answer the six defined auditability/reconstruction questions:

| Defined Auditability / Reconstruction Question | Required Field in Schema | Provenance Source | Verification Method |
| :--- | :--- | :--- | :--- |
| **1. What did the AI predict?** | `ai_hypothesis.recognized_text`, `confidence_score` | Automated model decoder | Exact string and float retrieval |
| **2. What did the human change?** | `human_review_event.human_corrected_text` | Reviewer interface | Character/word Levenshtein diff |
| **3. Why was it changed?** | `human_review_event.rationale_note`, `trigger_reason` | Mandatory examiner input field | Non-empty text verification |
| **4. Who made the change?** | `human_review_event.examiner_id`, `examiner_role` | Proposed schema identity fields | Recorded string matching *(Auth NOT implemented)* |
| **5. When was it decided?** | `human_review_event.timestamp_utc` | Proposed ISO 8601 UTC timestamp | Chronological replay validation |
| **6. Which pipeline version ran?**| `pipeline_version` | Software release manifest tag | Build commit tag verification |

> [!NOTE]
> **AUDITABILITY vs REGULATORY COMPLIANCE:**  
> Experiment D demonstrates that the proposed schema can deterministically reconstruct these six defined questions from serialized data. This establishes **technical auditability**, not formal legal or regulatory compliance (which depends on specific educational authority accreditations in future phases). Furthermore, while `examiner_id` and `examiner_role` fields are proposed, **authentication is explicitly NOT implemented in Phase 9.**

---

## 9. PAGE-LEVEL VS REGION-LEVEL REVIEW ANALYSIS (CONTROLLED SIMULATION)

Phase 9 evaluated three candidate review granularity models in a controlled architectural simulation:

| Granularity Strategy | Workload Volume (% Questions) | Simulation Review Latency | Context Availability | Operational Status |
| :--- | :---: | :---: | :--- | :--- |
| **Strategy 1: Page-Level Monolithic** | 100% (all questions read) | 90.0 s per script | Full visual page context | Evaluated in simulation (high reviewer fatigue risk) |
| **Strategy 2: Isolated Region Crop** | 40% (only flagged crops) | 28.0 s per script | None (cropped box only) | Evaluated in simulation (high handwriting ambiguity risk) |
| **Strategy 3: Context-Preserving Hierarchical** | 40% (flagged questions focused) | 32.0 s per script | Full-page visual context is retained in proposed interface | **PROPOSED / SELECTED FOR FUTURE VALIDATION** |

### Simulation Findings & Real-World Caveat:
- **In Controlled Simulation:** Context-preserving hierarchical review achieved a latency of $32.0\text{s}$ (compared to $90.0\text{s}$ for monolithic review) while retaining full-page visual context.
- **Validation Caveat:** These results represent a **controlled architectural simulation**. Real examiner accuracy, cognitive workload, fatigue over multi-hour grading sessions, and ergonomic usability remain unvalidated and require Phase 11 field trials.

---

## 10. FEEDBACK LOOP ELIGIBILITY (PROPOSED — REQUIRES PHASE 11 CALIBRATION)

A critical failure mode of automated machine learning systems is blindly ingesting human corrections as ground-truth training data. Examiners make typos, guess under time pressure, and occasionally misread messy handwriting.

Phase 9 investigates four candidate qualification checks:

1. **Check 1 (Image Quality Precondition):** Input image must be free of fatal blur, glare, or border clipping. Defective captures are marked `DISQUALIFIED_DEFECTIVE`.
2. **Check 2 (Ambiguity Flag Verification):** Corrections resulting from `UNCLEAR` or `ESCALATE` actions must be marked `DISQUALIFIED_DEFECTIVE`.
3. **Check 3 (Reviewer Consensus Measurement):** Reviewer agreement should be measured; single-examiner edits on difficult cursive should not automatically become reference data without secondary consensus.
4. **Check 4 (Completeness Verification):** Edits must cover the complete answer block without trailing truncation. Partial edits are marked `PROVISIONAL_AUDIT_ONLY`.

> [!IMPORTANT]
> **QUALIFICATION STATUS (PROPOSED / NOT FROZEN):**  
> While the four qualification concepts are sound, numerical consensus criteria (such as a $90\%$ agreement cutoff or specific character length floors) were evaluated in Experiment E solely as **exploratory experimental criteria**. They are **NOT frozen production thresholds** and require empirical calibration against multi-annotator datasets in Phase 11.

---

## 11. HUMAN REVIEW SAFETY PRINCIPLES

1. **Non-Destructive Dual State:** Human actions modify the *canonical outcome*, never the *original AI hypothesis* or *raw capture image*.
2. **Traceability of Disagreement:** Examiner overrides must preserve the original AI prediction so that model error distributions can be audited over time.
3. **Review Does Not Imply Model Failure:** Routing to review indicates that the system correctly recognized its own epistemic boundary.
4. **Preservation of Explicit Ambiguity:** If content is genuinely undecipherable, it must be recorded as `UNCLEAR` or `REJECT`; it must never be coerced into speculative text.
5. **No Blind Training Ingestion:** Model fine-tuning pipelines must consume only records that have passed rigorous qualification filters.

---

## 12. INVESTIGATION EXPERIMENTS SUMMARY

The five controlled experiments executed in [`phase9/01_human_review_boundary_investigation.py`](file:///C:/Users/bunde/OneDrive/Desktop/EvalAI/AI-EVAL-OpenCV/phase9/01_human_review_boundary_investigation.py) demonstrated:

- **Experiment A (Trigger Taxonomy):** Mapped 10 representative physical and layout edge cases across CP1–CP4 without unclassified cases.
- **Experiment B (Granularity Simulation):** Measured simulation latencies ($90.0\text{s}$ monolithic vs $28.0\text{s}$ isolated vs $32.0\text{s}$ hierarchical), demonstrating the conceptual viability of context-preserving review.
- **Experiment C (Non-Destructive Preservation):** Verified in-memory immutability; original AI text and confidence scores remained $100\%$ identical after correction.
- **Experiment D (Audit Replay):** Verified that the serialized data structure allows deterministic reconstruction of all 6 defined auditability questions.
- **Experiment E (Feedback Eligibility):** Demonstrated that an automated filter can successfully segregate consensus corrections from defective/incomplete edits under simulated rules.

---

## 13. FINDINGS & ARCHITECTURAL CONCLUSIONS

1. **Multi-Point Review is Necessary:** Restricting review solely to the end of the pipeline wastes compute and risks compounding errors. Gating physical intake (CP1) and readiness (CP2) early protects downstream models.
2. **Context-Preserving Hierarchical Granularity is the Recommended Target:** Retaining full-page context while bounding the editing focus provides the strongest conceptual balance between speed and contextual accuracy.
3. **Audit Immutability is Achievable in Data Models:** In-memory immutable dataclass contracts guarantee zero overwriting prior to database commitment.

---

## 14. LIMITATIONS

1. **Simulation-Only Ergonomics:** Examiner latencies and fatigue were evaluated using simulated models. Real examiner behavior across large live examination cohorts requires Phase 11 field calibration.
2. **No Web UI Implemented:** The examiner interaction model is currently architectural; no React/Vue frontend or WebSocket streaming protocol was created.
3. **No Database Persistence:** Audit payloads are currently evaluated as serialized in-memory records; database schemas, indexing, and ACID transactions belong to future backend milestones.
4. **Authentication Not Implemented:** Reviewer roles and credentials are proposed data fields, not cryptographically authenticated identities.

---

## 15. FUTURE IMPLEMENTATION REQUIREMENTS (FOR PHASE 10 / 11)

When backend integration begins in future milestones, the following components must be built based on Phase 9 contracts:
1. **Examiner Queue Dispatcher:** Routes CP1–CP4 events to examiners based on credentials and role tiers.
2. **Audit Logging Storage:** Persistent append-only write-ahead log for all `HumanReviewEvent` payloads.
3. **Hierarchical Annotation Canvas:** Web-based image viewer rendering full-page scans with highlighted active question bounding boxes.

---

## 16. PHASE 10 DEPENDENCIES

Phase 10 (Backend & Orchestration Integration) will reference Phase 9 for:
- Data contract specifications: `CanonicalEvaluationRecord`, `HumanReviewEvent`, `BoundingBox`.
- Routing enums: `ReviewCheckpoint`, `ReviewTriggerCategory`, `HumanReviewAction`.
- Qualification logic: `FeedbackEligibilityVerdict`.

---

## 17. FINAL GOVERNANCE WORDING & MILESTONE VERDICT

```text
Phase 9 Investigation
→ COMPLETE / APPROVED AT ARCHITECTURAL-INVESTIGATION LEVEL

Human review boundary
→ FOUR-CHECKPOINT MODEL PROPOSED / REQUIRES FUTURE VALIDATION

Trigger taxonomy
→ INVESTIGATED / CANDIDATE TAXONOMY

Review action model
→ INVESTIGATED / PROPOSED

AI output preservation
→ VALIDATED IN CONTROLLED IN-MEMORY EXPERIMENT

Audit trail
→ AUDITABILITY SCHEMA DEMONSTRATED

Page vs region review
→ CONTROLLED SIMULATION COMPLETED / REAL EXAMINER VALIDATION PENDING

Feedback qualification
→ PROPOSED / REQUIRES CALIBRATION

Production UI
→ NOT IMPLEMENTED

Production database
→ NOT IMPLEMENTED

Authentication
→ NOT IMPLEMENTED

Production OCR/HTR classifier
→ NOT IMPLEMENTED

Production AI Examiner
→ NOT IMPLEMENTED

Hard human-review thresholds
→ NOT FROZEN

Phase 2–8.5
→ STRICTLY FROZEN / UNMODIFIED

Phase 10
→ NOT STARTED

Phase 11
→ REQUIRED FOR REAL EXAMINER / THRESHOLD / WORKLOAD CALIBRATION
```
