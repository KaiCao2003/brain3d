import Brain3DCore
import Foundation
import Testing
@testable import Brain3DApp

@Suite("Major-vessel display preference", .serialized)
@MainActor
struct MajorVesselDisplayPreferenceTests {
    @Test("Display diameter snaps, clamps, and persists independently of source data")
    func persistence() throws {
        let suiteName = "Brain3DTests.vessel-display.\(UUID().uuidString)"
        let preferences = try #require(UserDefaults(suiteName: suiteName))
        defer { preferences.removePersistentDomain(forName: suiteName) }

        let initial = PlannerViewModel(
            launchConfiguration: nil,
            preferences: preferences
        )
        #expect(
            initial.minimumVisibleVesselDiameterMicrometres
                == MajorVesselDisplayFilter.defaultMinimumDiameterMicrometres
        )

        initial.setMinimumVisibleVesselDiameterMicrometres(83)
        #expect(initial.minimumVisibleVesselDiameterMicrometres == 80)
        #expect(
            preferences.double(
                forKey: PlannerViewModel.minimumVisibleVesselDiameterPreferenceKey
            ) == 80
        )

        let restored = PlannerViewModel(
            launchConfiguration: nil,
            preferences: preferences
        )
        #expect(restored.minimumVisibleVesselDiameterMicrometres == 80)

        restored.setMinimumVisibleVesselDiameterMicrometres(10)
        #expect(
            restored.minimumVisibleVesselDiameterMicrometres
                == MajorVesselContract.minimumIncludedDiameterMicrometres
        )
        restored.setMinimumVisibleVesselDiameterMicrometres(1_000)
        #expect(
            restored.minimumVisibleVesselDiameterMicrometres
                == MajorVesselDisplayFilter.maximumMinimumDiameterMicrometres
        )
    }
}
