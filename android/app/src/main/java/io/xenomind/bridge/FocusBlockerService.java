package io.xenomind.bridge;

import android.accessibilityservice.AccessibilityService;
import android.graphics.Color;
import android.graphics.PixelFormat;
import android.net.Uri;
import android.content.Intent;
import android.view.Gravity;
import android.view.WindowManager;
import android.view.accessibility.AccessibilityEvent;
import android.widget.Button;
import android.widget.LinearLayout;
import android.widget.TextView;

import java.util.Set;

public final class FocusBlockerService extends AccessibilityService {
    private static final String BACKGROUND = "#080D14";
    private static final String MINT = "#78F3D0";
    private WindowManager windowManager;
    private LinearLayout blockerView;

    @Override
    public void onServiceConnected() {
        super.onServiceConnected();
        windowManager = getSystemService(WindowManager.class);
    }

    @Override
    public void onAccessibilityEvent(AccessibilityEvent event) {
        if (event == null || event.getPackageName() == null) return;
        String packageName = event.getPackageName().toString();
        if (getPackageName().equals(packageName)) return;

        String activeMode = FocusModes.activeMode(this);
        if (activeMode.isEmpty()) {
            removeBlocker();
            return;
        }
        Set<String> blockedPackages = FocusModes.blockedApps(this, activeMode);
        if (blockedPackages.contains(packageName)) {
            showBlocker(activeMode);
        } else {
            removeBlocker();
        }
    }

    @Override
    public void onInterrupt() {
        removeBlocker();
    }

    @Override
    public void onDestroy() {
        removeBlocker();
        super.onDestroy();
    }

    private void showBlocker(String modeKey) {
        if (blockerView != null || windowManager == null) return;
        String modeName = FocusModes.label(modeKey);
        LinearLayout root = new LinearLayout(this);
        root.setOrientation(LinearLayout.VERTICAL);
        root.setGravity(Gravity.CENTER);
        root.setPadding(dp(28), dp(28), dp(28), dp(28));
        root.setBackgroundColor(Color.parseColor(BACKGROUND));
        root.setClickable(true);
        root.setFocusableInTouchMode(true);

        TextView brand = text("X E N O M I N D", 12, MINT, true);
        brand.setGravity(Gravity.CENTER);
        root.addView(brand, matchWrap());
        TextView title = text(modeName + " mode is active", 24, Color.WHITE, true);
        title.setGravity(Gravity.CENTER);
        LinearLayout.LayoutParams titleParams = matchWrap();
        titleParams.topMargin = dp(22);
        root.addView(title, titleParams);
        TextView details = text("This app is paused until you end the mode.", 15,
            Color.rgb(179, 197, 204), false);
        details.setGravity(Gravity.CENTER);
        LinearLayout.LayoutParams detailsParams = matchWrap();
        detailsParams.topMargin = dp(10);
        root.addView(details, detailsParams);

        Button home = new Button(this);
        home.setText("Return to Home screen");
        home.setAllCaps(false);
        home.setOnClickListener(view -> performGlobalAction(GLOBAL_ACTION_HOME));
        LinearLayout.LayoutParams homeParams = matchWrap();
        homeParams.topMargin = dp(28);
        root.addView(home, homeParams);

        Button end = new Button(this);
        end.setText("End " + modeName + " mode");
        end.setAllCaps(false);
        end.setOnClickListener(view -> {
            String callback = getSharedPreferences(FocusModes.STORE, MODE_PRIVATE)
                .getString(FocusModes.ACTIVE_CALLBACK, "");
            if (!FocusModes.clearActive(this)) {
                android.widget.Toast.makeText(this, "Could not end the mode. Try again.",
                    android.widget.Toast.LENGTH_LONG).show();
                return;
            }
            getSharedPreferences(FocusModes.STORE, MODE_PRIVATE).edit()
                .remove(FocusModes.ACTIVE_CALLBACK).commit();
            removeBlocker();
            returnToCockpitAfterStop(callback);
        });
        root.addView(end, matchWrap());

        WindowManager.LayoutParams params = new WindowManager.LayoutParams(
            WindowManager.LayoutParams.MATCH_PARENT,
            WindowManager.LayoutParams.MATCH_PARENT,
            WindowManager.LayoutParams.TYPE_ACCESSIBILITY_OVERLAY,
            WindowManager.LayoutParams.FLAG_LAYOUT_IN_SCREEN
                | WindowManager.LayoutParams.FLAG_LAYOUT_INSET_DECOR,
            PixelFormat.TRANSLUCENT
        );
        params.gravity = Gravity.TOP | Gravity.START;
        try {
            windowManager.addView(root, params);
            blockerView = root;
        } catch (WindowManager.BadTokenException | SecurityException error) {
            performGlobalAction(GLOBAL_ACTION_HOME);
        }
    }

    private void removeBlocker() {
        if (blockerView == null || windowManager == null) return;
        try {
            windowManager.removeView(blockerView);
        } catch (IllegalArgumentException ignored) {
            // The system may already have removed this accessibility overlay.
        }
        blockerView = null;
    }

    private void returnToCockpitAfterStop(String value) {
        if (value == null || value.isEmpty()) return;
        Uri original = Uri.parse(value);
        String id = original.getQueryParameter("id");
        if (id == null || id.isEmpty()) return;
        Uri callback = original.buildUpon().clearQuery()
            .appendQueryParameter("handoff", "success")
            .appendQueryParameter("id", id)
            .appendQueryParameter("modeAction", "stop")
            .build();
        try {
            startActivity(new Intent(Intent.ACTION_VIEW, callback).addFlags(Intent.FLAG_ACTIVITY_NEW_TASK));
        } catch (android.content.ActivityNotFoundException ignored) {
            // The mode is already stopped; the user can reopen the cockpit manually.
        }
    }

    private TextView text(String value, int size, int color, boolean bold) {
        TextView view = new TextView(this);
        view.setText(value);
        view.setTextSize(size);
        view.setTextColor(color);
        if (bold) view.setTypeface(null, android.graphics.Typeface.BOLD);
        return view;
    }

    private LinearLayout.LayoutParams matchWrap() {
        return new LinearLayout.LayoutParams(
            LinearLayout.LayoutParams.MATCH_PARENT,
            LinearLayout.LayoutParams.WRAP_CONTENT
        );
    }

    private int dp(int value) {
        return Math.round(value * getResources().getDisplayMetrics().density);
    }
}
