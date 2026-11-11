package io.xenomind.bridge;

import android.app.AlarmManager;
import android.app.PendingIntent;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.util.Log;

import org.json.JSONArray;
import org.json.JSONException;
import org.json.JSONObject;

public final class ReminderBootReceiver extends BroadcastReceiver {
    private static final String TAG = "XenomindBoot";
    private static final String STORE = "xenomind_reminders";
    private static final String TASKS = "tasks";

    @Override
    public void onReceive(Context context, Intent ignored) {
        String encoded = context.getSharedPreferences(STORE, Context.MODE_PRIVATE)
            .getString(TASKS, "[]");
        try {
            JSONArray tasks = new JSONArray(encoded);
            AlarmManager alarms = context.getSystemService(AlarmManager.class);
            if (alarms == null) {
                Log.e(TAG, "AlarmManager unavailable; reminders were not rescheduled.");
                return;
            }
            long now = System.currentTimeMillis();
            for (int index = 0; index < tasks.length(); index++) {
                JSONObject task = tasks.getJSONObject(index);
                long dueAt = task.optLong("dueAt", 0);
                if (task.optBoolean("completed", false) || dueAt <= now) {
                    continue;
                }
                int id = task.getInt("id");
                Intent alarmIntent = new Intent(context, ReminderAlarmReceiver.class)
                    .putExtra(ReminderAlarmReceiver.EXTRA_TITLE, task.getString("title"))
                    .putExtra(ReminderAlarmReceiver.EXTRA_TASK_ID, id);
                int flags = PendingIntent.FLAG_UPDATE_CURRENT;
                if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) {
                    flags |= PendingIntent.FLAG_IMMUTABLE;
                }
                PendingIntent pending = PendingIntent.getBroadcast(context, id, alarmIntent, flags);
                alarms.setAndAllowWhileIdle(AlarmManager.RTC_WAKEUP, dueAt, pending);
            }
        } catch (JSONException error) {
            Log.e(TAG, "Stored reminders are invalid; alarms were not rescheduled.", error);
        }
    }
}
