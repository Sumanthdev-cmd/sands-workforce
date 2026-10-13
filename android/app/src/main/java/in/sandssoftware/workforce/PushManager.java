package in.sandssoftware.workforce;

import android.Manifest;
import android.app.*;
import android.app.job.*;
import android.content.*;
import android.content.pm.PackageManager;
import android.media.AudioAttributes;
import android.net.Uri;
import android.os.Build;
import android.provider.Settings;
import com.google.firebase.FirebaseApp;
import com.google.firebase.messaging.FirebaseMessaging;
import org.json.*;
import java.security.SecureRandom;
import java.util.*;
import java.util.function.Consumer;

/** Notification delivery is independent of check-in, GPS and the tracking service. */
public final class PushManager {
    public static final String CHANNEL = "sands_workforce_alerts";
    private static final int JOB = 202;
    private final Context context;
    private final WorkController work;
    private final NotificationManager notifications;
    private volatile String state = "Enable phone alerts for approval and workforce updates.";

    PushManager(Context context, WorkController work) {
        this.context = context; this.work = work;
        notifications = context.getSystemService(NotificationManager.class);
        NotificationChannel channel = new NotificationChannel(CHANNEL,"Workforce alerts",NotificationManager.IMPORTANCE_HIGH);
        channel.setDescription("Approvals, tasks and other notifications for your signed-in account");
        channel.enableVibration(true); channel.setShowBadge(true);
        channel.setLockscreenVisibility(Notification.VISIBILITY_PRIVATE);
        channel.setSound(Settings.System.DEFAULT_NOTIFICATION_URI,
            new AudioAttributes.Builder().setUsage(AudioAttributes.USAGE_NOTIFICATION).build());
        notifications.createNotificationChannel(channel);
    }
    public boolean configured() { return !FirebaseApp.getApps(context).isEmpty(); }
    public boolean allowed() {
        NotificationChannel channel=notifications.getNotificationChannel(CHANNEL);
        return notifications.areNotificationsEnabled() && channel != null
            && channel.getImportance()!=NotificationManager.IMPORTANCE_NONE
            && (Build.VERSION.SDK_INT<33 || context.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)==PackageManager.PERMISSION_GRANTED);
    }
    public String status() { return configured() ? (allowed()?state:"Phone alerts are off. Enable notifications in app settings.")
        : "Push setup is pending. The app needs your organisation’s Firebase configuration."; }
    private void state(String value) {state=value;work.notifyUi();}

    // Called on the controller's serial executor immediately after a successful login.
    public synchronized void newLogin() {
        clearDisplayed();
        work.store.put("push_binding",UUID.randomUUID().toString());
        work.store.put("push_identity",work.api.identity());
        work.store.remove("push_seen");
        work.store.remove("push_registered");
        state("Connecting phone alerts…");
        work.main.post(this::connect);
    }
    private synchronized JSONObject installation() throws Exception {
        String id=work.store.get("push_installation","");
        if (id.isEmpty()) {id=UUID.randomUUID().toString();work.store.put("push_installation",id);}
        String secret=work.store.get("push_secret","");
        if (secret.isEmpty()) {
            byte[] bytes=new byte[32];new SecureRandom().nextBytes(bytes);
            StringBuilder hex=new StringBuilder();for(byte b:bytes)hex.append(String.format(Locale.ROOT,"%02x",b & 255));
            secret=hex.toString();work.store.put("push_secret",secret);
        }
        return new JSONObject().put("installation_id",id).put("installation_secret",secret)
            .put("binding_id",work.store.get("push_binding",""));
    }
    public void connect() {
        if (!work.api.loggedIn() || !configured()) {work.notifyUi();return;}
        work.io.execute(()->{
            if (!work.api.loggedIn())return;
            if (!work.api.identity().equals(work.store.get("push_identity","")))newLogin();
            FirebaseMessaging.getInstance().setAutoInitEnabled(allowed());
            if (!allowed()) {schedule();work.notifyUi();return;}
            FirebaseMessaging.getInstance().getToken().addOnSuccessListener(this::tokenChanged)
                .addOnFailureListener(e->{state("Could not connect phone alerts. Check internet and Google Play services, then retry.");schedule();});
        });
    }
    public void tokenChanged(String token) {
        if (token==null||token.isEmpty())return;
        work.store.put("push_token",token);
        // Register while the app is open. A JobScheduler-only path may wait for
        // Android to grant a background execution window after first sign-in.
        schedule();
        state("Registering this phone for alerts…");
        register(retry->{if(retry)schedule();});
    }
    public void schedule() {
        if (!configured() || !work.api.loggedIn())return;
        JobInfo job=new JobInfo.Builder(JOB,new ComponentName(context,PushRegistrationJob.class))
            .setRequiredNetworkType(JobInfo.NETWORK_TYPE_ANY)
            .setBackoffCriteria(30000,JobInfo.BACKOFF_POLICY_EXPONENTIAL).setPersisted(true).build();
        context.getSystemService(JobScheduler.class).schedule(job);
    }
    public void register(Consumer<Boolean> done) {
        work.io.execute(()->{
            if (!configured()||!work.api.loggedIn()) {done.accept(false);return;}
            try {
                // Same executor as login/logout avoids token registration racing account changes.
                if (!work.api.identity().equals(work.store.get("push_identity","")))newLogin();
                String token=work.store.get("push_token","");
                if (token.isEmpty()) {
                    if(!allowed()){done.accept(false);return;}
                    FirebaseMessaging.getInstance().getToken().addOnSuccessListener(value->{
                        work.store.put("push_token",value);register(done);
                    }).addOnFailureListener(error->done.accept(true));
                    return;
                }
                JSONObject body=installation().put("fcm_token",token).put("enabled",allowed());
                JSONObject result=(JSONObject)work.api.call("/mobile-push/"+work.api.kind()+"/register","POST",body);
                work.store.put("push_registered",body.getString("binding_id"));
                state(!allowed()?"Phone alerts are off.":result.optBoolean("server_configured")
                    ?"Phone registered for alerts. Send a test to check delivery."
                    :"Phone registered. Firebase delivery still needs to be enabled on the server.");
                done.accept(false);
            } catch (Exception e) {
                int code=e instanceof ApiClient.ApiException?((ApiClient.ApiException)e).status:0;
                state(code==404?"The phone notification update is not installed on the server yet."
                    :code==401||code==403?"Sign in again to reconnect phone alerts."
                    :"Phone alert registration failed ("+(code==0?"connection":String.valueOf(code))+"). "+WorkController.friendly(e));
                done.accept(code==0||code==429||code>=500);
            }
        });
    }
    // Called after successful logout (which clears the native session first).
    public void signedOut() {
        JSONObject previous;
        synchronized(this){
            try {previous=installation();}catch(Exception e){previous=null;}
            work.store.remove("push_binding");work.store.remove("push_identity");work.store.remove("push_registered");
            work.store.remove("push_seen");clearDisplayed();
        }
        context.getSystemService(JobScheduler.class).cancel(JOB);
        if(configured())FirebaseMessaging.getInstance().setAutoInitEnabled(false);
        if(previous!=null)try {work.api.call("/mobile-push/unregister","POST",previous);}catch(Exception ignored){}
        // Even if network cleanup fails, queued alerts fail the local binding check.
        state("Signed out. Phone alerts for this account are off.");
    }
    public void sendTest(WorkController.Done done) {
        work.io.execute(()->{
            String error=null;
            try {
                if(!allowed())throw new Exception("Allow phone notifications first.");
                String binding=work.store.get("push_binding","");
                if(binding.isEmpty()||!binding.equals(work.store.get("push_registered","")))
                    throw new Exception("Wait until this phone is registered, then send a test.");
                work.api.call("/mobile-push/"+work.api.kind()+"/test","POST",null);
                state("Test queued. Lock your phone and check for a Workforce alert.");
            }catch(Exception e){error=WorkController.friendly(e);}
            String result=error;work.main.post(()->done.complete(result));
        });
    }
    public synchronized boolean currentBinding(String binding) {
        return work.api.loggedIn() && work.api.identity().equals(work.store.get("push_identity",""))
            && PushPolicy.uuid(binding) && binding.equals(work.store.get("push_binding",""));
    }
    public synchronized void received(Map<String,String> data) {
        String binding=work.store.get("push_binding","");
        if(!allowed()||!currentBinding(binding)||!PushPolicy.accepts(data,binding,work.api.loggedIn()))return;
        String event=data.get("event_id");
        JSONArray seen;
        try {seen=new JSONArray(work.store.get("push_seen","[]"));}catch(Exception e){seen=new JSONArray();}
        for(int i=0;i<seen.length();i++)if(event.equals(seen.optString(i)))return;
        String route=PushPolicy.route(data.get("route"),work.api.vendor());
        Intent open=new Intent(context,MainActivity.class).setAction("sands.alert."+event)
            .setFlags(Intent.FLAG_ACTIVITY_CLEAR_TOP|Intent.FLAG_ACTIVITY_SINGLE_TOP)
            .putExtra("push_binding",binding).putExtra("push_route",route);
        PendingIntent pending=PendingIntent.getActivity(context,0,open,PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE);
        Notification publicView=new Notification.Builder(context,CHANNEL).setSmallIcon(R.drawable.ic_alert)
            .setContentTitle("Workforce update").setContentText("Unlock your phone to view details.").build();
        String title=data.getOrDefault("title","Workforce update"),body=data.getOrDefault("body","Open the app for details.");
        Notification notification=new Notification.Builder(context,CHANNEL).setSmallIcon(R.drawable.ic_alert)
            .setContentTitle(title).setContentText(body).setStyle(new Notification.BigTextStyle().bigText(body))
            .setVisibility(Notification.VISIBILITY_PRIVATE).setPublicVersion(publicView)
            .setCategory(Notification.CATEGORY_EVENT).setAutoCancel(true).setOnlyAlertOnce(true)
            .setContentIntent(pending).build();
        try {notifications.notify("sands-alert-"+event,200,notification);}catch(SecurityException e){return;}
        JSONArray recent=new JSONArray();for(int i=Math.max(0,seen.length()-499);i<seen.length();i++)recent.put(seen.optString(i));
        recent.put(event);work.store.put("push_seen",recent.toString());
        state("Phone alerts connected. Last alert received just now.");
    }
    private void clearDisplayed() {
        for(android.service.notification.StatusBarNotification n:notifications.getActiveNotifications())
            if(n.getTag()!=null&&n.getTag().startsWith("sands-alert-"))notifications.cancel(n.getTag(),n.getId());
    }
}
