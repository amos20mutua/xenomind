package io.xenomind.bridge;

import android.content.ComponentName;
import android.content.Context;
import android.provider.Settings;
import android.text.TextUtils;

import java.util.Collections;
import java.util.HashSet;
import java.util.Set;

final class FocusModes {
    static final String STORE = "xenomind_focus_modes";
    static final String ACTIVE_MODE = "active_mode";
    static final String ACTIVE_CALLBACK = "active_mode_callback";
    static final String[] KEYS = {"focus", "rehearsal", "rest"};
    static final String[] LABELS = {"Focus", "Rehearsal", "Rest"};

    private FocusModes() {}

    static boolean isValid(String key) {
        for (String candidate : KEYS) if (candidate.equals(key)) return true;
        return false;
    }

    static String label(String key) {
        for (int index = 0; index < KEYS.length; index++) {
            if (KEYS[index].equals(key)) return LABELS[index];
        }
        return "Focus";
    }

    static String blockedKey(String key) {
        return "blocked_apps_" + key;
    }

    static Set<String> blockedApps(Context context, String key) {
        if (!isValid(key)) return Collections.emptySet();
        Set<String> saved = context.getSharedPreferences(STORE, Context.MODE_PRIVATE)
            .getStringSet(blockedKey(key), Collections.emptySet());
        return saved == null ? Collections.emptySet() : new HashSet<>(saved);
    }

    static boolean saveBlockedApps(Context context, String key, Set<String> packages) {
        if (!isValid(key)) return false;
        return context.getSharedPreferences(STORE, Context.MODE_PRIVATE).edit()
            .putStringSet(blockedKey(key), new HashSet<>(packages))
            .commit();
    }

    static boolean setActive(Context context, String key) {
        return isValid(key) && context.getSharedPreferences(STORE, Context.MODE_PRIVATE)
            .edit().putString(ACTIVE_MODE, key).commit();
    }

    static boolean clearActive(Context context) {
        return context.getSharedPreferences(STORE, Context.MODE_PRIVATE).edit()
            .remove(ACTIVE_MODE).commit();
    }

    static String activeMode(Context context) {
        String active = context.getSharedPreferences(STORE, Context.MODE_PRIVATE)
            .getString(ACTIVE_MODE, "");
        return isValid(active) ? active : "";
    }

    static boolean blockerEnabled(Context context) {
        String enabled = Settings.Secure.getString(
            context.getContentResolver(), Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES
        );
        if (TextUtils.isEmpty(enabled)) return false;
        ComponentName expected = new ComponentName(context, FocusBlockerService.class);
        for (String item : enabled.split(":")) {
            ComponentName component = ComponentName.unflattenFromString(item);
            if (expected.equals(component)) return true;
        }
        return false;
    }
}
