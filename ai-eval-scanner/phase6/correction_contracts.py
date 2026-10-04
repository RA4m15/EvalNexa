"""
phase6/correction_contracts.py

AI-EVAL PHASE 6.2: PRODUCTION CORRECTION ARCHITECTURE CONTRACTS
================================================================

PURPOSE:
Defines the clean, production-grade architecture contracts, interfaces,
state-machine transitions, and data models for intelligent document correction.

STRICT PHASE 6.2 CONSTRAINTS:
1. ARCHITECTURE / DESIGN ONLY: Zero image transformation execution logic.
2. ZERO MODIFICATION TO FROZEN CODE: Phase 2, 3, 4, and 5 modules are untouched.
3. NO PHASE 7 RESCAN AUTOMATION: rescan_required=True remains a pure data signal.
4. SAFE-STATE REVERSIBILITY INVARIANT: Unverified candidates NEVER become safe states.
5. NO FROZEN UNIVERSAL THRESHOLDS: All thresholds are configurable provisional baselines.
6. PRESERVE RAW RECTIFIED BGR: Original rectified BGR buffer is preserved throughout.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import Enum, auto
from typing import Any, Dict, List, Optional, Sequence, Tuple, Union

import numpy as np

# Import frozen Phase 5 contracts for type annotations and integration
from phase5.production_quality_assessment import (
    QualityAssessmentResult,
    QualityEvidenceProfile,
    FatalDefectRecord,
    QualityGateConfig,
)


# ===========================================================================
# 1. CORE ENUMERATIONS & TAXONOMY
# ===========================================================================

class RecoverabilityClass(str, Enum):
    """
    Defect recoverability taxonomy approved in Phase 6.1 investigation.
    """
    RECOVERABLE = "RECOVERABLE"
    """High confidence improvement possible without altering genuine handwriting."""

    CONDITIONALLY_RECOVERABLE = "CONDITIONALLY_RECOVERABLE"
    """Correction may help, but intervention permitted ONLY if multi-dimensional verification confirms zero information loss."""

    UNRECOVERABLE = "UNRECOVERABLE"
    """Physical information is missing or saturated in captured photons. Algorithmic synthesis is strictly prohibited."""


class DefectConditionCategory(str, Enum):
    """
    Document condition and defect categories identified by Phase 5 assessment.
    """
    ILLUMINATION_SHADOW = "ILLUMINATION_SHADOW"
    LOW_STROKE_CONTRAST = "LOW_STROKE_CONTRAST"
    OPTICAL_SOFTNESS = "OPTICAL_SOFTNESS"
    SUBSTRATE_NOISE = "SUBSTRATE_NOISE"
    VERSO_BLEED_THROUGH = "VERSO_BLEED_THROUGH"
    SPECULAR_GLARE = "SPECULAR_GLARE"
    PHYSICAL_OCCLUSION = "PHYSICAL_OCCLUSION"
    BASELINE_SKEW = "BASELINE_SKEW"
    TEXT_CLIPPING = "TEXT_CLIPPING"
    INK_DROPOUT = "INK_DROPOUT"
    CLEAN_NO_OP = "CLEAN_NO_OP"


class VerificationVerdict(str, Enum):
    """
    Evaluation verdict from the multi-dimensional safety verification gate.
    """
    PASS = "PASS"
    """Correction verified safe across all dimensions. Promoted to new SafeImageState."""

    FAIL = "FAIL"
    """Safety violation detected (e.g. stroke loss, halo ringing). Automatic rollback to previous SafeImageState."""

    INSUFFICIENT_EVIDENCE = "INSUFFICIENT_EVIDENCE"
    """Evidence is inconclusive or below measurement confidence. Pipeline retains previous verified safe state."""


class CorrectionStatus(str, Enum):
    """
    Lifecycle status of a correction candidate.
    """
    PROPOSED = "PROPOSED"
    IN_FLIGHT = "IN_FLIGHT"
    COMMITTED = "COMMITTED"
    ROLLED_BACK = "ROLLED_BACK"
    REJECTED_UNSAFE = "REJECTED_UNSAFE"
    BLOCKED_DEPENDENCY = "BLOCKED_DEPENDENCY"
    SKIPPED_UNNECESSARY = "SKIPPED_UNNECESSARY"
    HALTED_FATAL = "HALTED_FATAL"


# ===========================================================================
# 2. CENTRALIZED PROVISIONAL CONFIGURATION
# ===========================================================================

@dataclass(frozen=True)
class CorrectionVerificationConfig:
    """
    Centralized provisional calibration baselines for post-correction verification.
    
    CRITICAL ARCHITECTURAL MANDATE:
    These are provisional calibration baselines derived from Phase 6.1 investigation.
    They are NOT immutable universal truths and will be refined during Phase 11.
    No magic numbers are scattered elsewhere in the code.
    """
    # Stroke skeleton survival baseline (fraction of 1-pixel skeleton retained)
    min_thin_stroke_survival: float = 0.80

    # Maximum acceptable attenuation of faint stroke pixels
    max_faint_stroke_loss: float = 0.15

    # Maximum allowable gradient overshoot (ringing halos) around stroke perimeter
    # PROVISIONAL CALIBRATION BASELINE: Not scientifically frozen; requires Phase 11 real-world validation.
    max_halo_gain: float = 15.0

    # Local-paper-relative faint stroke contrast boundaries [min, max] intensity levels
    # PROVISIONAL CALIBRATION BASELINE: Separates faint strokes from substrate noise and dark pen.
    min_faint_contrast_delta: float = 10.0
    max_faint_contrast_delta: float = 35.0
    local_bg_kernel_base: int = 25

    # Maximum allowable standard deviation increase on flat paper substrate
    max_substrate_noise_gain: float = 3.0

    # Allowable divergence in connected component count (fragmentation / merging)
    max_connected_component_ratio_deviation: float = 0.20

    # Minimum contrast delta gain for low-contrast intervention to be deemed effective
    min_contrast_delta_gain: float = 15.0

    # Minimum acutance gain required for sharpening intervention to be deemed effective
    min_acutance_gain: float = 15.0

    # Maximum allowable baseline skew angle after deskew correction (degrees)
    max_post_skew_angle_deg: float = 1.0

    # Zero tolerance for stroke loss during bleed-through suppression
    max_bleed_through_stroke_loss: float = 0.05


@dataclass(frozen=True)
class CorrectionPlanningConfig:
    """
    Configuration parameters guiding the dynamic correction planner.
    """
    # Maximum correction iterations allowed before terminal evaluation
    max_planner_iterations: int = 5

    # Whether to enforce strict topological verification
    enforce_strict_topology: bool = True

    # Minimum condition deficit required to trigger candidate generation
    min_shadow_deficit_trigger: float = 40.0
    min_contrast_deficit_trigger: float = 30.0
    min_acutance_deficit_trigger: float = 180.0
    min_noise_sigma_trigger: float = 8.0
    min_skew_angle_trigger_deg: float = 3.0


# ===========================================================================
# 3. VERIFICATION EVIDENCE & SAFE STATE
# ===========================================================================

@dataclass
class CorrectionVerificationEvidence:
    """
    Empirical multi-dimensional evidence measured strictly after a candidate correction.
    """
    thin_stroke_survival_ratio: float
    faint_stroke_loss: float
    halo_overshoot_gain: float
    substrate_noise_delta: float
    connected_component_ratio: float
    background_mean_drift: float
    stroke_intensity_delta_gain: float
    normalized_acutance_gain: float
    verdict: VerificationVerdict
    rejection_reasons: List[str] = field(default_factory=list)
    evidence_notes: List[str] = field(default_factory=list)
    evaluated_at_epoch: float = field(default_factory=time.time)


@dataclass(frozen=True)
class SafeImageState:
    """
    Immutable representation of a VERIFIED-SAFE image state.
    
    CORE INVARIANT:
    A candidate image that has NOT passed multi-dimensional verification
    can NEVER become a SafeImageState.
    """
    state_id: str
    version_index: int
    parent_state_id: Optional[str]
    image_gray: np.ndarray
    image_bgr: Optional[np.ndarray]
    raw_rectified_bgr: np.ndarray  # Invariant: Raw rectified BGR is preserved at all versions
    applied_operator_id: Optional[str]
    quality_profile: Optional[QualityEvidenceProfile]
    verification_evidence: Optional[CorrectionVerificationEvidence]
    is_verified_safe: bool = True
    created_timestamp: float = field(default_factory=time.time)

    def __post_init__(self) -> None:
        if not self.is_verified_safe:
            raise ValueError(
                f"Invariant Violation: Cannot construct SafeImageState '{self.state_id}' "
                "with is_verified_safe=False. Unverified candidate images cannot become safe states."
            )
        # Enforce physical numpy buffer immutability (hardware-level write protection)
        if isinstance(self.image_gray, np.ndarray):
            self.image_gray.flags.writeable = False
        if isinstance(self.raw_rectified_bgr, np.ndarray):
            self.raw_rectified_bgr.flags.writeable = False
        if self.image_bgr is not None and isinstance(self.image_bgr, np.ndarray):
            self.image_bgr.flags.writeable = False


# ===========================================================================
# 4. CANDIDATES, AUDIT TRAILS & RESULTS
# ===========================================================================

@dataclass
class CorrectionCandidate:
    """
    Formal representation of a candidate correction operator under consideration.
    """
    candidate_id: str
    operator_id: str
    condition_category: DefectConditionCategory
    recoverability_class: RecoverabilityClass
    dependencies: List[str] = field(default_factory=list)
    prerequisites: Dict[str, Any] = field(default_factory=dict)
    expected_benefit: str = ""
    risk_category: str = ""
    is_reversible: bool = True
    is_verification_mandatory: bool = True
    priority: int = 100
    config_parameters: Dict[str, Any] = field(default_factory=dict)


@dataclass
class AppliedCorrectionRecord:
    """
    Audit record for a successfully applied and verified correction operator.
    """
    candidate_id: str
    operator_id: str
    condition_addressed: DefectConditionCategory
    from_state_id: str
    to_state_id: str
    verification_evidence: CorrectionVerificationEvidence
    execution_latency_ms: float
    verification_latency_ms: float


@dataclass
class RejectedCorrectionRecord:
    """
    Audit record for a candidate correction rejected by verification gate.
    """
    candidate_id: str
    operator_id: str
    condition_addressed: DefectConditionCategory
    at_state_id: str
    verification_evidence: CorrectionVerificationEvidence
    rejection_reasons: List[str]
    rolled_back_to_state_id: str


@dataclass
class RollbackEventRecord:
    """
    Formal audit of a safe-state rollback event.
    """
    event_id: str
    rejected_candidate_id: str
    from_candidate_state_id: str
    restored_safe_state_id: str
    trigger_reason: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class CorrectionAuditEntry:
    """
    Chronological trace entry of planner deliberations and execution steps.
    """
    step_index: int
    action_type: str  # "PLAN", "EXECUTE", "VERIFY", "ACCEPT", "ROLLBACK", "HALT"
    details: str
    timestamp: float = field(default_factory=time.time)


@dataclass
class CorrectedDocumentResult:
    """
    Unified Production Output Contract for Phase 6.
    """
    status: str  # "CORRECTED_VERIFIED", "PRISTINE_PASS_THROUGH", "PARTIAL_SAFE_FALLBACK", "UNRECOVERABLE_FATAL"
    final_safe_state: SafeImageState
    corrected_gray: np.ndarray
    preserved_raw_bgr: np.ndarray
    binary_derivative: Optional[np.ndarray]
    applied_corrections: List[AppliedCorrectionRecord]
    rejected_corrections: List[RejectedCorrectionRecord]
    rollback_events: List[RollbackEventRecord]
    audit_trail: List[CorrectionAuditEntry]
    rescan_required: bool
    human_review_required: bool
    overall_recoverability: RecoverabilityClass
    quality_assessment_initial: QualityAssessmentResult
    quality_assessment_final: Optional[QualityAssessmentResult]
    total_processing_latency_ms: float
    metadata: Dict[str, Any] = field(default_factory=dict)


# ===========================================================================
# 5. ABSTRACT INTERFACES & EXTENSIBLE EXTENSION POINTS
# ===========================================================================

class CorrectionOperator(ABC):
    """
    Abstract Base Class for all pluggable correction operators.
    Operators contain execution metadata and application logic, but are strictly
    isolated from the verified safe state until post-correction verification passes.
    """
    @property
    @abstractmethod
    def operator_id(self) -> str:
        """Unique machine-readable operator identifier."""
        raise NotImplementedError

    @property
    @abstractmethod
    def supported_condition(self) -> DefectConditionCategory:
        """Defect condition category this operator is designed to remediate."""
        raise NotImplementedError

    @property
    @abstractmethod
    def recoverability_class(self) -> RecoverabilityClass:
        """Default recoverability classification for this operator."""
        raise NotImplementedError

    @property
    @abstractmethod
    def prerequisite_operators(self) -> List[str]:
        """Operator IDs that must be completed/verified prior to executing this operator."""
        raise NotImplementedError

    @abstractmethod
    def estimate_applicability(
        self,
        current_state: SafeImageState,
        quality_profile: QualityEvidenceProfile
    ) -> Tuple[bool, str]:
        """
        Evaluate whether this operator is applicable to the current state.
        Returns (is_applicable, rationale).
        """
        raise NotImplementedError

    @abstractmethod
    def apply(
        self,
        candidate_image: np.ndarray,
        config: Dict[str, Any]
    ) -> np.ndarray:
        """
        Execute candidate transformation on an isolated image buffer.
        MUST NOT mutate the current safe state directly.
        """
        raise NotImplementedError


class OperatorRegistry(ABC):
    """
    Registry managing discovery, registration, and dependency inspection of operators.
    """
    @abstractmethod
    def register_operator(self, operator: CorrectionOperator) -> None:
        """Register a new correction operator."""
        raise NotImplementedError

    @abstractmethod
    def get_operator(self, operator_id: str) -> Optional[CorrectionOperator]:
        """Retrieve an operator by ID."""
        raise NotImplementedError

    @abstractmethod
    def list_operators_for_condition(
        self,
        condition: DefectConditionCategory
    ) -> List[CorrectionOperator]:
        """List all operators addressing a specific condition."""
        raise NotImplementedError


class CorrectionVerificationGate(ABC):
    """
    Interface for the multi-dimensional safety verification gate.
    """
    @abstractmethod
    def verify_candidate(
        self,
        before_state: SafeImageState,
        candidate_image: np.ndarray,
        candidate: CorrectionCandidate,
        config: CorrectionVerificationConfig
    ) -> CorrectionVerificationEvidence:
        """
        Measure multi-dimensional safety metrics comparing candidate image against before_state.
        Returns complete VerificationEvidence with PASS, FAIL, or INSUFFICIENT_EVIDENCE verdict.
        """
        raise NotImplementedError


class IntelligentCorrectionPlanner(ABC):
    """
    Interface for the dynamic, non-linear correction planner.
    """
    @abstractmethod
    def plan_next_candidate(
        self,
        current_state: SafeImageState,
        quality_assessment: QualityAssessmentResult,
        applied_candidates: Sequence[AppliedCorrectionRecord],
        rejected_candidates: Sequence[RejectedCorrectionRecord],
        registry: OperatorRegistry,
        config: CorrectionPlanningConfig
    ) -> Optional[CorrectionCandidate]:
        """
        Inspect current safe state and quality evidence to select the NEXT single candidate operator.
        Returns None when all degradations are resolved or no safe operators remain.
        """
        raise NotImplementedError


class CorrectionExecutionEngine(ABC):
    """
    Interface for the atomic execution and rollback engine.
    """
    @abstractmethod
    def execute_and_verify(
        self,
        current_state: SafeImageState,
        candidate: CorrectionCandidate,
        operator: CorrectionOperator,
        verifier: CorrectionVerificationGate,
        config: CorrectionVerificationConfig
    ) -> Tuple[SafeImageState, Union[AppliedCorrectionRecord, RejectedCorrectionRecord]]:
        """
        Atomically executes candidate on an isolated buffer, verifies safety, and either:
        - Returns (new_safe_state, AppliedCorrectionRecord) on PASS
        - Returns (current_state, RejectedCorrectionRecord) on FAIL / INSUFFICIENT_EVIDENCE
        """
        raise NotImplementedError
