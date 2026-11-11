package io.xenomind.bridge;

import android.Manifest;
import android.app.Activity;
import android.app.AlarmManager;
import android.app.AlertDialog;
import android.app.PendingIntent;
import android.content.ActivityNotFoundException;
import android.content.ClipData;
import android.content.Intent;
import android.content.pm.PackageManager;
import android.database.Cursor;
import android.graphics.Color;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.provider.DocumentsContract;
import android.provider.OpenableColumns;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowInsets;
import android.widget.Button;
import android.widget.EditText;
import android.widget.LinearLayout;
import android.widget.ScrollView;
import android.widget.TextView;
import android.widget.Toast;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

import java.io.IOException;
import java.io.InputStream;
import java.io.OutputStream;
import java.time.DateTimeException;
import java.time.Instant;
import java.util.ArrayList;
import java.util.List;
import java.util.Locale;
import java.util.concurrent.ExecutorService;
import java.util.concurrent.Executors;

public final class MainActivity extends Activity {
    private static final String STORE = "xenomind_reminders";
    private static final String TASKS = "tasks";
    private static final int REQUEST_NOTIFICATIONS = 20;
    private static final int REQUEST_PHOTOS = 21;
    private static final int REQUEST_FILES = 22;
    private static final int REQUEST_DESTINATION = 23;
    private static final String MINT = "#78F3D0";
    private static final String BACKGROUND = "#080D14";
    private static final String TEXT = "#EAF7F5";
    private static final String MUTED = "#91A5AD";

