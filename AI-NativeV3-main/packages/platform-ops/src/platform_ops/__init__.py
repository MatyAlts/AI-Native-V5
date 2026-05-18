"""Platform ops — scripts operacionales."""

from platform_ops.ab_testing import (
    ABComparisonReport,
    EpisodeForComparison,
    ProfileComparisonResult,
    compare_profiles,
)
from platform_ops.academic_export import (
    AcademicExporter,
    CohortDataset,
    EpisodeRecord,
)
from platform_ops.adversarial_aggregation import (
    aggregate_adversarial_events,
)
from platform_ops.audit import (
    AccessEvent,
    AuditEngine,
    BruteForceRule,
    CrossTenantAccessRule,
    RepeatedAuthFailuresRule,
    Severity,
    SuspiciousAccess,
)
from platform_ops.cii_alerts import (
    ALERTS_VERSION,
    MIN_STUDENTS_FOR_QUARTILES,
    compute_alerts_payload,
    compute_cohort_quartiles_payload,
    compute_cohort_slopes_stats,
    compute_student_alerts,
    position_in_quartiles,
)
from platform_ops.cii_longitudinal import (
    CII_LONGITUDINAL_VERSION,
    MIN_EPISODES_FOR_LONGITUDINAL,
    compute_cii_evolution_longitudinal,
    compute_evolution_per_template,
    compute_evolution_per_unidad,
    compute_mean_slope,
)
from platform_ops.export_worker import (
    ExportJob,
    ExportJobStore,
    ExportWorker,
    JobStatus,
)
from platform_ops.feature_flags import (
    FeatureFlags,
    FeatureNotDeclaredError,
    FlagsSnapshot,
)
from platform_ops.kappa_analysis import (
    CATEGORIES,
    KappaRating,
    KappaResult,
    compute_cohen_kappa,
    format_report,
)
from platform_ops.ldap_federation import (
    LDAPConfig,
    LDAPFederationError,
    LDAPFederationSpec,
    LDAPFederator,
    LDAPGroupMapping,
)
from platform_ops.longitudinal import (
    APPROPRIATION_ORDINAL,
    ClassificationPoint,
    CohortProgression,
    StudentTrajectory,
    build_trajectories,
    summarize_cohort,
)
from platform_ops.privacy import (
    AnonymizationReport,
    ExportedData,
    anonymize_student,
    export_student_data,
)
from platform_ops.real_datasources import (
    RealCohortDataSource,
    RealLongitudinalDataSource,
    set_tenant_rls,
)
from platform_ops.tenant_onboarding import (
    KeycloakClient,
    KeycloakConfig,
    OnboardingReport,
    TenantOnboarder,
    TenantSpec,
)
from platform_ops.tenant_secrets import (
    SecretNotFoundError,
    TenantSecretConfig,
    TenantSecretResolver,
    get_resolver,
)

__all__ = [
    "ALERTS_VERSION",
    "APPROPRIATION_ORDINAL",
    "CATEGORIES",
    "CII_LONGITUDINAL_VERSION",
    "MIN_EPISODES_FOR_LONGITUDINAL",
    "MIN_STUDENTS_FOR_QUARTILES",
    "ABComparisonReport",
    "AcademicExporter",
    "AccessEvent",
    "AnonymizationReport",
    "AuditEngine",
    "BruteForceRule",
    "ClassificationPoint",
    "CohortDataset",
    "CohortProgression",
    "CrossTenantAccessRule",
    "EpisodeForComparison",
    "EpisodeRecord",
    "ExportJob",
    "ExportJobStore",
    "ExportWorker",
    "ExportedData",
    "FeatureFlags",
    "FeatureNotDeclaredError",
    "FlagsSnapshot",
    "JobStatus",
    "KappaRating",
    "KappaResult",
    "KeycloakClient",
    "KeycloakConfig",
    "LDAPConfig",
    "LDAPFederationError",
    "LDAPFederationSpec",
    "LDAPFederator",
    "LDAPGroupMapping",
    "OnboardingReport",
    "ProfileComparisonResult",
    "RealCohortDataSource",
    "RealLongitudinalDataSource",
    "RepeatedAuthFailuresRule",
    "SecretNotFoundError",
    "Severity",
    "StudentTrajectory",
    "SuspiciousAccess",
    "TenantOnboarder",
    "TenantSecretConfig",
    "TenantSecretResolver",
    "TenantSpec",
    "aggregate_adversarial_events",
    "anonymize_student",
    "build_trajectories",
    "compare_profiles",
    "compute_alerts_payload",
    "compute_cii_evolution_longitudinal",
    "compute_cohen_kappa",
    "compute_cohort_quartiles_payload",
    "compute_cohort_slopes_stats",
    "compute_evolution_per_template",
    "compute_evolution_per_unidad",
    "compute_mean_slope",
    "compute_student_alerts",
    "export_student_data",
    "format_report",
    "get_resolver",
    "position_in_quartiles",
    "set_tenant_rls",
    "summarize_cohort",
]
