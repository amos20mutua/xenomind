package io.xenomind.bridge;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.os.Build;
import android.util.Log;

public final class ReminderAlarmReceiver extends BroadcastReceiver {
    private static final String TAG = "XenomindReminder";
    static final String CHANNEL_ID = "xenomind_reminders";
    static final String EXTRA_TITLE = "title";
    static final String EXTRA_TASK_ID = "task_id";

    @Override
    public void onReceive(Context context, Intent intent) {
        String title = intent.getStringExtra(EXTRA_TITLE);
        int taskId = intent.getIntExtra(EXTRA_TASK_ID, 0);
        if (title == null || title.trim().isEmpty()) {
            return;
        }

        NotificationManager manager = context.getSystemService(NotificationManager.class);
        if (manager == null) {
            Log.e(TAG, "NotificationManager unavailable; reminder notification was not shown.");
            return;
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.N && !manager.areNotificationsEnabled()) {
            Log.w(TAG, "Notifications are disabled; reminder notification was not shown.");
            return;
        }
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            NotificationChannel channel = new NotificationChannel(
                CHANNEL_ID, "Xenomind reminders", NotificationManager.IMPORTANCE_DEFAULT
            );
            manager.createNotificationChannel(channel);
        }

        Notification.Builder builder = Build.VERSION.SDK_INT >= Build.VERSION_CODES.O
            ? new Notification.Builder(context, CHANNEL_ID)
            : new Notification.Builder(context);
        Notification notification = builder
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle("Xenomind reminder")
            .setContentText(title)
            .setAutoCancel(true)
            .build();
        manager.notify(taskId, notification);
    }
}
