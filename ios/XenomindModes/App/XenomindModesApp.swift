import FamilyControls
import ManagedSettings
import SwiftUI
import UIKit

private enum DeviceMode: String, CaseIterable, Identifiable, Hashable {
    case focus
    case rehearsal
    case rest

    var id: String { rawValue }

    var title: String {
        switch self {
        case .focus: return "Focus"
        case .rehearsal: return "Rehearsal"
        case .rest: return "Rest"
        }
    }

    var storeName: ManagedSettingsStore.Name {
        ManagedSettingsStore.Name("io.xenomind.modes.\(rawValue)")
    }

    var selectionKey: String { "xenomind.mode-selection.\(rawValue)" }
}

private let activeModeCallbackKey = "xenomind.active-mode-callback"

@main
struct XenomindModesApp: App {
    var body: some Scene {
        WindowGroup {
            ModeControlView()
        }
    }
}

@MainActor
private struct ModeControlView: View {
    @State private var selectedMode: DeviceMode = .focus
    @State private var selection = FamilyActivitySelection()
    @State private var activeMode = UserDefaults.standard.string(forKey: "xenomind.active-mode")
        .flatMap(DeviceMode.init(rawValue:))
    @State private var isPickerPresented = false
    @State private var pendingActivation = false
    @State private var returnAfterPicker = false
    @State private var stoppedDuringConfig = false
    @State private var callbackURL: URL?
    @State private var message = "Choose a mode and select apps or websites to block."
    @State private var errorMessage = ""
    @State private var isErrorPresented = false
    @ObservedObject private var authorizationCenter = AuthorizationCenter.shared

    var body: some View {
        NavigationStack {
            Form {
                Section("Device mode") {
                    Picker("Mode", selection: $selectedMode) {
                        ForEach(DeviceMode.allCases) { mode in
                            Text(mode.title).tag(mode)
                        }
                    }

                    Text(activeMode.map { "\($0.title) mode is active on this iPhone." }
                         ?? "No mode is active.")
                        .font(.subheadline)
                        .foregroundStyle(activeMode == nil ? Color.secondary : Color.mint)
                }

                Section("Blocked apps and websites") {
                    Text(selectionSummary)
                        .font(.subheadline)
                        .foregroundStyle(.secondary)

                    Button("Choose apps, categories, or websites") {
                        Task { await authorizeAndChoose() }
                    }
                }

                Section {
                    Button("Start \(selectedMode.title) mode") {
                        pendingActivation = true
                        Task { await authorizeAndStart() }
                    }

                    Button("End active mode", role: .destructive) {
                        let stopCallback = callbackURL ?? UserDefaults.standard.string(forKey: activeModeCallbackKey)
                            .flatMap(URL.init(string:))
                        endAllModes()
                        completeHandoff(modeAction: "stop", callbackOverride: stopCallback)
                        message = "All Xenomind mode shields have been removed."
                    }
                    .disabled(activeMode == nil)
                }

                Section("Status") {
                    Text(message)
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                    Text(authorizationDescription)
                        .font(.footnote)
                        .foregroundStyle(.secondary)
                }
            }
            .navigationTitle("Xenomind Modes")
            .familyActivityPicker(
                headerText: "Select what \(selectedMode.title) mode can block",
                footerText: "Xenomind stores only Apple's private selection tokens on this iPhone.",
                isPresented: $isPickerPresented,
                selection: $selection
            )
            .onAppear(perform: loadSelection)
            .onChange(of: selectedMode) { _ in loadSelection() }
            .onChange(of: selection) { newSelection in
                saveSelection(newSelection, for: selectedMode)
                if activeMode == selectedMode {
                    if hasSelection { apply(newSelection, for: selectedMode) }
                    else {
                        stoppedDuringConfig = true
                        endAllModes()
                    }
                }
            }
            .onChange(of: isPickerPresented) { presented in
                guard !presented else { return }
                if pendingActivation {
                    pendingActivation = false
                    guard hasSelection else {
                        message = "No apps or websites are selected. Choose at least one before starting this mode."
                        callbackURL = nil
                        return
                    }
                    apply(selection, for: selectedMode)
                    activeMode = selectedMode
                    UserDefaults.standard.set(selectedMode.rawValue, forKey: "xenomind.active-mode")
                    message = "\(selectedMode.title) mode is active. Apple's Screen Time controls now shield the selected apps and websites."
                    saveActiveCallback()
                    completeHandoff(modeAction: "activate")
                } else if returnAfterPicker {
                    returnAfterPicker = false
                    message = "Saved the blocked items for \(selectedMode.title) mode."
                    completeHandoff(modeAction: stoppedDuringConfig ? "stop" : nil)
                    stoppedDuringConfig = false
                }
            }
            .onOpenURL(perform: handleDeepLink)
            .alert("Xenomind could not start this mode", isPresented: $isErrorPresented) {
                Button("OK", role: .cancel) { }
            } message: {
                Text(errorMessage)
            }
            .preferredColorScheme(.dark)
        }
    }

