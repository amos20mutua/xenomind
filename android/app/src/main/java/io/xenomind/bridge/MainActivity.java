package io.xenomind.bridge;

import android.Manifest;
import android.app.Activity;
import android.app.AlarmManager;
import android.app.AlertDialog;
import android.app.DatePickerDialog;
import android.app.PendingIntent;
import android.app.TimePickerDialog;
import android.content.ActivityNotFoundException;
import android.content.ClipData;
import android.content.Intent;
import android.content.pm.ResolveInfo;
import android.content.pm.PackageManager;
import android.database.Cursor;
import android.graphics.Color;
import android.net.Uri;
import android.os.Build;
import android.os.Bundle;
import android.provider.DocumentsContract;
import android.provider.OpenableColumns;
import android.provider.Settings;
import android.view.Gravity;
import android.view.View;
import android.view.ViewGroup;
import android.view.WindowInsets;
import android.widget.Button;
import android.widget.CheckBox;
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
import java.util.Calendar;
import java.util.Collections;
import java.util.Comparator;
import java.util.HashSet;
import java.util.List;
import java.util.Locale;
import java.util.Set;
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
    private String handoffReturnUrl;
    private String handoffModule;
    private String handoffAction;
    private String libraryAction;
    private String libraryRequest;
    private boolean refreshAlarmsOnResume;
    private boolean refreshRemindersOnResume;
    private boolean pendingReminderSave;
    private boolean activateAfterModeSave;
    private String pendingModeKey = "";
    private final ArrayList<Uri> selectedUris = new ArrayList<>();

    @Override
    protected void onCreate(Bundle state) {
        super.onCreate(state);
        getWindow().setStatusBarColor(Color.parseColor(BACKGROUND));
        getWindow().setNavigationBarColor(Color.parseColor(BACKGROUND));
        routeIntent(getIntent());
        ReminderBootReceiver.reschedule(this);
    }

    @Override
    protected void onNewIntent(Intent intent) {
        super.onNewIntent(intent);
        setIntent(intent);
        routeIntent(intent);
        ReminderBootReceiver.reschedule(this);
    }

    @Override
    protected void onResume() {
        super.onResume();
        if (refreshAlarmsOnResume) {
            refreshAlarmsOnResume = false;
            ReminderBootReceiver.reschedule(this);
            showReminderList("");
        }
        if (refreshRemindersOnResume) {
            refreshRemindersOnResume = false;
            ReminderBootReceiver.reschedule(this);
            showReminderList("");
        }
        if (!pendingModeKey.isEmpty() && FocusModes.blockerEnabled(this)) {
            String modeKey = pendingModeKey;
            pendingModeKey = "";
            activateMode(modeKey);
        }
    }

    @Override
    protected void onDestroy() {
        fileWorker.shutdown();
        super.onDestroy();
    }

    private void routeIntent(Intent intent) {
        handoffReturnUrl = null;
        handoffModule = null;
        handoffAction = null;
        Uri data = intent == null ? null : intent.getData();
        if (data == null || !"xenomind".equals(data.getScheme()) || !"run".equals(data.getHost())) {
            pendingModeKey = "";
            showHome();
            return;
        }

        String module = data.getQueryParameter("module");
        String action = data.getQueryParameter("action");
        handoffModule = module;
        handoffAction = action;
        String request = data.getQueryParameter("text");
        handoffReturnUrl = validatedReturnUrl(data.getQueryParameter("callback"));
        if (request != null && request.length() > 500) {
            showError("That request is too long. Shorten it in the cockpit and try again.");
            return;
        }

        if ("reminder".equals(module)) {
            routeReminder(action, request, data.getQueryParameter("dueAt"));
        } else if ("library".equals(module)) {
            routeLibrary(action, request);
        } else if ("home".equals(module)) {
            showModeHub();
        } else if ("mode".equals(module)) {
            routeMode(action, data.getQueryParameter("modeKey"));
        } else {
            showError("This action is not supported by the Android companion.");
        }
    }

    private void routeMode(String action, String modeKey) {
        pendingModeKey = "";
        activateAfterModeSave = false;
        if ("settings".equals(action)) {
            showModeSettings(FocusModes.isValid(modeKey) ? modeKey : "focus");
        } else if ("activate".equals(action)) {
            if (!FocusModes.isValid(modeKey)) {
                showError("Choose Focus, Rehearsal, or Rest in the cockpit, then try again.");
                return;
            }
            requestModeActivation(modeKey);
        } else if ("stop".equals(action)) {
            pendingModeKey = "";
            if (!FocusModes.clearActive(this)) {
                showError("Android could not end the active mode. Try again.");
                return;
            }
            getSharedPreferences(FocusModes.STORE, MODE_PRIVATE).edit()
                .remove(FocusModes.ACTIVE_CALLBACK).commit();
            handoffModule = "mode";
            handoffAction = "stop";
            showHome("success");
            returnToCockpit("success");
        } else {
            showError("That device mode action is not supported.");
        }
    }

    private void activateMode(String modeKey) {
        if (!FocusModes.isValid(modeKey) || FocusModes.blockedApps(this, modeKey).isEmpty()) {
            showModeSettings(FocusModes.isValid(modeKey) ? modeKey : "focus");
            showMessage("Choose at least one app before starting this mode.");
            return;
        }
        if (!FocusModes.blockerEnabled(this)) {
            showAccessibilitySetup(modeKey);
            return;
        }
        if (!FocusModes.setActive(this, modeKey)) {
            showError("Android could not save the active mode on this device.");
            return;
        }
        getSharedPreferences(FocusModes.STORE, MODE_PRIVATE).edit()
            .putString(FocusModes.ACTIVE_CALLBACK, handoffReturnUrl == null ? "" : handoffReturnUrl)
            .commit();
        handoffModule = "mode";
        handoffAction = "activate";
        showHome("success");
        showMessage(FocusModes.label(modeKey) + " mode is active. Selected apps will be covered when opened.");
        returnToCockpit("success");
    }

    private void requestModeActivation(String modeKey) {
        if (FocusModes.blockedApps(this, modeKey).isEmpty()) {
            activateAfterModeSave = true;
            showModeSettings(modeKey);
            showMessage("Choose at least one app before starting this mode.");
        } else if (!FocusModes.blockerEnabled(this)) {
            showAccessibilitySetup(modeKey);
        } else {
            activateMode(modeKey);
        }
    }

    private void showModeHub() {
        beginPage("DEVICE MODES", "APPS BLOCKED ON THIS PHONE");
        addText("Choose a separate blocked-app list for each mode.", 14, MUTED, false, 0, 0, 14, 0);
        for (String key : FocusModes.KEYS) {
            Set<String> apps = FocusModes.blockedApps(this, key);
            String state = key.equals(FocusModes.activeMode(this)) ? "Active now"
                : apps.isEmpty() ? "No apps selected" : apps.size() + " app(s) selected";
            addText(FocusModes.label(key) + " / " + state, 17, TEXT, true, 0, 12, 0, 0);
            addButton("Choose apps for " + FocusModes.label(key), () -> showModeSettings(key));
            if (!apps.isEmpty()) {
                addButton("Start " + FocusModes.label(key) + " mode", () -> requestModeActivation(key));
            }
            if (key.equals(FocusModes.activeMode(this))) {
                addButton("End " + FocusModes.label(key) + " mode", () -> {
                    if (!FocusModes.clearActive(this)) {
                        showError("Android could not end the active mode. Try again.");
                        return;
                    }
                    getSharedPreferences(FocusModes.STORE, MODE_PRIVATE).edit()
                        .remove(FocusModes.ACTIVE_CALLBACK).commit();
                    handoffModule = "mode";
                    handoffAction = "stop";
                    showModeHub();
                    returnToCockpit("success");
                });
            }
        }
        if (!FocusModes.blockerEnabled(this)) {
            addText("App blocking is off. Android asks you to enable the Xenomind focus service in Accessibility before a mode can start.",
                12, MUTED, false, 0, 16, 0, 0);
        }
        addButton("Back to companion", () -> showHome("cancel"));
        addReturnButton("cancel");
    }

    private void showAccessibilitySetup(String modeKey) {
        pendingModeKey = modeKey;
        beginPage("ALLOW APP BLOCKING", "ANDROID ACCESSIBILITY SETTING");
        addText("Android requires you to enable Xenomind’s focus service before it can block selected apps.",
            19, TEXT, true, 0, 0, 12, 0);
        addText("The service checks only which app is currently open. It does not read screen text, collect usage history, or send data anywhere. Enable “Xenomind focus mode” in Accessibility, then return here; " +
            FocusModes.label(modeKey) + " will start automatically.", 14, MUTED, false, 0, 0, 18, 0);
        addButton("Open Accessibility settings", () -> {
            try {
                startActivity(new Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS));
            } catch (ActivityNotFoundException error) {
                showError("Open Android Settings, then Accessibility, and enable Xenomind focus mode.");
            }
        });
        addButton("Choose blocked apps", () -> showModeSettings(modeKey));
        addButton("Cancel", () -> {
            pendingModeKey = "";
            activateAfterModeSave = false;
            showHome("cancel");
        });
        addReturnButton("cancel");
    }

    private void showModeSettings(String modeKey) {
        String validKey = FocusModes.isValid(modeKey) ? modeKey : "focus";
        beginPage(FocusModes.label(validKey).toUpperCase(Locale.ROOT) + " MODE", "CHOOSE APPS TO BLOCK");
        addText("Select the apps this mode should pause. Android’s system and Xenomind settings remain available so you can end the mode.",
            14, MUTED, false, 0, 0, 14, 0);

        Set<String> savedPackages = FocusModes.blockedApps(this, validKey);
        Set<String> selectedPackages = new HashSet<>();
        LinearLayout choices = new LinearLayout(this);
        choices.setOrientation(LinearLayout.VERTICAL);
        choices.setPadding(dp(12), dp(8), dp(12), dp(8));
        choices.setBackgroundColor(Color.rgb(17, 28, 39));
        content.addView(choices, new LinearLayout.LayoutParams(
            ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));

        Intent launcherIntent = new Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_LAUNCHER);
        List<ResolveInfo> apps = getPackageManager().queryIntentActivities(launcherIntent, 0);
        Collections.sort(apps, Comparator.comparing(
            item -> String.valueOf(item.loadLabel(getPackageManager())).toLowerCase(Locale.ROOT)));
        Intent homeIntent = new Intent(Intent.ACTION_MAIN).addCategory(Intent.CATEGORY_HOME);
        Set<String> homePackages = new HashSet<>();
        for (ResolveInfo homeApp : getPackageManager().queryIntentActivities(homeIntent, 0)) {
            if (homeApp.activityInfo != null) homePackages.add(homeApp.activityInfo.packageName);
        }
        int appCount = 0;
        Set<String> seen = new HashSet<>();
        for (ResolveInfo app : apps) {
            String packageName = app.activityInfo == null ? "" : app.activityInfo.packageName;
            if (packageName.isEmpty() || packageName.equals(getPackageName())
                || packageName.equals("com.android.settings") || homePackages.contains(packageName)
                || !seen.add(packageName)) continue;
            appCount++;
            if (savedPackages.contains(packageName)) selectedPackages.add(packageName);
            CheckBox checkBox = new CheckBox(this);
            checkBox.setText(app.loadLabel(getPackageManager()));
            checkBox.setTextColor(Color.parseColor(TEXT));
            checkBox.setButtonTintList(android.content.res.ColorStateList.valueOf(Color.parseColor(MINT)));
            checkBox.setChecked(selectedPackages.contains(packageName));
            checkBox.setTag(packageName);
            checkBox.setPadding(dp(5), dp(5), dp(5), dp(5));
            checkBox.setOnCheckedChangeListener((button, checked) -> {
                String selectedPackage = (String) button.getTag();
                if (checked) selectedPackages.add(selectedPackage);
                else selectedPackages.remove(selectedPackage);
            });
            choices.addView(checkBox, new LinearLayout.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT));
        }
        if (appCount == 0) {
            addText("Android did not return any launchable apps. Check that the app list is available on this phone.",
                13, MUTED, false, 0, 12, 0, 0);
        }
        addButton("Save blocked apps", () -> {
            if (!FocusModes.saveBlockedApps(this, validKey, selectedPackages)) {
                showError("Android could not save this mode’s app list.");
                return;
            }
            if (validKey.equals(FocusModes.activeMode(this))) {
                if (selectedPackages.isEmpty()) {
                    FocusModes.clearActive(this);
                    getSharedPreferences(FocusModes.STORE, MODE_PRIVATE).edit()
                        .remove(FocusModes.ACTIVE_CALLBACK).commit();
                    handoffModule = "mode";
                    handoffAction = "stop";
                }
                else if (FocusModes.blockerEnabled(this)) {
                    FocusModes.clearActive(this);
                    FocusModes.setActive(this, validKey);
                }
            }
            if (activateAfterModeSave) {
                activateAfterModeSave = false;
                if (selectedPackages.isEmpty()) {
                    showMessage("Choose at least one app before starting this mode.");
                    showModeSettings(validKey);
                } else if (FocusModes.blockerEnabled(this)) {
                    activateMode(validKey);
                } else {
                    showAccessibilitySetup(validKey);
                }
                return;
            }
            pendingModeKey = "";
            showHome("success");
            showMessage(selectedPackages.size() + " app(s) saved for " + FocusModes.label(validKey) + " mode.");
            if (handoffReturnUrl != null) returnToCockpit("success");
        });
        addButton("Enable app blocking", () -> {
            pendingModeKey = validKey;
            if (selectedPackages.isEmpty()) {
                showMessage("Save at least one blocked app first.");
                return;
            }
            if (!selectedPackages.equals(savedPackages)) {
                if (!FocusModes.saveBlockedApps(this, validKey, selectedPackages)) {
                    showError("Android could not save this mode’s app list.");
                    return;
                }
            }
            if (FocusModes.blockerEnabled(this)) activateMode(validKey);
            else showAccessibilitySetup(validKey);
        });
        addButton("Back to modes", () -> {
            pendingModeKey = "";
            activateAfterModeSave = false;
            showModeHub();
        });
        addReturnButton("cancel");
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
        showHome("success");
    }

    private void showHome(String returnOutcome) {
        beginPage("XENOMIND", "ANDROID COMPANION / READY");
        addText("Your phone. Your permissions.", 23, TEXT, true, 0, 0, 8, 0);
        addText(
            "The companion handles device-local reminders and user-selected photos and files. " +
                "It does not upload data or run actions in the background without your approval.",
            14, MUTED, false, 0, 0, 20, 0
        );
        addButton("Create a reminder", () -> showReminderForm("", 0));
        addButton("View my reminders", () -> showReminderList(""));
        addButton("Configure device modes", this::showModeHub);
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
            "Modes use Android Accessibility to cover only apps you choose. Reminder alerts need notification permission; Android battery settings can delay them.",
            12, MUTED, false, 0, 18, 12, 0
        );
        addReturnButton(returnOutcome);
    }

    private void showReminderForm(String initialTitle, long dueAt) {
        beginPage("NEW REMINDER", "SAVED ON THIS ANDROID DEVICE");
        addText("A thought worth keeping.", 22, TEXT, true, 0, 0, 6, 0);
        addText("This creates a local task. Add an optional due time for a notification.",
            13, MUTED, false, 0, 0, 17, 0);
        addText("TASK TITLE", 10, MINT, true, 0, 0, 6, 0);
        EditText title = addInput(initialTitle, "What should you remember?");
        title.setSingleLine(true);
        long[] dueAtValue = {dueAt};
        TextView dueSummary = text("", 12, MUTED, false);
        content.addView(dueSummary);
        updateDueSummary(dueSummary, dueAtValue[0]);
        addButton("Choose date and time", () -> chooseReminderDueTime(dueAtValue, dueSummary));
        addButton("Clear due time", () -> {
            dueAtValue[0] = 0;
            updateDueSummary(dueSummary, 0);
        });
        addButton("Save local reminder", () -> {
            String value = title.getText().toString().trim();
            if (value.isEmpty()) {
                title.setError("Enter a reminder title");
                return;
            }
            if (value.length() > 180) {
                title.setError("Use 180 characters or fewer");
                return;
            }
            if (dueAtValue[0] > 0 && dueAtValue[0] <= System.currentTimeMillis()) {
                showError("Choose a future due time or clear the due time.");
                return;
            }
            pendingTitle = value;
            pendingDueAt = dueAtValue[0];
            saveReminderAfterPermission();
        });
        addButton("Cancel", () -> showHome("cancel"));
    }

    private void chooseReminderDueTime(long[] dueAtValue, TextView dueSummary) {
        Calendar initial = Calendar.getInstance();
        if (dueAtValue[0] > 0) initial.setTimeInMillis(dueAtValue[0]);
        DatePickerDialog datePicker = new DatePickerDialog(this, (picker, year, month, day) -> {
            Calendar chosen = Calendar.getInstance();
            chosen.set(year, month, day);
            new TimePickerDialog(this, (timePicker, hour, minute) -> {
                chosen.set(Calendar.HOUR_OF_DAY, hour);
                chosen.set(Calendar.MINUTE, minute);
                chosen.set(Calendar.SECOND, 0);
                chosen.set(Calendar.MILLISECOND, 0);
                dueAtValue[0] = chosen.getTimeInMillis();
                updateDueSummary(dueSummary, dueAtValue[0]);
            }, initial.get(Calendar.HOUR_OF_DAY), initial.get(Calendar.MINUTE),
                android.text.format.DateFormat.is24HourFormat(this)).show();
        }, initial.get(Calendar.YEAR), initial.get(Calendar.MONTH), initial.get(Calendar.DAY_OF_MONTH));
        datePicker.getDatePicker().setMinDate(System.currentTimeMillis());
        datePicker.show();
    }

    private void updateDueSummary(TextView dueSummary, long dueAt) {
        if (dueAt <= 0) {
            dueSummary.setText("No due time selected. The task will not create an alert.");
        } else {
            dueSummary.setText("Due " + android.text.format.DateFormat.getMediumDateFormat(this).format(dueAt)
                + "  " + android.text.format.DateFormat.getTimeFormat(this).format(dueAt)
                + ". Android may deliver the notification later.");
        }
    }

    private void saveReminderAfterPermission() {
        if (pendingDueAt <= System.currentTimeMillis()) {
            saveReminder();
            return;
        }
        if (Build.VERSION.SDK_INT >= 33 &&
            checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
            pendingReminderSave = true;
            requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS}, REQUEST_NOTIFICATIONS);
            return;
        }
        saveReminder();
    }

    @Override
    public void onRequestPermissionsResult(int requestCode, String[] permissions, int[] grantResults) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults);
        if (requestCode == REQUEST_NOTIFICATIONS) {
            ReminderBootReceiver.reschedule(this);
            if (pendingReminderSave) {
                pendingReminderSave = false;
                saveReminder();
            } else {
                showReminderList("");
                showMessage(grantResults.length > 0 && grantResults[0] == PackageManager.PERMISSION_GRANTED
                    ? "Notifications enabled. Future reminders were rescheduled."
                    : "Notifications remain off. You can still use and complete saved reminders.");
            }
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
                    if (scheduleReminder(id, pendingTitle, pendingDueAt)) {
                        showMessage(hasExactAlarmAccess()
                            ? "Reminder saved. Android may apply battery-saving delays."
                            : "Reminder saved. Android may delay its alert; enable precise timing in the reminder list.");
                    } else {
                        showMessage("Reminder saved without an alert. Check Android's alarm and notification settings.");
                    }
                } else {
                    showMessage("Reminder saved without an alert; notification permission was declined.");
                }
            } else {
                showMessage("Reminder saved on this device. No notification was scheduled.");
            }
            showReminderList("");
            if (pendingDueAt > System.currentTimeMillis()
                && Build.VERSION.SDK_INT >= Build.VERSION_CODES.S
                && !hasExactAlarmAccess()
                && (Build.VERSION.SDK_INT < 33 ||
                    checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) == PackageManager.PERMISSION_GRANTED)) {
                promptForExactAlarmAccess();
            }
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
            addButton("Create a reminder", () -> showReminderForm("", 0));
            if (Build.VERSION.SDK_INT >= 33 &&
                checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS) != PackageManager.PERMISSION_GRANTED) {
                addButton("Enable reminder notifications", () -> requestPermissions(
                    new String[]{Manifest.permission.POST_NOTIFICATIONS}, REQUEST_NOTIFICATIONS));
            } else if (!notificationsEnabled()) {
                addButton("Open notification settings", this::openNotificationSettings);
            }
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S && !hasExactAlarmAccess()) {
                addButton("Enable precise reminder timing", this::requestExactAlarmAccess);
            }
            addButton("Back to companion", this::showHome);
            addReturnButton();
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

    private boolean scheduleReminder(int id, String title, long dueAt) {
        AlarmManager alarms = getSystemService(AlarmManager.class);
        if (alarms == null) {
            return false;
        }
        try {
            Intent alarmIntent = new Intent(this, ReminderAlarmReceiver.class)
                .putExtra(ReminderAlarmReceiver.EXTRA_TITLE, title)
                .putExtra(ReminderAlarmReceiver.EXTRA_TASK_ID, id);
            int flags = PendingIntent.FLAG_UPDATE_CURRENT;
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) flags |= PendingIntent.FLAG_IMMUTABLE;
            PendingIntent pending = PendingIntent.getBroadcast(this, id, alarmIntent, flags);
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S && alarms.canScheduleExactAlarms()) {
                try {
                    alarms.setExactAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, dueAt, pending);
                } catch (SecurityException permissionChanged) {
                    alarms.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, dueAt, pending);
                }
            } else {
                alarms.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, dueAt, pending);
            }
            return true;
        } catch (SecurityException | IllegalStateException error) {
            return false;
        }
    }

    private boolean hasExactAlarmAccess() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.S) return true;
        AlarmManager alarms = getSystemService(AlarmManager.class);
        return alarms != null && alarms.canScheduleExactAlarms();
    }

    private boolean notificationsEnabled() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.N) return true;
        android.app.NotificationManager manager = getSystemService(android.app.NotificationManager.class);
        return manager != null && manager.areNotificationsEnabled();
    }

    private void openNotificationSettings() {
        Intent settingsIntent = new Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS)
            .putExtra(Settings.EXTRA_APP_PACKAGE, getPackageName());
        try {
            refreshRemindersOnResume = true;
            startActivity(settingsIntent);
        } catch (ActivityNotFoundException error) {
            refreshRemindersOnResume = false;
            showError("Open Android Settings, then allow notifications for Xenomind Companion.");
        }
    }

    private void promptForExactAlarmAccess() {
        new AlertDialog.Builder(this)
            .setTitle("Improve reminder timing?")
            .setMessage("Android can delay standard reminders by up to an hour. Allow Xenomind to set exact alarms for alerts close to the time you choose.")
            .setNegativeButton("Keep delayed alerts", (dialog, which) -> dialog.dismiss())
            .setPositiveButton("Open alarm settings", (dialog, which) -> requestExactAlarmAccess())
            .show();
    }

    private void requestExactAlarmAccess() {
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.S || hasExactAlarmAccess()) return;
        Intent settingsIntent = new Intent(Settings.ACTION_REQUEST_SCHEDULE_EXACT_ALARM)
            .setData(Uri.parse("package:" + getPackageName()));
        try {
            refreshAlarmsOnResume = true;
            startActivity(settingsIntent);
        } catch (ActivityNotFoundException error) {
            refreshAlarmsOnResume = false;
            showError("Open Android Settings, then allow Xenomind under Alarms & reminders.");
        }
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
        android.app.NotificationManager notifications = getSystemService(android.app.NotificationManager.class);
        if (notifications != null) notifications.cancel(id);
    }

    private void openDocumentPicker() {
        beginPage("CHOOSE ITEMS", "ANDROID SYSTEM PICKER");
        addText(
            "Choose only the photos or files you want XENOMIND to use. Your selection stays on this device.",
            14, MUTED, false, 0, 0, 16, 0
        );
        addButton("Cancel selection", () -> showHome("cancel"));
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
        if (resultCode != RESULT_OK || data == null) {
            if (requestCode == REQUEST_PHOTOS || requestCode == REQUEST_FILES) showHome("cancel");
            else if (requestCode == REQUEST_DESTINATION) showSelectedItems("cancel");
            return;
        }
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
        showSelectedItems("organize".equals(libraryAction) ? "cancel" : "success");
    }

    private void showSelectedItems(String returnOutcome) {
        beginPage("SELECTION / REVIEW", "NOTHING HAS BEEN SHARED");
        addText(libraryRequest.isEmpty() ? "Your selection" : libraryRequest, 18, TEXT, true, 0, 0, 5, 0);
        addText("organize".equals(libraryAction)
                ? selectedUris.size() + " item(s) selected. Choose a destination to copy them; originals stay in place."
                : selectedUris.size() + " item(s) selected. Review the system share sheet before sending.",
            13, MUTED, false, 0, 0, 15, 0);
        for (Uri uri : selectedUris) {
            addText(displayName(uri), 12, MUTED, false, 0, 0, 8, 0);
        }
        addButton("Choose another selection", this::openDocumentPicker);
        if ("organize".equals(libraryAction)) {
            addButton("Choose a destination folder", this::openDestinationPicker);
        } else {
            addButton("Open share sheet", this::shareSelection);
        }
        addButton("Cancel", () -> showHome("cancel"));
        addReturnButton(returnOutcome);
    }

    private void shareSelection() {
        if (selectedUris.isEmpty()) {
            showError("Select at least one item first.");
            return;
        }
        Intent share = new Intent(selectedUris.size() == 1
            ? Intent.ACTION_SEND : Intent.ACTION_SEND_MULTIPLE);
        share.setType("organize".equals(libraryAction) ? "*/*"
            : "photos".equals(libraryAction) ? "image/*" : "*/*");
        if (selectedUris.size() == 1) {
            share.putExtra(Intent.EXTRA_STREAM, selectedUris.get(0));
        } else {
            share.putParcelableArrayListExtra(Intent.EXTRA_STREAM, new ArrayList<>(selectedUris));
        }
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
        beginPage("CHOOSE DESTINATION", "COPY SELECTED FILES");
        addText(
            selectedUris.size() + " item(s) are ready to copy. Choose a destination folder; originals will be kept.",
            14, MUTED, false, 0, 0, 16, 0
        );
        addButton("Back to selected items", this::showSelectedItems);
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
            .setNegativeButton("Cancel", (dialog, which) -> showHome("cancel"))
            .setPositiveButton("Copy files", (dialog, which) -> copySelectedFiles(tree))
            .show();
    }

    private void copySelectedFiles(Uri tree) {
        final ArrayList<Uri> sources = new ArrayList<>(selectedUris);
        beginPage("COPYING FILES", "ORIGINALS ARE KEPT");
        addText("Copying " + sources.size() + " selected item(s) into the folder you chose.",
            15, TEXT, true, 0, 0, 16, 0);
        addText("Keep XENOMIND open until the copy finishes.",
            13, MUTED, false, 0, 0, 18, 0);
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
        } catch (IOException | SecurityException error) {
            try {
                DocumentsContract.deleteDocument(getContentResolver(), destination);
            } catch (IOException | SecurityException cleanupError) {
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
        AlertDialog.Builder dialog = new AlertDialog.Builder(this)
            .setTitle("Xenomind could not continue")
            .setMessage(message)
            .setPositiveButton("OK", (alert, which) -> alert.dismiss());
        if (handoffReturnUrl != null) {
            dialog.setNeutralButton("Return to XENOMIND", (alert, which) -> returnToCockpit("error"));
        }
        dialog.show();
    }

    private void addReturnButton() {
        addReturnButton("success");
    }

    private void addReturnButton(String outcome) {
        if (handoffReturnUrl == null) return;
        addButton("Return to XENOMIND", () -> returnToCockpit(outcome));
    }

    private void returnToCockpit(String outcome) {
        if (handoffReturnUrl == null) return;
        Uri original = Uri.parse(handoffReturnUrl);
        Uri callback = original.buildUpon().clearQuery()
            .appendQueryParameter("handoff", outcome)
            .appendQueryParameter("id", original.getQueryParameter("id"))
            .appendQueryParameter("modeAction", "mode".equals(handoffModule) ? handoffAction : "")
            .build();
        try {
            startActivity(new Intent(Intent.ACTION_VIEW, callback));
            finish();
        } catch (ActivityNotFoundException error) {
            showMessage("Could not reopen XENOMIND. Return to it from your app switcher.");
        }
    }

    private String validatedReturnUrl(String value) {
        if (value == null || value.length() > 2048) return null;
        Uri uri = Uri.parse(value);
        String scheme = uri.getScheme();
        if (!"https".equalsIgnoreCase(scheme) && !"http".equalsIgnoreCase(scheme)) return null;
        String authority = uri.getAuthority();
        if (uri.getHost() == null || authority == null || authority.contains("@")) return null;
        if (!"success".equals(uri.getQueryParameter("handoff")) ||
            uri.getQueryParameter("id") == null || uri.getQueryParameter("id").isEmpty()) return null;
        return uri.toString();
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }
}
