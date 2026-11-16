# Set up iPhone Shortcuts and app modes

XENOMIND uses three iPhone Shortcuts for Reminders, Photos & Files, and Quick
Chains. Create them on the iPhone, set each to accept **Text**, and enter the
same names in the cockpit's gear menu. Device app blocking is handled by the
separate native Xenomind Modes app in `ios/XenomindModes.xcodeproj`; it does not
use a Shortcut or HomeKit.

Every Shortcut receives a JSON dictionary. Start it with **Get Dictionary from
Input**. Read `action` for a single Reminder or Library request. The request
also has `category`, `actionType`, and `actionLabel`; `text` and `noteText`
contain the user-entered text. `dueAt` is optional UTC ISO 8601 text. A Quick
Chain request has a `steps` list instead of one ordinary action.

## Xenomind - Reminder

Read `action`, `text`, and `dueAt` from the dictionary, then add three `If`
branches:

- `create`: make a new Apple Reminder with `text` as its title. If `dueAt` is
  non-empty, convert it to a Shortcuts Date and use it as the due date. If your
  iOS version cannot parse it, ask for a due date in the Shortcut. If empty,
  create the reminder without a due date.
- `list`: find incomplete reminders and show the results.
- `complete`: find incomplete reminders whose title contains `text`, let the
  user choose a match, then mark only that reminder complete.

## Xenomind - Library

Read `action` and `text`, then branch on `photos`, `files`, or `organize`.

- `photos`: use **Select Photos** and enable multiple selection if wanted.
- `files`: use **Select File** and enable multiple selection if wanted.
- `organize`: let the user choose photos or files, ask for a destination, and
  save copies there. Keep the originals.

For selection actions, pass the chosen items to **Share** so iOS shows its
share sheet. Treat `text` as a prompt or folder-name hint; it does not grant
access to any item on its own.

## Xenomind - Chain

Read `steps`, repeat with each dictionary, and branch on `category` and
`actionType`. Run the actions in order, using each step's `noteText` and
optional `dueAt`. The **Deep Work** preset asks the Shortcut to enable Do Not
Disturb Focus and create a reminder due in 25 minutes. **End of Day Sync** asks
for a user-selected file copy and a `Tomorrow summary` reminder.

Shortcuts can still display their own permission, confirmation, or picker UI.
The XENOMIND timeline reports whether Shortcuts returned through its callback;
that does not independently prove each requested device action happened.

## Install native app modes

Open `ios/XenomindModes.xcodeproj` on a Mac in Xcode, set your Apple developer
team, then build and install **Xenomind Modes** on the iPhone. The app registers
the `xenomind://run` link used by the cockpit. In the app, choose Focus,
Rehearsal, or Rest, select apps, categories, or websites with Apple's system
picker, then start the mode. The selected items are shielded by Apple's Screen
Time controls until you end the active mode. The selections remain private to
the device as Apple-provided tokens.

iOS asks the device owner to authorize Screen Time access. Before distributing
the app, the Apple Developer Account Holder must request the Family Controls
entitlement for the app and receive Apple's approval. See [Apple's Family
Controls entitlement instructions](https://developer.apple.com/documentation/FamilyControls/requesting-the-family-controls-entitlement).
This project cannot be built or signed from Windows; finish signing and test
the picker, app shields, deep links, and callbacks on an iPhone before release.