    private var hasSelection: Bool {
        !selection.applicationTokens.isEmpty
            || !selection.categoryTokens.isEmpty
            || !selection.webDomainTokens.isEmpty
    }

    private var selectionSummary: String {
        let apps = selection.applicationTokens.count
        let categories = selection.categoryTokens.count
        let sites = selection.webDomainTokens.count
        guard apps + categories + sites > 0 else { return "Nothing selected for this mode yet." }
        return "\(apps) app(s), \(categories) app category(s), and \(sites) website(s) selected."
    }

    private var authorizationDescription: String {
        switch authorizationCenter.authorizationStatus {
        case .approved:
            return "Screen Time permission is enabled on this iPhone."
        case .denied:
            return "Screen Time permission is off. Enable it in iOS Settings before starting a mode."
        case .notDetermined:
            return "iOS will ask for your Screen Time permission before Xenomind can shield selected apps."
        @unknown default:
            return "Screen Time permission status is unavailable."
        }
    }

    private func loadSelection() {
        guard let data = UserDefaults.standard.data(forKey: selectedMode.selectionKey),
              let saved = try? JSONDecoder().decode(FamilyActivitySelection.self, from: data) else {
            selection = FamilyActivitySelection()
            return
        }
        selection = saved
    }

    private func saveSelection(_ value: FamilyActivitySelection, for mode: DeviceMode) {
        guard let encoded = try? JSONEncoder().encode(value) else {
            showError("iOS could not save this mode's app selection.")
            return
        }
        UserDefaults.standard.set(encoded, forKey: mode.selectionKey)
    }

    private func authorizeAndChoose() async {
        do {
            try await requestAuthorizationIfNeeded()
            returnAfterPicker = callbackURL != nil
            isPickerPresented = true
        } catch {
            showError("Screen Time permission was not granted. \(error.localizedDescription)")
        }
    }

    private func authorizeAndStart() async {
        do {
            try await requestAuthorizationIfNeeded()
            if hasSelection {
                apply(selection, for: selectedMode)
                activeMode = selectedMode
                UserDefaults.standard.set(selectedMode.rawValue, forKey: "xenomind.active-mode")
                message = "\(selectedMode.title) mode is active. Apple's Screen Time controls now shield the selected apps and websites."
                pendingActivation = false
                saveActiveCallback()
                completeHandoff(modeAction: "activate")
            } else {
                message = "Select the apps or websites for this mode. It will start after you confirm the selection."
                pendingActivation = true
                isPickerPresented = true
            }
        } catch {
            pendingActivation = false
            callbackURL = nil
            showError("Screen Time permission was not granted. \(error.localizedDescription)")
        }
    }

    private func requestAuthorizationIfNeeded() async throws {
        if authorizationCenter.authorizationStatus != .approved {
            try await authorizationCenter.requestAuthorization(for: .individual)
        }
        guard authorizationCenter.authorizationStatus == .approved else {
            throw NSError(domain: "XenomindModes", code: 1,
                          userInfo: [NSLocalizedDescriptionKey: "iOS did not approve Screen Time access."])
        }
    }

