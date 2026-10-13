package in.sandssoftware.workforce;

import android.Manifest;
import android.app.*;
import android.content.*;
import android.content.pm.PackageManager;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.location.*;
import android.net.Uri;
import android.os.*;
import android.provider.Settings;
import android.text.InputType;
import android.view.*;
import android.widget.*;
import org.json.*;
import java.time.*;
import java.time.format.DateTimeFormatter;
import java.util.*;

public class MainActivity extends Activity implements WorkController.Listener {
    private WorkController work;
    private LinearLayout column;
    private TextView status,details,message,checkInTime,checkOutTime,trackingLabel;
    private Button checkIn,checkOut,resume,refresh,workspace,settingsButton;
    private Spinner shop;
    private boolean renderedLoggedIn=false, visible=false, requesting=false;
    private EditText org,code,password;
    private RadioButton vendor;
    private Runnable afterPermission;
    private LocationListener oneShot;
    private final Handler handler=new Handler(Looper.getMainLooper());
    private long outletsStamp=-1;
    private static final int BLUE=0xff245dee,INK=0xff14213b,MUTED=0xff596983;

    @Override public void onCreate(Bundle state){super.onCreate(state);work=WorkforceApp.controller(this);work.listen(this);render();if(work.api.loggedIn())work.refresh(null);openAlert(getIntent());}
    @Override protected void onResume(){super.onResume();visible=true;changed();getSystemService(NotificationManager.class).cancel(101);WorkforceApp.push(this).connect();}
    @Override protected void onNewIntent(Intent intent){super.onNewIntent(intent);setIntent(intent);openAlert(intent);}
    @Override protected void onPause(){visible=false;super.onPause();}
    @Override protected void onStop(){if(requesting)work.message="Attendance location request cancelled because Workday was closed. Return to retry; your existing work session is unchanged.";cancelLocation();super.onStop();}
    @Override protected void onDestroy(){work.unlisten(this);cancelLocation();super.onDestroy();}
    int dp(int n){return (int)(n*getResources().getDisplayMetrics().density);}
    TextView text(String value,int size,int color){TextView t=new TextView(this);t.setText(value);t.setTextSize(size);t.setTextColor(color);t.setPadding(0,dp(4),0,dp(4));return t;}
    private void render(){
        renderedLoggedIn=work.api.loggedIn();outletsStamp=-1;
        ScrollView scroll=new ScrollView(this);scroll.setFillViewport(true);scroll.setBackgroundColor(0xfff4f6fb);
        column=new LinearLayout(this);column.setOrientation(LinearLayout.VERTICAL);column.setPadding(dp(16),dp(8),dp(16),dp(20));scroll.addView(column);
        scroll.setOnApplyWindowInsetsListener((v,insets)->{v.setPadding(insets.getSystemWindowInsetLeft(),insets.getSystemWindowInsetTop(),insets.getSystemWindowInsetRight(),insets.getSystemWindowInsetBottom());return insets;});
        setContentView(scroll);
        LinearLayout header=new LinearLayout(this);header.setGravity(Gravity.CENTER_VERTICAL);
        TextView brand=text("SandS Workforce",20,BLUE);brand.setTypeface(null,Typeface.BOLD);header.addView(brand,new LinearLayout.LayoutParams(0,-2,1));
        if(renderedLoggedIn){settingsButton=actionButton("Settings",this::showWorkdaySettings,false);header.addView(settingsButton,new LinearLayout.LayoutParams(-2,-2));}
        column.addView(header);
        column.addView(text(renderedLoggedIn?"YOUR WORKDAY":"WELCOME BACK",11,MUTED));
        if(!renderedLoggedIn){loginForm();return;}
        JSONObject s=work.api.session();column.addView(text(s.optString("organization_code")+" · "+s.optString("code")+" · "+(work.api.vendor()?"Vendor":"Employee"),13,MUTED));
        LinearLayout card=new LinearLayout(this);card.setOrientation(LinearLayout.VERTICAL);card.setPadding(dp(16),dp(12),dp(16),dp(12));card.setBackground(round(Color.WHITE));
        LinearLayout.LayoutParams cardParams=new LinearLayout.LayoutParams(-1,-2);cardParams.topMargin=dp(12);cardParams.bottomMargin=dp(8);column.addView(card,cardParams);
        trackingLabel=text("Checking attendance…",13,MUTED);trackingLabel.setTypeface(null,Typeface.BOLD);card.addView(trackingLabel);
        status=text("Your workday",24,INK);status.setTypeface(null,Typeface.BOLD);card.addView(status);
        LinearLayout times=new LinearLayout(this);times.setBaselineAligned(false);
        checkInTime=metric(times,"CHECK IN");checkOutTime=metric(times,"CHECK OUT");card.addView(times);
        details=text("",13,MUTED);card.addView(details);
        message=text("",14,INK);message.setPadding(dp(12),dp(10),dp(12),dp(10));message.setBackground(round(0xffe8efff));column.addView(message);
        if(work.api.vendor()){column.addView(text("Shop / outlet",14,INK));shop=new Spinner(this);column.addView(shop,new LinearLayout.LayoutParams(-1,dp(52)));}
        else shop=null;
        checkIn=button("Check in & start work",()->permissionFlow(()->getPosition(l->work.checkIn(l,selectedShop(),this::startIfConfirmed))));
        resume=button("Restore work tracking",()->permissionFlow(()->work.resume(this::startIfConfirmed)));
        workspace=button("Open workspace",()->openWorkspace(false));
        checkOut=button("Check out & finish work",()->new AlertDialog.Builder(this).setTitle("Finish your workday?").setMessage("We will use a fresh location to save your checkout. Work tracking stops after checkout is confirmed. If checkout fails, your workday stays open and tracking continues while permissions and the work session remain valid.")
            .setPositiveButton("Check out",(d,w)->permissionFlow(()->getPosition(l->work.checkOut(l,this::showError)))).setNegativeButton("Keep working",null).show(),false);
        LinearLayout shortcuts=new LinearLayout(this);shortcuts.setBaselineAligned(false);
        refresh=actionButton("Refresh",()->work.refresh(this::showError),false);LinearLayout.LayoutParams half=new LinearLayout.LayoutParams(0,-2,1);half.topMargin=dp(8);shortcuts.addView(refresh,half);
        if(!work.api.vendor()){Button map=actionButton("Team map",()->openWorkspace(true),false);LinearLayout.LayoutParams other=new LinearLayout.LayoutParams(0,-2,1);other.topMargin=dp(8);other.leftMargin=dp(8);shortcuts.addView(map,other);}
        column.addView(shortcuts);
        column.addView(text("Location is shared with authorised managers during duty. Check out when you finish. Phone alerts and account options are in Settings.",12,MUTED));
        changed();
    }
    private void loginForm(){
        column.addView(text("Sign in to your organisation",26,INK));
        column.addView(text("Use the same account as your workforce website.",15,MUTED));
        org=field("Organisation code","SANDS",false);code=field("Employee or vendor code","",false);password=field("Password","",true);
        RadioGroup group=new RadioGroup(this);group.setOrientation(RadioGroup.HORIZONTAL);
        RadioButton employee=new RadioButton(this);employee.setText("Employee");employee.setId(View.generateViewId());vendor=new RadioButton(this);vendor.setText("Vendor");vendor.setId(View.generateViewId());group.addView(employee);group.addView(vendor);group.check(employee.getId());column.addView(group);
        message=text(work.message,14,MUTED);column.addView(message);
        button("Sign in",()->{String o=org.getText().toString().trim(),c=code.getText().toString().trim(),p=password.getText().toString();if(o.isEmpty()||c.isEmpty()||p.isEmpty()){showError("Enter organisation code, your login code and password.");return;}work.login(o,c,p,vendor.isChecked(),error->{password.setText("");if(work.api.loggedIn())render();showError(error);});});
        column.addView(text("Your password is sent over HTTPS and is not saved on the phone. Location permission is requested when you start a work session.",14,MUTED));
    }
    EditText field(String label,String initial,boolean secret){column.addView(text(label,14,INK));EditText e=new EditText(this);e.setSingleLine(true);e.setText(initial);e.setTextSize(16);e.setInputType(secret?InputType.TYPE_CLASS_TEXT|InputType.TYPE_TEXT_VARIATION_PASSWORD:InputType.TYPE_CLASS_TEXT);e.setPadding(dp(14),0,dp(14),0);e.setBackground(round(Color.WHITE));LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(-1,dp(54));p.bottomMargin=dp(12);column.addView(e,p);return e;}
    Button button(String label,Runnable click){return button(label,click,true);}
    Button button(String label,Runnable click,boolean primary){Button b=actionButton(label,click,primary);LinearLayout.LayoutParams p=new LinearLayout.LayoutParams(-1,-2);p.topMargin=dp(8);column.addView(b,p);return b;}
    Button actionButton(String label,Runnable click,boolean primary){Button b=new Button(this);b.setText(label);b.setAllCaps(false);b.setTextSize(15);b.setTextColor(primary?Color.WHITE:BLUE);b.setMinHeight(dp(48));b.setMinimumHeight(dp(48));b.setPadding(dp(12),dp(12),dp(12),dp(12));b.setBackground(round(primary?BLUE:0xffe8efff));b.setStateListAnimator(null);b.setOnClickListener(v->{if(work.busy||requesting){showError("Please wait for the current action.");return;}click.run();});return b;}
    TextView metric(LinearLayout row,String label){LinearLayout cell=new LinearLayout(this);cell.setOrientation(LinearLayout.VERTICAL);cell.setPadding(0,dp(8),dp(8),dp(8));cell.addView(text(label,10,MUTED));TextView value=text("—",15,INK);value.setTypeface(null,Typeface.BOLD);cell.addView(value);row.addView(cell,new LinearLayout.LayoutParams(0,-2,1));return value;}
    GradientDrawable round(int color){GradientDrawable d=new GradientDrawable();d.setColor(color);d.setCornerRadius(dp(12));return d;}
    private String selectedShop(){int i=shop==null?-1:shop.getSelectedItemPosition();JSONObject o=work.outlets.optJSONObject(i);return o==null?"":o.optString("id");}
    static String time(String value){long m=WorkController.millis(value);return m==0?"—":Instant.ofEpochMilli(m).atZone(ZoneId.systemDefault()).format(DateTimeFormatter.ofPattern("dd MMM, h:mm a"));}
    @Override public void changed(){
        if(isDestroyed())return;
        if(renderedLoggedIn!=work.api.loggedIn()){render();return;}
        if(message!=null)message.setText(work.busy?"Working… "+work.message:work.message);
        if(!renderedLoggedIn)return;
        boolean open=work.open(),tracking=work.tracking();status.setText(open?"You're checked in":"You're off duty");
        trackingLabel.setText(tracking?"● Tracking active":open?"Tracking needs attention":"Tracking off");trackingLabel.setTextColor(tracking?0xff067647:open?0xff934f00:MUTED);
        checkInTime.setText(time(work.attendance.optString("check_in_at")));checkOutTime.setText(time(work.attendance.optString("check_out_at")));
        details.setText("Last location  "+time(work.lastFix)+"\nLast sync  "+time(work.lastSent)+(work.queued>0?" · "+work.queued+" waiting":""));
        checkIn.setVisibility(open?View.GONE:View.VISIBLE);checkOut.setVisibility(open?View.VISIBLE:View.GONE);resume.setVisibility(open&&!tracking?View.VISIBLE:View.GONE);
        // Keep the action available after a failed server probe so a retry can
        // explain the actual problem instead of leaving a silent disabled button.
        boolean ready=!work.busy&&!requesting&&!work.passwordChange;
        checkIn.setEnabled(ready&&(!work.api.vendor()||work.outlets.length()>0));checkOut.setEnabled(ready);resume.setEnabled(ready);refresh.setEnabled(ready);workspace.setEnabled(!work.busy&&!requesting);settingsButton.setEnabled(!work.busy&&!requesting);
        if(shop!=null&&outletsStamp!=System.identityHashCode(work.outlets)){
            ArrayList<String> names=new ArrayList<>();for(int i=0;i<work.outlets.length();i++){JSONObject o=work.outlets.optJSONObject(i);if(o!=null)names.add(o.optString("code")+" · "+o.optString("name"));}
            shop.setAdapter(new ArrayAdapter<>(this,android.R.layout.simple_spinner_dropdown_item,names));outletsStamp=System.identityHashCode(work.outlets);
            checkIn.setEnabled(ready&&!names.isEmpty());
        }
    }
    private void permissionFlow(Runnable action){
        String key="consent:"+work.api.identity();
        if(!"v2".equals(work.store.get(key,""))){
            new AlertDialog.Builder(this).setTitle("Share location during duty?").setMessage("SandS Workforce collects your precise location about every 30 seconds after check-in, including while the screen is locked or another app is open. It sends the locations to your organisation's authorised managers for attendance and the live work map. There is no in-app Pause option during duty. Tracking stops when checkout is confirmed. Enable notifications to see the ongoing tracking notice. During short network outages, work locations are stored encrypted on this phone and sent later. Android permission and stop controls remain available. Tracking may stop if permission, access or work-session verification is lost.")
                .setPositiveButton("Agree & continue",(d,w)->{work.store.put(key,"v2");requestPermissionsFor(action);}).setNegativeButton("Not now",null).show();
        }else requestPermissionsFor(action);
    }
    private void requestPermissionsFor(Runnable action){
        ArrayList<String> missing=new ArrayList<>();
        if(checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION)!=PackageManager.PERMISSION_GRANTED){missing.add(Manifest.permission.ACCESS_FINE_LOCATION);missing.add(Manifest.permission.ACCESS_COARSE_LOCATION);}
        if(!missing.isEmpty()){afterPermission=action;requestPermissions(missing.toArray(new String[0]),10);return;}
        LocationManager lm=(LocationManager)getSystemService(LOCATION_SERVICE);
        if(lm.getProviders(true).isEmpty()){new AlertDialog.Builder(this).setTitle("Turn on device location").setMessage("Enable location, then return and try again.").setPositiveButton("Settings",(d,w)->startActivity(new Intent(Settings.ACTION_LOCATION_SOURCE_SETTINGS))).setNegativeButton("Cancel",null).show();return;}
        action.run();
    }
    @Override public void onRequestPermissionsResult(int request,String[] permissions,int[] results){super.onRequestPermissionsResult(request,permissions,results);if(request==11){WorkforceApp.push(this).connect();changed();return;}if(request!=10)return;Runnable action=afterPermission;afterPermission=null;boolean allowed=checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION)==PackageManager.PERMISSION_GRANTED;WorkforceApp.push(this).connect();if(allowed&&action!=null)requestPermissionsFor(action);else new AlertDialog.Builder(this).setTitle("Precise location needed").setMessage("Allow Location while using the app and turn on Precise location. Then return to Workday and retry check-in.").setPositiveButton("App settings",(d,w)->startActivity(new Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS,Uri.parse("package:"+getPackageName())))).setNegativeButton("Close",null).show();}
    interface PositionReady{void ready(Location l);}
    private void getPosition(PositionReady done){
        if(work.api.vendor()&&!work.open()&&selectedShop().isEmpty()){showError("No shop is assigned to this vendor. Ask Admin to assign the shop first.");return;}
        requesting=true;work.message="Getting a fresh GPS position…";changed();
        LocationManager lm=(LocationManager)getSystemService(LOCATION_SERVICE);
        oneShot=new LocationListener(){public void onLocationChanged(Location l){if(!requesting)return;if(l.isFromMockProvider()||!l.hasAccuracy()||l.getAccuracy()>100||Math.abs(System.currentTimeMillis()-l.getTime())>30000)return;cancelLocation();done.ready(l);}public void onProviderEnabled(String p){}public void onProviderDisabled(String p){}public void onStatusChanged(String p,int s,Bundle b){}};
        try{boolean provider=false;for(String name:new String[]{LocationManager.GPS_PROVIDER,LocationManager.NETWORK_PROVIDER,"fused"})if(lm.getAllProviders().contains(name)&&lm.isProviderEnabled(name)){lm.requestLocationUpdates(name,1000,0,oneShot,Looper.getMainLooper());provider=true;}if(!provider){cancelLocation();work.message="Turn on device location, then retry check-in.";changed();showError(work.message);return;}}
        catch(SecurityException e){cancelLocation();showError("Location permission was removed. Allow precise location and retry.");return;}
        handler.postDelayed(()->{if(requesting){cancelLocation();work.message="GPS timed out. Move near a window or outside, keep location on, and retry.";changed();showError(work.message);}},45000);
    }
    private void cancelLocation(){if(oneShot!=null){try{((LocationManager)getSystemService(LOCATION_SERVICE)).removeUpdates(oneShot);}catch(SecurityException ignored){}oneShot=null;}requesting=false;handler.removeCallbacksAndMessages(null);}
    private void startIfConfirmed(String error){
        if(error!=null){showError(error);return;}
        if(!visible){work.pause("Check-in is saved. Reopen Workday and tap Restore work tracking.");return;}
        try{startForegroundService(new Intent(this,TrackingService.class));work.message="Work location tracking started. You may lock your screen.";changed();}catch(Exception e){work.pause("Could not start tracking. Keep this screen open and tap Restore work tracking.");showError(work.message);}
    }
    private void openWorkspace(boolean map){if(!work.api.loggedIn())return;startActivity(new Intent(this,WorkspaceActivity.class).putExtra("map",map));}
    private void openAlert(Intent intent){
        String binding=intent.getStringExtra("push_binding");
        if(binding==null)return;
        String route=intent.getStringExtra("push_route");
        intent.removeExtra("push_binding");intent.removeExtra("push_route");
        if(!WorkforceApp.push(this).currentBinding(binding))return;
        startActivity(new Intent(this,WorkspaceActivity.class).putExtra("push_binding",binding)
            .putExtra("route",PushPolicy.route(route,work.api.vendor())));
    }
    private void notificationSettings(){
        PushManager push=WorkforceApp.push(this);
        if(!push.configured()){showError(push.status());return;}
        if(Build.VERSION.SDK_INT>=33&&checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)!=PackageManager.PERMISSION_GRANTED
            &&!"yes".equals(work.store.get("push_permission_asked",""))){
            new AlertDialog.Builder(this).setTitle("Allow workforce alerts?")
                .setMessage("Get approval, task and other alerts on your phone while the workspace is closed. This does not start location tracking.")
                .setPositiveButton("Enable alerts",(d,w)->{work.store.put("push_permission_asked","yes");requestPermissions(new String[]{Manifest.permission.POST_NOTIFICATIONS},11);})
                .setNegativeButton("Not now",null).show();return;
        }
        push.connect();
        new AlertDialog.Builder(this).setTitle("Workforce phone alerts").setMessage(push.status()+"\n\nSound, vibration and lock-screen visibility follow your Android notification settings. Internet and Google Play services are required. Reopen the app after force-stopping it.")
            .setPositiveButton("Android settings",(d,w)->startActivity(new Intent(Settings.ACTION_APP_NOTIFICATION_SETTINGS).putExtra(Settings.EXTRA_APP_PACKAGE,getPackageName())))
            .setNegativeButton("Close",null).show();
    }
    private void showWorkdaySettings(){
        ArrayList<String> labels=new ArrayList<>();ArrayList<Runnable> actions=new ArrayList<>();
        labels.add("Phone notifications");actions.add(this::notificationSettings);
        labels.add("Send test notification");actions.add(()->WorkforceApp.push(this).sendTest(this::showError));
        if(!work.api.vendor()){labels.add("Check account setup");actions.add(()->work.accountSetup(error->{showError(error==null?work.message:error);}));}
        labels.add("Location & battery settings");actions.add(this::showSettings);
        labels.add("Change password");actions.add(this::changePassword);
        if(!work.tracking()){
            labels.add("Reconnect account");actions.add(()->{EditText p=new EditText(this);p.setInputType(129);p.setHint("Password for "+work.api.session().optString("code"));new AlertDialog.Builder(this).setTitle("Reconnect this account").setView(p).setPositiveButton("Sign in",(d,w)->work.reauthenticate(p.getText().toString(),this::showError)).setNegativeButton("Cancel",null).show();});
        }
        labels.add("Sign out");actions.add(()->work.logout(error->{showError(error);if(error==null)render();}));
        labels.add("About this app");actions.add(()->new AlertDialog.Builder(this).setTitle("SandS Workforce").setMessage("Version "+BuildConfig.VERSION_NAME+"\n\n"+WorkforceApp.push(this).status()+"\n\nLocation is collected during a verified work session. Checkout ends tracking. Android can stop the app or remove location access; return to Workday to restore tracking if interrupted.").setPositiveButton("Close",null).show());
        new AlertDialog.Builder(this).setTitle("Settings").setItems(labels.toArray(new String[0]),(d,which)->actions.get(which).run()).setNegativeButton("Close",null).show();
    }
    void showError(String error){if(error!=null&&visible&&!isFinishing())new AlertDialog.Builder(this).setTitle("Workday update").setMessage(error).setPositiveButton("OK",null).show();}
    private void changePassword(){LinearLayout form=new LinearLayout(this);form.setOrientation(LinearLayout.VERTICAL);form.setPadding(dp(22),0,dp(22),0);EditText old=new EditText(this),next=new EditText(this);old.setHint("Current password");next.setHint("New password (10+ characters)");old.setInputType(129);next.setInputType(129);form.addView(old);form.addView(next);new AlertDialog.Builder(this).setTitle("Change password").setView(form).setPositiveButton("Save",(d,w)->work.changePassword(old.getText().toString(),next.getText().toString(),error->{showError(error);work.refresh(null);})).setNegativeButton("Cancel",null).show();}
    private void showSettings(){new AlertDialog.Builder(this).setTitle("Reliable work tracking").setMessage("Allow precise location and notifications. If your phone restricts background activity, choose Unrestricted battery use for SandS Workforce. Keep mobile data and GPS on. After rebooting or force-stopping the app, reopen Workday and resume. Tracking pauses after 15 minutes without server verification, or after a 24-hour open session.")
        .setPositiveButton("App settings",(d,w)->startActivity(new Intent(Settings.ACTION_APPLICATION_DETAILS_SETTINGS,Uri.parse("package:"+getPackageName())))).setNeutralButton("Battery settings",(d,w)->startActivity(new Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS))).setNegativeButton("Close",null).show();}
}
