# Set up the iPhone Shortcuts

XENOMIND hands each iPhone action to a Shortcut you create on that phone. This
is required because a web app cannot read or control Reminders, Home, Photos, or
Files by itself. Create the four Shortcuts below, set each to accept **Text**,
and enter the exact shortcut names in XENOMIND's gear menu.

Every request is a JSON dictionary. Start each Shortcut with **Get Dictionary
from Input**. Read the `action` value to choose a branch. `text` and `noteText`
contain the same user-entered text. The request also has `category`,
`actionType`, and `actionLabel`; `dueAt` is optional UTC ISO 8601 text. A Quick
Chain request has a `steps` list instead of one ordinary action.

## Xenomind - Reminder

Read `action`, `text`, and `dueAt` from the dictionary, then add three `If`
branches:

- `create`: make a new Apple Reminder with `text` as its title. If `dueAt` is
  non-empty, convert that ISO 8601 value to a Shortcuts Date and use it as the
  due date. If your iOS version cannot parse it, ask for a due date in the
  Shortcut. If it is empty, create the reminder without a due date.
- `list`: find incomplete reminders and show the results.
- `complete`: find incomplete reminders whose title contains `text`, let the
  user choose the matching reminder, then mark only that reminder complete.

## Xenomind - Library

Read `action` and `text`, then branch on `photos`, `files`, or `organize`.

- `photos`: use **Select Photos** and enable multiple selection if wanted.
- `files`: use **Select File** and enable multiple selection if wanted.
- `organize`: let the user choose photos or files, ask for a destination, and
  save copies there. Keep the originals.

For the selection actions, pass the chosen items to **Share** so iOS shows its
share sheet. Treat `text` as a prompt or folder-name hint; it does not grant
access to any item on its own.

## Xenomind - Home

Read `text` and add an `If` branch for each scene name you want to support. In
each branch, add the corresponding preconfigured Home scene action. The
built-in names are `Arrive Home`, `Deep Focus`, `Evening`, and `All Off`; each
scene must exist in the user's Home setup. Add a confirmation before scenes
that should not run with one tap.

## Xenomind - Chain

Read `steps`, repeat with each dictionary, and branch on its `category` and
`actionType`. Run the actions in order, using each step's `noteText` and
optional `dueAt`. A `set_focus` step is a request to turn on Focus; configure
the Focus action on the phone. The **Deep Work** preset requests the `Deep
Focus` Home scene, Do Not Disturb, and a reminder 25 minutes from now. **End of
Day Sync** requests a user-selected file copy and a `Tomorrow summary`
reminder.

Shortcuts can still display their own permission, confirmation, or picker UI.
The XENOMIND timeline reports whether Shortcuts returned through its callback;
that does not independently prove the requested device action happened.
