package io.xenomind.bridge;

import android.app.Notification;
import android.app.NotificationChannel;
import android.app.NotificationManager;
import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.app.PendingIntent;
import android.net.Uri;
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
        Intent openReminders = new Intent(context, MainActivity.class)
            .setAction(Intent.ACTION_VIEW)
            .setData(Uri.parse("xenomind://run?module=reminder&action=list"))
            .addFlags(Intent.FLAG_ACTIVITY_NEW_TASK | Intent.FLAG_ACTIVITY_CLEAR_TOP | Intent.FLAG_ACTIVITY_SINGLE_TOP);
        int pendingFlags = PendingIntent.FLAG_UPDATE_CURRENT;
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.M) pendingFlags |= PendingIntent.FLAG_IMMUTABLE;
        PendingIntent contentIntent = PendingIntent.getActivity(context, taskId, openReminders, pendingFlags);
        Notification notification = builder
            .setSmallIcon(android.R.drawable.ic_dialog_info)
            .setContentTitle("Xenomind reminder")
            .setContentText(title)
            .setContentIntent(contentIntent)
            .setAutoCancel(true)
            .build();
        manager.notify(taskId, notification);
    }
}
