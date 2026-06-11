"""ko-pii — rule-based PII detection for Korean public-sector documents.

Public API
----------
- ``Anonymizer`` / ``ProcessingMode`` / ``Action`` — high-level orchestration.
- ``ReversibleVault`` — reversible pseudonymization storage.
- ``detect_all`` — run every detector at once.
- ``DetectionResult`` / ``RiskLevel`` — core data types.
- ``tokenize`` / ``redact`` / ``hashed`` — substitution primitives.
"""
from ko_pii.analytics import (
    AttributeClass, CombinedRiskReport,
    classify_attribute, score_combined_risk,
    KAnonymityReport, k_anonymity, evaluate_dataset,
)
from ko_pii.integrations import (
    SecondaryDetector,
    MockSecondaryDetector,
    MergeMode,
    merge_detections,
    get_privacy_filter_adapter,
)
from ko_pii.anonymizer import Anonymizer, AnonymizationResult, DetectionRecord
from ko_pii.core.modes import Action, ProcessingMode
from ko_pii.core.types import DetectionResult, RiskLevel
from ko_pii.detect import detect_all
from ko_pii.modes.fpe import fpe
from ko_pii.modes.hashed import hashed
from ko_pii.modes.partial import partial, mask_value
from ko_pii.modes.redact import redact
from ko_pii.modes.tokenize import tokenize
from ko_pii.vault.reversible import ReversibleVault, VaultEntry

__version__ = "1.15.1"  # pyproject.toml 과 동기화 (tests/unit/test_version.py 가드)

__all__ = [
    "Anonymizer",
    "AnonymizationResult",
    "DetectionRecord",
    "Action",
    "ProcessingMode",
    "DetectionResult",
    "RiskLevel",
    "detect_all",
    "tokenize",
    "redact",
    "hashed",
    "partial",
    "mask_value",
    "fpe",
    "ReversibleVault",
    "VaultEntry",
    # analytics
    "AttributeClass",
    "CombinedRiskReport",
    "classify_attribute",
    "score_combined_risk",
    "KAnonymityReport",
    "k_anonymity",
    "evaluate_dataset",
    # integrations
    "SecondaryDetector",
    "MockSecondaryDetector",
    "MergeMode",
    "merge_detections",
    "get_privacy_filter_adapter",
    "__version__",
]