    private func apply(_ value: FamilyActivitySelection, for mode: DeviceMode) {
        for otherMode in DeviceMode.allCases where otherMode != mode {
            ManagedSettingsStore(named: otherMode.storeName).clearAllSettings()
        }
        let store = ManagedSettingsStore(named: mode.storeName)
        store.shield.applications = value.applicationTokens.isEmpty ? nil : value.applicationTokens
        store.shield.applicationCategories = value.categoryTokens.isEmpty
            ? nil : .specific(value.categoryTokens)
        store.shield.webDomains = value.webDomainTokens.isEmpty ? nil : value.webDomainTokens
        store.shield.webDomainCategories = value.categoryTokens.isEmpty
            ? nil : .specific(value.categoryTokens)
    }

    private func endAllModes() {
        for mode in DeviceMode.allCases {
            ManagedSettingsStore(named: mode.storeName).clearAllSettings()
        }
        activeMode = nil
        UserDefaults.standard.removeObject(forKey: "xenomind.active-mode")
        UserDefaults.standard.removeObject(forKey: activeModeCallbackKey)
    }

    private func saveActiveCallback() {
        if let callbackURL {
            UserDefaults.standard.set(callbackURL.absoluteString, forKey: activeModeCallbackKey)
        } else {
            UserDefaults.standard.removeObject(forKey: activeModeCallbackKey)
        }
    }

    private func handleDeepLink(_ url: URL) {
        guard url.scheme == "xenomind", url.host == "run" else { return }
        let components = URLComponents(url: url, resolvingAgainstBaseURL: false)
        let query = components?.queryItems ?? []
        func value(_ name: String) -> String? { query.first(where: { $0.name == name })?.value }
        guard value("module") == "mode" else { return }

        callbackURL = validatedCallback(value("callback"))
        if let key = value("modeKey"), let mode = DeviceMode(rawValue: key) {
            selectedMode = mode
            loadSelection()
        }
        switch value("action") {
        case "activate":
            pendingActivation = true
            Task { await authorizeAndStart() }
        case "stop":
            let stopCallback = callbackURL ?? UserDefaults.standard.string(forKey: activeModeCallbackKey)
                .flatMap(URL.init(string:))
            endAllModes()
            message = "All Xenomind mode shields have been removed."
            completeHandoff(modeAction: "stop", callbackOverride: stopCallback)
        case "settings":
            message = "Choose this mode's blocked apps and websites below."
        default:
            showError("This Xenomind mode request is not supported.")
        }
    }

    private func validatedCallback(_ value: String?) -> URL? {
        guard let value, let url = URL(string: value),
              let scheme = url.scheme?.lowercased(), scheme == "https" || scheme == "http",
              url.host != nil, url.user == nil, url.password == nil else { return nil }
        return url
    }

    private func completeHandoff(modeAction: String? = nil, callbackOverride: URL? = nil) {
        guard let destination = callbackOverride ?? callbackURL,
              var components = URLComponents(url: destination, resolvingAgainstBaseURL: false) else { return }
        var query = components.queryItems ?? []
        query.removeAll { $0.name == "handoff" || $0.name == "modeAction" || $0.name == "id" }
        query.append(URLQueryItem(name: "handoff", value: "success"))
        if let modeAction {
            query.append(URLQueryItem(name: "modeAction", value: modeAction))
        }
        if let id = URLComponents(url: destination, resolvingAgainstBaseURL: false)?
            .queryItems?.first(where: { $0.name == "id" })?.value {
            query.append(URLQueryItem(name: "id", value: id))
        }
        components.queryItems = query
        guard let returnURL = components.url else { return }
        UIApplication.shared.open(returnURL)
        callbackURL = nil
    }

    private func showError(_ detail: String) {
        errorMessage = detail
        isErrorPresented = true
    }
}
