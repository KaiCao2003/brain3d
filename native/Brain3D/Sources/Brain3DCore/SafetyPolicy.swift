import Foundation

public enum SafetyPolicy {
    public static let animalResearchOnly = "Animal research only — not for human or clinical use"
    public static let planningOnlyNotice =
        "Animal research planning only. Not validated for surgical navigation. "
            + "Verify coordinates, probe geometry, vessel data, registration, and trajectory independently."
    public static let supportedAtlasIdentifier = "allen_mouse_25um"
    public static let supportedAtlasVersion = "1.2"
    public static let supportedAtlasDisplayName = "allen_mouse_25um v1.2"

    public static let populationReferenceDOI = "10.17632/stxvn5sv44.1"
    public static let populationReferenceVersion = 1
    public static let populationReferenceContributor = "Yongsoo Kim"
    public static let populationReferenceRepository = "Mendeley Data v1"
    public static let populationReferenceLicense = "CC BY 4.0"
    public static let populationReferenceLandingPage =
        "https://data.mendeley.com/datasets/stxvn5sv44/1"
    public static let populationReferencePaperURL =
        "https://doi.org/10.1016/j.celrep.2022.110978"
    public static let populationReferenceArchiveByteCount = 311_493_514
    public static let populationReferenceArchiveSHA256 =
        "c715c92ad153bff7f676b883f47108f886147e5d6fcd4502bcc04a0f92ed98fe"
    public static let populationReferenceDefaultOpacity = 0.65

    public static let populationDensityCaveat =
        "Symmetrized population reference vascular length density — four fixed adult C57BL/6 brains; "
        + "100 µm local window; not individual vessel paths and not subject-specific."
}

public enum WorkspaceMode: String, CaseIterable, Codable, Sendable {
    case dorsal = "Dorsal"
    case coronal = "Coronal"
    case sagittal = "Sagittal"
    case horizontal = "Horizontal"
    case threeDimensional = "3D"

    public var accessibilityDescription: String {
        switch self {
        case .dorsal:
            "Dorsal planning view"
        case .coronal:
            "Coronal atlas slice"
        case .sagittal:
            "Sagittal atlas slice"
        case .horizontal:
            "Horizontal atlas slice"
        case .threeDimensional:
            "Three-dimensional planning view"
        }
    }
}
