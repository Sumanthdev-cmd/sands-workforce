package in.sandssoftware.workforce;

import android.content.*;
import android.location.Location;
import android.os.*;
import org.json.*;
import java.time.Instant;
import java.util.*;
import java.util.concurrent.*;

/** Serialises attendance, uploads and reconciliation. UI never waits on network locks. */
public final class WorkController {
    public interface Done { void complete(String error); }
    public interface Listener { void changed(); }
    final Context context;
    final SecureStore store;
    final ApiClient api;
    final TrackingGate gate=new TrackingGate();
    final ExecutorService io=Executors.newSingleThreadExecutor();
    final Handler main=new Handler(Looper.getMainLooper());
    private final Set<Listener> listeners=new CopyOnWriteArraySet<>();
    public volatile JSONObject attendance=new JSONObject(), profile=new JSONObject();
    public volatile JSONArray outlets=new JSONArray();
    public volatile String message="Ready to sign in", lastSent="", lastFix="";
    public volatile boolean busy=false, wanted=false, serverReady=false, passwordChange=false;
    public volatile int queued=0;
    private JSONArray queue;
    private String deviceId="";
    private long lastAcceptedElapsed=0, lastStatusElapsed=0;
    private volatile long stopGeneration=0;
    private volatile boolean syncing=false;

    WorkController(Context c){
        context=c;store=new SecureStore(c);api=new ApiClient(store);
        attendance=store.object("attendance");
        try{queue=new JSONArray(store.get("queue","[]"));}catch(Exception e){queue=new JSONArray();}
        queued=queue.length();deviceId=store.get("device","");
        message=api.loggedIn()?"Refresh your workday to continue":"Sign in with your organisation account";
    }
    public void listen(Listener l){listeners.add(l);}
    public void unlisten(Listener l){listeners.remove(l);}
    void notifyUi(){main.post(()->{for(Listener l:listeners)l.changed();});}
    public boolean tracking(){return wanted&&gate.active(SystemClock.elapsedRealtime());}
    public boolean open(){return !attendance.optString("check_in_at","").isEmpty()&&!attendance.isNull("check_in_at")&&attendance.isNull("check_out_at");}
    public static long millis(String value){try{return Instant.parse(value).toEpochMilli();}catch(Exception e){try{return java.time.OffsetDateTime.parse(value).toInstant().toEpochMilli();}catch(Exception ignored){return 0;}}}
    public String id(){return attendance.optString("id","");}
    private void saveAttendance(JSONObject row){attendance=row;store.put("attendance",row.toString());notifyUi();}
    private void saveQueue(){store.put("queue",queue.toString());queued=queue.length();}
    public void execute(Throwing action,Done done){
        if(busy){if(done!=null)done.complete("Please wait for the current action.");return;}
        busy=true;notifyUi();io.execute(()->{
            String error=null;
            try{action.run();}catch(Exception e){error=friendly(e);message=error;if(e instanceof ApiClient.ApiException&&(((ApiClient.ApiException)e).status==401||((ApiClient.ApiException)e).status==403))pause("Sign in again or contact your administrator. Tracking paused.");}
            String result=error;busy=false;notifyUi();main.post(()->{if(done!=null)done.complete(result);});
        });
    }
    interface Throwing {void run() throws Exception;}
    static String friendly(Exception e){if(e instanceof java.net.SocketTimeoutException||e instanceof java.net.UnknownHostException)return "Cannot reach the server. Check your internet connection and retry.";return e.getMessage()==null?"The action could not be completed. Please retry.":e.getMessage();}

