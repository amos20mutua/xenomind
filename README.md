# XENOMIND — Cross-platform Personal Systems

A responsive phone cockpit hands tasks to iOS Shortcuts on Apple devices and to
the native Android companion on Android. Apple HomeKit is intentionally
iPhone-only; Android controls local reminders and user-selected files.

The cockpit is also an installable PWA. Its manifest, offline shell, neural
app icon, safe-area layout, Safari install tip, voice input, local handoff
timeline, and optional x-callback-url return are served with the app.

## Start the phone cockpit

1. Connect the Windows PC and phone to the same trusted Wi-Fi.
2. In PowerShell, from this project folder, start the static cockpit server:

   ```powershell
   .\.venv\Scripts\python.exe .\run_iphone_cockpit.py
   ```

3. Open the printed `http://...` address in Safari or Chrome on the phone.
   Keep the PowerShell window open while using the cockpit. This local HTTP
   preview supports handoffs, but iOS only enables Service Workers in a secure
   context. For offline PWA launches, host the files over HTTPS (or test at
   `localhost` on the same device).
4. On iPhone, create the Shortcuts below. On Android, build and install the
   companion app from Android Studio.
5. Tap an action and review it in the device handoff. Stop the local server
   with **Ctrl+C** when finished.

The server binds to local network interfaces and serves only the cockpit page
and its four PWA assets, not other project files. Use it only on a trusted
private network; do not port-forward it or expose it to the public internet. If
Windows Firewall asks, allow access on private networks only.

## Install on iPhone

Open the HTTPS app URL in Safari, tap **Share**, then **Add to Home Screen**.
The cockpit launches in standalone mode; iOS still controls Shortcuts, Home,
microphone, and file permissions. Voice recognition is supplied by the
browser/OS and may use online speech services, so do not speak sensitive
information. If speech recognition is unavailable, enter the intent manually.
The cockpit uses one shared intent field across systems; saying an intent
selects the likely system and fills the field. Review it and tap the action
button to hand it to iOS. This visible tap is intentional: a web page cannot
reliably launch phone apps from background speech callbacks.

## iPhone setup

Create the four Shortcuts below on the iPhone and allow each to receive **Text**
input. Use **Get Dictionary from Input** to parse the JSON. Standard requests
include `category`, `actionType`, and `noteText`, plus `module`/`action`/`text`
compatibility keys and optional `dueAt` or macro `steps`.

- **Xenomind - Reminder** — use **Get Dictionary from Input**, branch by
  `action`: create an Apple Reminder (using `text` and optional `dueAt`), show
  incomplete reminders for `list`, or find and let the user confirm a match
  before completing it.
- **Xenomind - Library** — branch by `action` (`photos`, `files`, `organize`).
  Use the appropriate iOS picker; show a confirmation before sharing or
  changing anything. Configure `organize` as a copy unless you explicitly
  choose otherwise.
- **Xenomind - Home** — match the requested scene in your Home setup, confirm
  if appropriate, then use the Home action. HomeKit is only offered on iOS.
- **Xenomind - Chain** — branch on `actionType` and process each object in
  `steps` in order. The **Deep Work** chain requests a Home scene, Do Not
  Disturb Focus, and a reminder due in 25 minutes. **End of Day Sync** requests
  a photo/file copy and a “Tomorrow summary” reminder. Build those actions
  yourself in Shortcuts and preserve its user prompts and permissions; the web
  app sends one macro request but cannot create or authorize the actions.

Set the exact names in the cockpit's gear dialog. The iOS dispatcher uses
`shortcuts://x-callback-url/run-shortcut` and returns to the current app URL
with a one-time handoff ID. A **Confirmed** timeline state means the callback
returned; it does not independently verify every device action. The last five
requests and their payloads are stored only in this browser's local storage.
Replay launches a new callback-tracked instance of the same request.

## Android companion

The Android source is in [android](./android). Open that folder in Android
Studio with JDK 17+ and Android SDK Platform 35, sync Gradle, then run/install
the `app` on your phone. The app registers the `xenomind://run` handoff used by
the cockpit.

- Reminders are stored locally in the companion app, not synced to Apple
  Reminders or Google Tasks. Optional notifications require OS permission and
  use inexact Android alarms; battery settings can delay them.
- Photos and files are selected with Android's system picker. Share opens the
  Android share sheet. Organize copies selected files to a folder you choose
  and keeps the originals.
- HomeKit controls are disabled on Android. There is no direct Android
  HomeKit control path in this build.

**Android implementation status: source scaffold only, not built or device
tested.** This workspace has no Java, Gradle, Android SDK, emulator, or Android
device. Do not treat Android task actions as verified until the app builds and
the permission, notification, picker, copy, and share flows are tested on your
target phone.

## Desktop neural interface

## Desktop neural interface requirements and run

- Python 3.10 or newer
- Tkinter (included with the standard Windows Python distribution)

From PowerShell in this folder, run:

```powershell
.\.venv\Scripts\python.exe .\activity_simulator.py
```

Or, if Python is on your `PATH`, run `py -3 .\activity_simulator.py`.
No third-party packages are required. If Tkinter is missing, rerun the
standard Windows Python installer and enable **tcl/tk and IDLE**.

Choose **First Contact**, **Dream Sequence**, or **Signal Migration**, then
select **Awaken the core**. Use **Suspend** to pause or **Dissolve** to end a
cycle early. JSONL records are appended to the selected file.

## Interface

- Animated, two-hemisphere neural lattice with firing nodes, synaptic links,
  orbital markers, and live signal intensity.
- Live telemetry for core state, protocol, uptime, impulse count, and the latest
  transmission.
- Configurable protocol, cycle duration, pulse interval, replay signature, and
  optional quiet intervals.
- Append-only JSONL traces with `synthetic: true`,
  `scope: "in_app_sandbox"`, and `real_input_sent: false`.

The neural organism and its pulses are generative visual art, not an AI or
biological brain. The desktop visualization sends no OS-level input, does not
control external applications, and performs no network or user-activity
monitoring. Output records are written only to the selected local path.

Run all tests with:

```powershell
.\.venv\Scripts\python.exe -m unittest -v
```

At shorter window heights, the scenario settings panel scrolls independently
while the run controls stay visible.