    private final ExecutorService fileWorker = Executors.newSingleThreadExecutor();
    private LinearLayout content;
    private String pendingTitle;
    private long pendingDueAt;
    private String libraryAction;
    private String libraryRequest;
    private final ArrayList<Uri> selectedUris = new ArrayList<>();

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().setStatusBarColor(Color.parseColor(BACKGROUND));
        getWindow().setNavigationBarColor(Color.parseColor(BACKGROUND));
        routeIntent(getIntent());
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        routeIntent(intent);
    }

    @Override
    protected void onDestroy() {
        fileWorker.shutdown();
        super.onDestroy();
    }

    private void routeIntent(Intent intent) {
        Uri data = intent == null ? null : intent.getData();
        if (data == null || !"xenomind".equals(data.getScheme()) || !"run".equals(data.getHost())) {
            showHome();
            return;
        }

        String module = data.getQueryParameter("module");
        String action = data.getQueryParameter("action");
        String request = data.getQueryParameter("text");
        if (request != null && request.length() > 500) {
            showError("That request is too long. Shorten it in the cockpit and try again.");
            return;
        }

        if ("reminder".equals(module)) {
            routeReminder(action, request, data.getQueryParameter("dueAt"));
        } else if ("library".equals(module)) {
            routeLibrary(action, request);
        } else if ("home".equals(module)) {
            showHomeKitUnavailable();
        } else {
            showError("This action is not supported by the Android companion.");
        }
    }

    private void routeReminder(String action, String title, String dueAt) {
        if ("create".equals(action)) {
            long dueMillis = 0;
            if (dueAt != null && !dueAt.isEmpty()) {
                try {
                    dueMillis = Instant.parse(dueAt).toEpochMilli();
                    if (dueMillis <= System.currentTimeMillis()) {
                        showError("The due date has passed. Choose a future time in the cockpit.");
                        return;
                    }
                } catch (DateTimeException | ArithmeticException error) {
                    showError("The due date could not be read. Choose it again in the cockpit.");
                    return;
                }
            }
            showReminderForm(title == null ? "" : title, dueMillis);
        } else if ("list".equals(action)) {
            showReminderList("");
        } else if ("complete".equals(action)) {
            showReminderList(title == null ? "" : title);
        } else {
            showError("That reminder action is not supported.");
        }
    }

    private void routeLibrary(String action, String request) {
        if (!"photos".equals(action) && !"files".equals(action) && !"organize".equals(action)) {
            showError("That library action is not supported.");
            return;
        }
        libraryAction = action;
        libraryRequest = request == null ? "" : request;
        openDocumentPicker();
    }

    private void showHome() {
        beginPage("XENOMIND", "ANDROID COMPANION / READY");
        addText("Your phone. Your permissions.", 23, TEXT, true, 0, 0, 8, 0);
        addText(
            "The companion handles device-local reminders and user-selected photos and files. " +
                "It does not upload data or run actions in the background without your approval.",
            14, MUTED, false, 0, 0, 20, 0
        );
        addButton("View my reminders", () -> showReminderList(""));
        addButton("Choose photos", () -> {
            libraryAction = "photos";
            libraryRequest = "";
            openDocumentPicker();
        });
        addButton("Choose files", () -> {
            libraryAction = "files";
            libraryRequest = "";
            openDocumentPicker();
        });
        addText(
            "Apple HomeKit scenes are available only on iPhone in this version. " +
                "Local reminder notifications can be delayed by Android battery and notification settings.",
            12, MUTED, false, 0, 18, 12, 0
        );
    }

    private void showHomeKitUnavailable() {
        beginPage("HOMEKIT / UNAVAILABLE", "PLATFORM LIMIT");
        addText("Apple HomeKit cannot be controlled from this Android app.", 20, TEXT, true, 0, 0, 12, 0);
        addText(
            "Use the Home module on an iPhone with the configured Xenomind - Home Shortcut. " +
                "This companion will not pretend that an Android handoff changed your home.",
            14, MUTED, false, 0, 0, 16, 0
        );
        addButton("Return to Android tasks", this::showHome);
    }

    private void showReminderForm(String initialTitle, long dueAt) {
        beginPage("NEW REMINDER", "SAVED ON THIS ANDROID DEVICE");
        addText("A thought worth keeping.", 22, TEXT, true, 0, 0, 6, 0);
        addText(
            dueAt > 0
                ? "Review the title and due time. Android may deliver the notification later than scheduled."
                : "This creates a local task. Add an optional due time for a notification.",
            13, MUTED, false, 0, 0, 17, 0
        );
        addText("TASK TITLE", 10, MINT, true, 0, 0, 6, 0);
        EditText title = addInput(initialTitle, "What should you remember?");
        title.setSingleLine(true);
        if (dueAt > 0) {
            addText("DUE", 10, MINT, true, 0, 16, 5, 0);
            addText(
                android.text.format.DateFormat.getMediumDateFormat(this).format(dueAt) + "  " +
                    android.text.format.DateFormat.getTimeFormat(this).format(dueAt),
                14, TEXT, false, 0, 0, 17, 0
            );
        } else {
            addText("No due time selected. The task will not create an alert.", 12, MUTED, false, 0, 9, 17, 0);
        }
        addButton("Save local reminder", () -> {
            String value = title.getText().toString().trim();
            if (value.isEmpty()) {
                title.setError("Enter a reminder title");
                return;
            }
            pendingTitle = value;
            pendingDueAt = dueAt;
            saveReminderAfterPermission();
        });
        addButton("Cancel", this::showHome);
    }

    private void saveReminderAfterPermission() {
        if (pendingDueAt <= System.currentTimeMillis()) {
            saveReminder();
            return;
        }
        if (Build.VERSION.SDK_INT >= 33 &&
            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, REQUEST_NOTIFICATIONS);
            return;
        }
        saveReminder();
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode == REQUEST_NOTIFICATIONS) {
            saveReminder();
        }
    }

    private void saveReminder() {
        try {
            JSONArray tasks = loadTasks();
            int id = (int) (System.currentTimeMillis() & 0x7fffffff);
            while (findTask(tasks, id) >= 0) {
                id = id == Integer.MAX_VALUE ? 1 : id + 1;
            }
            JSONObject item = new JSONObject();
            item.put("id", id);
            item.put("title", pendingTitle);
            item.put("dueAt", pendingDueAt);
            item.put("completed", false);
            tasks.put(item);
            writeTasks(tasks);

            if (pendingDueAt > System.currentTimeMillis()) {
                if (Build.VERSION.SDK_INT < 33 ||
                    checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED) {
                    scheduleReminder(id, pendingTitle, pendingDueAt);
                    showMessage("Reminder saved. Android may delay its notification.");
                } else {
                    showMessage("Reminder saved without an alert; notification permission was declined.");
                }
            } else {
                showMessage("Reminder saved on this device. No notification was scheduled.");
            }
            showReminderList("");
        } catch (JSONException | IllegalStateException error) {
            showError("The local reminder could not be saved: " + error.getMessage());
        }
    }

    private void showReminderList(String filter) {
        beginPage("REMINDER VAULT", "LOCAL TO THIS DEVICE");
        addText("Your reminders", 22, TEXT, true, 0, 0, 5, 0);
        addText(
            filter.isEmpty() ? "Select a task to mark it complete." : "Matching tasks for: " + filter,
            13, MUTED, false, 0, 0, 16, 0
        );
        try {
            JSONArray tasks = loadTasks();
            int shown = 0;
            for (int index = tasks.length() - 1; index >= 0; index--) {
                JSONObject task = tasks.getJSONObject(index);
                String title = task.getString("title");
                boolean completed = task.optBoolean("completed", false);
                if (!filter.isEmpty() && !title.toLowerCase(Locale.ROOT).contains(filter.toLowerCase(Locale.ROOT))) {
                    continue;
                }
                shown++;
                LinearLayout row = new LinearLayout(this);
                row.setOrientation(LinearLayout.VERTICAL);
                row.setPadding(dp(13), dp(12), dp(13), dp(12));
                row.setBackgroundColor(Color.rgb(17, 28, 39));
                LinearLayout.LayoutParams rowParams = new LinearLayout.LayoutParams(
                    ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT
                );
                rowParams.bottomMargin = dp(9);
                content.addView(row, rowParams);
                TextView taskTitle = text(title, 15, completed ? MUTED : TEXT, true);
                row.addView(taskTitle);
                long dueAt = task.optLong("dueAt", 0);
                String status = completed ? "Completed"
                    : dueAt > 0 ? "Due " + android.text.format.DateFormat.getMediumDateFormat(this).format(dueAt)
                        + " " + android.text.format.DateFormat.getTimeFormat(this).format(dueAt)
                    : "No due time";
                row.addView(text(status, 11, MUTED, false));
                if (!completed) {
                    int id = task.getInt("id");
                    Button complete = button("Mark complete", () -> completeTask(id));
                    LinearLayout.LayoutParams completeParams = new LinearLayout.LayoutParams(
                        ViewGroup.LayoutParams.WRAP_CONTENT, dp(40)
                    );
                    completeParams.topMargin = dp(8);
                    row.addView(complete, completeParams);
                }
            }
            if (shown == 0) {
                addText(
                    filter.isEmpty() ? "No reminders yet. Create one from the mobile cockpit."
                        : "No matching reminders. Try a shorter title.",
                    14, MUTED, false, 0, 4, 18, 0
                );
            }
            addButton("Back to companion", this::showHome);
        } catch (JSONException error) {
            showError("The local reminder list could not be read: " + error.getMessage());
        }
    }

    private void completeTask(int id) {
        try {
            JSONArray tasks = loadTasks();
            int index = findTask(tasks, id);
            if (index < 0) {
                showError("That reminder no longer exists.");
                return;
            }
            JSONObject task = tasks.getJSONObject(index);
            task.put("completed", true);
            writeTasks(tasks);
            cancelReminder(id);
            showMessage("Reminder completed.");
            showReminderList("");
        } catch (JSONException | IllegalStateException error) {
            showError("The reminder could not be completed: " + error.getMessage());
        }
    }

    private JSONArray loadTasks() throws JSONException {
        String encoded = getSharedPreferences(STORE, MODE_PRIVATE).getString(TASKS, "[]");
        return new JSONArray(encoded);
    }

    private void writeTasks(JSONArray tasks) {
        boolean saved = getSharedPreferences(STORE, MODE_PRIVATE).edit()
            .putString(TASKS, tasks.toString())
            .commit();
        if (!saved) {
            throw new IllegalStateException("Android could not persist the local reminder list.");
        }
    }

    private int findTask(JSONArray tasks, int id) throws JSONException {
        for (int index = 0; index < tasks.length(); index++) {
            if (tasks.getJSONObject(index).getInt("id") == id) return index;
        }
        return -1;
    }

    private void scheduleReminder(int id, String title, long dueAt) {
        AlarmManager alarms = getSystemService(AlarmManager.class);
        if (alarms == null) {
            showError("Android's alarm service is unavailable. The task was saved without a notification.");
            return;
        }
        Intent alarmIntent = new Intent(this, ReminderAlarmReceiver.class)
            .putExtra(ReminderAlarmReceiver.EXTRA_TITLE, title)
            .putExtra(ReminderAlarmReceiver.EXTRA_TASK_ID, id);
        int flags = PendingIntent.FLAG_UPDATE_CURRENT;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) flags |= PendingIntent.FLAG_IMMUTABLE;
        PendingIntent pending = PendingIntent.getBroadcast(this, id, alarmIntent, flags);
        alarms.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, dueAt, pending);
    }

    private void cancelReminder(int id) {
        AlarmManager alarms = getSystemService(AlarmManager.class);
        if (alarms == null) return;
        int flags = PendingIntent.FLAG_NO_CREATE;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) flags |= PendingIntent.FLAG_IMMUTABLE;
        PendingIntent pending = PendingIntent.getBroadcast(
            this, id, new Intent(this, ReminderAlarmReceiver.class), flags
        );
        if (pending != null) {
            alarms.cancel(pending);
            pending.cancel();
        }
    }

    private void openDocumentPicker() {
        Intent picker = new Intent(Intent.ACTION_OPEN_DOCUMENT);
        picker.addCategory(Intent.CATEGORY_OPENABLE);
        picker.setType("photos".equals(libraryAction) ? "image/*" : "*/*");
        picker.putExtra(Intent.EXTRA_ALLOW_MULTIPLE, true);
        picker.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION);
        try {
            startActivityForResult(picker, "organize".equals(libraryAction) ? REQUEST_FILES : REQUEST_PHOTOS);
        } catch (ActivityNotFoundException error) {
            showError("No compatible Android document picker is installed.");
        }
    }

    @Override
    protected void onActivityResult(int requestCode, int resultCode, Intent data) {
        super.onActivityResult(requestCode, resultCode, data);
        if (resultCode != RESULT_OK || data == null) return;
        if (requestCode == REQUEST_PHOTOS || requestCode == REQUEST_FILES) {
            selectedUris.clear();
            if (data.getClipData() != null) {
                ClipData clips = data.getClipData();
                for (int index = 0; index < clips.getItemCount(); index++) {
                    selectedUris.add(clips.getItemAt(index).getUri());
                }
            } else if (data.getData() != null) {
                selectedUris.add(data.getData());
            }
            retainReadPermissions(selectedUris, data.getFlags());
            if (selectedUris.isEmpty()) {
                showMessage("No items were selected.");
            } else if ("organize".equals(libraryAction)) {
                openDestinationPicker();
            } else {
                showSelectedItems();
            }
        } else if (requestCode == REQUEST_DESTINATION && data.getData() != null) {
            Uri tree = data.getData();
            int grantFlags = data.getFlags() &
                (Intent.FLAG_GRANT_READ_URI_PERMISSION | Intent.FLAG_GRANT_WRITE_URI_PERMISSION);
            try {
                getContentResolver().takePersistableUriPermission(tree, grantFlags);
            } catch (SecurityException | IllegalArgumentException error) {
                showError("Android did not grant access to that folder. Choose a folder again.");
                return;
            }
            confirmCopy(tree);
        }
    }

    private void retainReadPermissions(List<Uri> uris, int flags) {
        if ((flags & Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION) == 0) return;
        int readFlag = flags & Intent.FLAG_GRANT_READ_URI_PERMISSION;
        if (readFlag == 0) return;
        for (Uri uri : uris) {
            try {
                getContentResolver().takePersistableUriPermission(uri, readFlag);
            } catch (SecurityException error) {
                showMessage("The picker granted temporary access; choose items again if access expires.");
                return;
            }
        }
    }

    private void showSelectedItems() {
        beginPage("SELECTION / REVIEW", "NOTHING HAS BEEN SHARED");
        addText(libraryRequest.isEmpty() ? "Your selection" : libraryRequest, 18, TEXT, true, 0, 0, 5, 0);
        addText(selectedUris.size() + " item(s) selected. Review the system share sheet before sending.", 13, MUTED, false, 0, 0, 15, 0);
        for (Uri uri : selectedUris) {
            addText(displayName(uri), 12, MUTED, false, 0, 0, 8, 0);
        }
        addButton("Choose another selection", this::openDocumentPicker);
        addButton("Open share sheet", this::shareSelection);
        addButton("Cancel", this::showHome);
    }

    private void shareSelection() {
        if (selectedUris.isEmpty()) {
            showError("Select at least one item first.");
            return;
        }
        Intent share = new Intent(Intent.ACTION_SEND_MULTIPLE);
        share.setType("organize".equals(libraryAction) ? "*/*"
            : "photos".equals(libraryAction) ? "image/*" : "*/*");
        share.putParcelableArrayListExtra(Intent.EXTRA_STREAM, new ArrayList<>(selectedUris));
        share.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION);
        ClipData clip = ClipData.newUri(getContentResolver(), "Xenomind selection", selectedUris.get(0));
        for (int index = 1; index < selectedUris.size(); index++) {
            clip.addItem(new ClipData.Item(selectedUris.get(index)));
        }
        share.setClipData(clip);
        try {
            startActivity(Intent.createChooser(share, "Share selected items"));
        } catch (ActivityNotFoundException error) {
            showError("No Android app can receive this selection.");
        }
    }

    private void openDestinationPicker() {
        Intent picker = new Intent(Intent.ACTION_OPEN_DOCUMENT_TREE);
        picker.addFlags(Intent.FLAG_GRANT_READ_URI_PERMISSION |
            Intent.FLAG_GRANT_WRITE_URI_PERMISSION |
            Intent.FLAG_GRANT_PERSISTABLE_URI_PERMISSION);
        try {
            startActivityForResult(picker, REQUEST_DESTINATION);
        } catch (ActivityNotFoundException error) {
            showError("No compatible Android folder picker is installed.");
        }
    }

    private void confirmCopy(Uri tree) {
        new AlertDialog.Builder(this)
            .setTitle("Copy selected files?")
            .setMessage(selectedUris.size() + " item(s) will be copied into the folder you chose. Originals are kept.")
            .setNegativeButton("Cancel", (dialog, which) -> showHome())
            .setPositiveButton("Copy files", (dialog, which) -> copySelectedFiles(tree))
            .show();
    }

    private void copySelectedFiles(Uri tree) {
        final ArrayList<Uri> sources = new ArrayList<>(selectedUris);
        fileWorker.execute(() -> {
            int copied = 0;
            String errorMessage = null;
            for (Uri source : sources) {
                try {
                    copyDocument(tree, source, copied + 1);
                    copied++;
                } catch (IOException | SecurityException | IllegalArgumentException error) {
                    errorMessage = error.getMessage();
                    break;
                }
            }
            final int count = copied;
            final String failure = errorMessage;
            runOnUiThread(() -> {
                if (failure != null) {
                    showError(count + " file(s) copied before an error: " + failure);
                } else {
                    showMessage(count + " file(s) copied. Originals were kept.");
                    showHome();
                }
            });
        });
    }

    private void copyDocument(Uri tree, Uri source, int ordinal) throws IOException {
        String documentId = DocumentsContract.getTreeDocumentId(tree);
        Uri parent = DocumentsContract.buildDocumentUriUsingTree(tree, documentId);
        String name = displayName(source).replace("/", "_").replace("\\", "_");
        String mime = getContentResolver().getType(source);
        if (mime == null) mime = "application/octet-stream";
        String destinationName = "Xenomind-" + System.currentTimeMillis() + "-" + ordinal + "-" + name;
        Uri destination = DocumentsContract.createDocument(getContentResolver(), parent, mime, destinationName);
        if (destination == null) throw new IOException("The selected storage provider could not create a destination file.");

        try {
            try (InputStream input = getContentResolver().openInputStream(source);
                 OutputStream output = getContentResolver().openOutputStream(destination, "w")) {
                if (input == null || output == null) {
                    throw new IOException("The storage provider could not open a selected file.");
                }
                byte[] buffer = new byte[16 * 1024];
                int read;
                while ((read = input.read(buffer)) != -1) output.write(buffer, 0, read);
                output.flush();
            }
        } catch (IOException error) {
            try {
                DocumentsContract.deleteDocument(getContentResolver(), destination);
            } catch (IOException cleanupError) {
                error.addSuppressed(cleanupError);
            }
            throw error;
        }
    }

    private String displayName(Uri uri) {
        try (Cursor cursor = getContentResolver().query(
            uri, new String[]{OpenableColumns.DISPLAY_NAME}, null, null, null
        )) {
            if (cursor != null && cursor.moveToFirst()) {
                int column = cursor.getColumnIndex(OpenableColumns.DISPLAY_NAME);
                if (column >= 0) return cursor.getString(column);
            }
        }
        return "Selected item";
    }

    private void beginPage(String title, String eyebrow) {
        ScrollView scroll = new ScrollView(this);
        scroll.setFillViewport(true);
        scroll.setBackgroundColor(Color.parseColor(BACKGROUND));
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.R) {
            getWindow().setDecorFitsSystemWindows(false);
            scroll.setOnApplyWindowInsetsListener((view, insets) -> {
                android.graphics.Insets bars = insets.getInsets(
                    WindowInsets.Type.systemBars() | WindowInsets.Type.displayCutout()
                );
                view.setPadding(bars.left, bars.top, bars.right, bars.bottom);
                return insets;
            });
        }
        content = new LinearLayout(this);
        content.setOrientation(LinearLayout.VERTICAL);
        content.setPadding(dp(22), dp(27), dp(22), dp(30));
        scroll.addView(content, new ScrollView.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT
        ));
        setContentView(scroll);
        scroll.requestApplyInsets();
        addText("X E N O M I N D", 11, MINT, true, 0, 0, 6, 0);
        addText(eyebrow, 9, MUTED, true, 0, 0, 22, 0);
        addText(title, 15, TEXT, true, 0, 0, 17, 0);
    }

    private void addText(String value, int sizeSp, String color, boolean bold,
                         int left, int top, int right, int bottom) {
        TextView view = text(value, sizeSp, color, bold);
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT
        );
        params.setMargins(dp(left), dp(top), dp(right), dp(bottom));
        content.addView(view, params);
    }

    private TextView text(String value, int sizeSp, String color, boolean bold) {
        TextView view = new TextView(this);
        view.setText(value);
        view.setTextSize(sizeSp);
        view.setTextColor(Color.parseColor(color));
        if (bold) view.setTypeface(null, android.graphics.Typeface.BOLD);
        return view;
    }

    private EditText addInput(String value, String hint) {
        EditText input = new EditText(this);
        input.setText(value);
        input.setHint(hint);
        input.setTextColor(Color.parseColor(TEXT));
        input.setHintTextColor(Color.parseColor(MUTED));
        input.setSingleLine(false);
        input.setPadding(dp(13), dp(10), dp(13), dp(10));
        input.setBackgroundTintList(android.content.res.ColorStateList.valueOf(Color.parseColor(MINT)));
        content.addView(input, new LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT
        ));
        return input;
    }

    private void addButton(String label, Runnable action) {
        Button button = button(label, action);
        LinearLayout.LayoutParams params = new LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, dp(50)
        );
        params.topMargin = dp(9);
        content.addView(button, params);
    }

    private Button button(String label, Runnable action) {
        Button button = new Button(this);
        button.setText(label);
        button.setTextColor(Color.parseColor(MINT));
        button.setAllCaps(false);
        button.setGravity(Gravity.CENTER);
        button.setOnClickListener(view -> action.run());
        return button;
    }

    private void showMessage(String message) {
        Toast.makeText(this, message, Toast.LENGTH_LONG).show();
    }

    private void showError(String message) {
        new AlertDialog.Builder(this)
            .setTitle("Xenomind could not continue")
            .setMessage(message)
            .setPositiveButton("OK", (dialog, which) -> dialog.dismiss())
            .show();
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }
}