    public void login(String org,String code,String password,boolean vendor,Done done){
        execute(()->{
            pause("Signing in");api.login(org,code,password,vendor);WorkforceApp.push(context).newLogin();
            // A new login never inherits another account's queue, device, or tracking lease.
            queue=new JSONArray();saveQueue();store.remove("device");deviceId="";saveAttendance(new JSONObject());
            readProfile();checkServer();readStatus(false);message="Signed in. Location tracking is off until you check in or resume.";
        },done);
    }
    private void readProfile() throws Exception {
        profile=(JSONObject)api.call(api.vendor()?"/vendor-portal/me":"/auth/me","GET",null);
        passwordChange=profile.optBoolean(api.vendor()?"force_password_change":"must_change_password");
        if(api.vendor()&&!passwordChange)outlets=(JSONArray)api.call("/vendor-portal/outlets","GET",null);
    }
    private void checkServer() throws Exception {
        JSONObject v=(JSONObject)api.call("/mobile/version","GET",null);serverReady=v.optInt("version")==1;
        if(!serverReady)throw new Exception("The Android tracking server update is required.");
    }
    public void refresh(Done done){execute(()->{readProfile();checkServer();if(!passwordChange){readStatus(false);flush();}message=passwordChange?"Open Workspace to change your temporary password.":tracking()?"Your work session is being tracked.":open()?"Checked in. Tap Restore work tracking if you are working.":"You are checked out. Location tracking is off.";},done);}
    public void accountSetup(Done done){execute(()->{
        JSONObject result=(JSONObject)api.call("/workday-support/employee","GET",null);
        JSONArray lines=result.optJSONArray("messages");StringBuilder text=new StringBuilder();
        if(lines!=null)for(int i=0;i<lines.length();i++){if(i>0)text.append("\n\n");text.append(lines.optString(i));}
        message=text.length()>0?text.toString():"Account check completed.";
    },done);}
    public void changePassword(String current,String replacement,Done done){execute(()->{
        api.call(api.vendor()?"/vendor-portal/change-password":"/auth/change-password","POST",new JSONObject().put("current_password",current).put("new_password",replacement));
        readProfile();message="Password updated. Refresh your workday.";
    },done);}
    private void device() throws Exception {
        if(api.vendor()||!deviceId.isEmpty())return;
        String identifier=store.get("device_identifier","");
        if(identifier.isEmpty()){identifier="android-"+UUID.randomUUID();store.put("device_identifier",identifier);}
        JSONObject p=new JSONObject().put("device_identifier",identifier).put("platform","ANDROID").put("device_name",Build.MANUFACTURER+" "+Build.MODEL).put("manufacturer",Build.MANUFACTURER).put("model",Build.MODEL).put("os_version",Build.VERSION.RELEASE).put("app_version",BuildConfig.VERSION_NAME);
        JSONObject r;
        try{r=(JSONObject)api.call("/devices/register","POST",p);}catch(ApiClient.ApiException e){
            if(e.status!=409)throw e;
            identifier="android-"+UUID.randomUUID();store.put("device_identifier",identifier);p.put("device_identifier",identifier);r=(JSONObject)api.call("/devices/register","POST",p);
        }
        deviceId=r.getString("id");store.put("device",deviceId);
    }
    JSONObject point(Location l) throws Exception {
        int battery=((BatteryManager)context.getSystemService(Context.BATTERY_SERVICE)).getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY);
        return new JSONObject().put("client_event_id",UUID.randomUUID().toString()).put("latitude",l.getLatitude()).put("longitude",l.getLongitude()).put("accuracy_meters",l.hasAccuracy()?l.getAccuracy():10000).put("speed_mps",l.hasSpeed()?Math.max(0,l.getSpeed()):JSONObject.NULL).put("battery_percentage",battery>=0&&battery<=100?battery:JSONObject.NULL).put("recorded_at",Instant.ofEpochMilli(l.getTime()).toString());
    }
    private void submitActionPosition(Location l) throws Exception {
        device();api.call("/locations/batch","POST",new JSONObject().put("device_id",deviceId).put("points",new JSONArray().put(point(l))));
    }
    public void checkIn(Location l,String outlet,Done done){
        long generation=stopGeneration;
        execute(()->{
            message="Checking the attendance server…";notifyUi();
            checkServer();
            if(passwordChange)throw new Exception("Change your temporary password first.");
            JSONObject row;
            if(api.vendor())row=(JSONObject)api.call("/vendor-portal/attendance/check-in","POST",new JSONObject().put("outlet_id",outlet).put("latitude",l.getLatitude()).put("longitude",l.getLongitude()).put("accuracy_meters",l.getAccuracy()));
            else{message="Sending your check-in location…";notifyUi();submitActionPosition(l);message="Saving check-in…";notifyUi();row=(JSONObject)api.call("/attendance/check-in","POST",new JSONObject().put("automatic",false));}
            saveAttendance(row);readStatus(false);
            if(generation!=stopGeneration)throw new Exception("Check-in saved. Tracking is paused; tap Restore work tracking.");
            arm();message="Check-in saved. Starting work location tracking.";
        },done);
    }
    public void resume(Done done){long generation=stopGeneration;execute(()->{checkServer();readStatus(false);device();if(generation!=stopGeneration)throw new Exception("Tracking stayed paused. Refresh and try again.");arm();},done);}
    public void reauthenticate(String password,Done done){
        if(tracking()){if(done!=null)done.complete("Your work session is connected. Check out before reconnecting this account.");return;}
        JSONObject current=api.session();pause("Reconnecting your account. Tracking paused.");
        execute(()->{api.login(current.getString("organization_code"),current.getString("code"),password,"vendor".equals(current.optString("kind")));WorkforceApp.push(context).connect();readProfile();checkServer();if(!passwordChange){readStatus(false);flush();}message="Signed in again. Tap Restore work tracking if you are still working.";},done);
    }
    private void arm() throws Exception {
        if(!attendance.optBoolean("active"))throw new Exception(attendance.optBoolean("requires_review")?"This attendance session is over 24 hours old. Ask Admin to correct the attendance before resuming.":"No active check-in was found.");
        store.put("resume_reminder","true");wanted=true;confirmGate();
        if(!gate.active(SystemClock.elapsedRealtime())){wanted=false;throw new Exception("Check your phone's date and time, then refresh.");}
    }
    private void confirmGate(){gate.confirm(id(),millis(attendance.optString("check_in_at")),millis(attendance.optString("tracking_until")),System.currentTimeMillis(),SystemClock.elapsedRealtime());}
    public void checkOut(Location l,Done done){
        execute(()->{
            message="Saving checkout… Work tracking stays on until checkout is confirmed.";notifyUi();
            flush();
            JSONObject row;
            if(api.vendor())row=(JSONObject)api.call("/vendor-portal/attendance/check-out","POST",new JSONObject().put("outlet_id",attendance.getString("outlet_id")).put("latitude",l.getLatitude()).put("longitude",l.getLongitude()).put("accuracy_meters",l.getAccuracy()));
            else{submitActionPosition(l);row=(JSONObject)api.call("/attendance/check-out","POST",new JSONObject().put("automatic",false));}
            // Stop only after the attendance API accepts checkout. Failed GPS,
            // validation or network attempts must not become a hidden Pause button.
            pause("Checkout saved. Location tracking is off.");
            saveAttendance(row);store.remove("resume_reminder");
        },error->{if(error!=null){message="Checkout not confirmed. "+(tracking()?"Work tracking is still on. ":"Check your workday status and restore tracking if you are on duty. ")+error;notifyUi();}if(done!=null)done.complete(error==null?null:message);});
    }
    private void readStatus(boolean keepLease) throws Exception {
        String path="/mobile/"+api.kind()+"/status";
        if(!id().isEmpty()&&open())path+="?attendance_id="+id();
        JSONObject row=(JSONObject)api.call(path,"GET",null);
        saveAttendance(row);lastStatusElapsed=SystemClock.elapsedRealtime();
        if(!row.optBoolean("active")){pause("Location tracking stopped. No active work session.");store.remove("resume_reminder");}
        else if(keepLease&&wanted)confirmGate();
    }
    public void pause(String reason){
        stopGeneration++;wanted=false;gate.stop();message=reason;
        context.stopService(new Intent(context,TrackingService.class));notifyUi();
    }
    public void captured(Location location){
        long elapsed=SystemClock.elapsedRealtime();String session=id();long generation=stopGeneration;
        if(!tracking()||!gate.allows(session,location.getTime(),elapsed))return;
        if(location.isFromMockProvider()){message="A mock location was ignored. Turn off simulated location.";notifyUi();return;}
        if(!location.hasAccuracy()||location.getAccuracy()>200||Math.abs(System.currentTimeMillis()-location.getTime())>60000)return;
        if(elapsed-lastAcceptedElapsed<25000)return;
        lastAcceptedElapsed=elapsed;lastFix=Instant.ofEpochMilli(location.getTime()).toString();
        io.execute(()->{
            if(generation!=stopGeneration||!gate.allows(session,location.getTime(),SystemClock.elapsedRealtime()))return;
            try{
                if(queue.length()>=1800){pause("Offline queue is full. Connect to the internet, refresh, and resume tracking.");return;}
                queue.put(new JSONObject().put("identity",api.identity()).put("attendance_id",session).put("point",point(location)));saveQueue();
                syncInternal();
            }catch(Exception e){handleSyncError(e);}notifyUi();
        });
    }
    public void sync(){if(syncing||busy)return;syncing=true;io.execute(()->{try{syncInternal();}catch(Exception e){handleSyncError(e);}finally{syncing=false;notifyUi();}});}
    private void syncInternal() throws Exception {
        if(!api.loggedIn())return;
        if(wanted&&SystemClock.elapsedRealtime()-lastStatusElapsed>=60000)readStatus(true);
        if(wanted&&!gate.active(SystemClock.elapsedRealtime())){pause("Offline for 15 minutes. Tracking paused until you reconnect and tap Restore work tracking.");return;}
        flush();
    }
    private void handleSyncError(Exception e){
        if(e instanceof ApiClient.ApiException&&(((ApiClient.ApiException)e).status==401||((ApiClient.ApiException)e).status==403))pause("Session expired or access removed. Sign in again. Tracking paused.");
        else if(wanted&&!gate.active(SystemClock.elapsedRealtime()))pause("Unable to verify your work session for 15 minutes. Reconnect and resume tracking.");
        else message="Waiting to sync "+queued+" location point(s). "+friendly(e);
    }
    private void flush() throws Exception {
        // Bounded, chronological, per-account/session, duplicate-safe UUID batches.
        for(int batch=0;batch<20&&queue.length()>0;batch++){
            JSONObject first=queue.getJSONObject(0);
            if(!api.identity().equals(first.optString("identity"))){queue.remove(0);saveQueue();continue;}
            String session=first.getString("attendance_id");JSONArray points=new JSONArray();int count=0;
            while(count<queue.length()&&count<100){JSONObject item=queue.getJSONObject(count);if(!session.equals(item.optString("attendance_id"))||!api.identity().equals(item.optString("identity")))break;points.put(item.getJSONObject("point"));count++;}
            JSONObject body=new JSONObject().put("attendance_id",session).put("points",points);
            if(!api.vendor()){device();body.put("device_id",deviceId);}
            JSONObject result=(JSONObject)api.call("/mobile/"+api.kind()+"/locations","POST",body);
            JSONArray remaining=new JSONArray();for(int i=count;i<queue.length();i++)remaining.put(queue.get(i));queue=remaining;saveQueue();lastSent=Instant.now().toString();
            JSONObject status=result.optJSONObject("session");
            if(status!=null&&session.equals(id())&&!status.optBoolean("active")){saveAttendance(status);pause("Checkout detected. Location tracking stopped.");store.remove("resume_reminder");}
            else if(wanted)message="Work location is up to date.";
        }
    }
    public void logout(Done done){
        if(open()){if(done!=null)done.complete("Please check out and finish your workday before signing out.");return;}
        pause("Signing out");execute(()->{api.logout();WorkforceApp.push(context).signedOut();queue=new JSONArray();saveQueue();saveAttendance(new JSONObject());profile=new JSONObject();outlets=new JSONArray();store.remove("resume_reminder");serverReady=false;message="Signed out. Location tracking is off.";},done);
    }
}
