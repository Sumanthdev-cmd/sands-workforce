package in.sandssoftware.workforce;

import android.Manifest;
import android.app.*;
import android.content.*;
import android.content.pm.PackageManager;
import android.content.pm.ServiceInfo;
import android.location.*;
import android.os.*;

/** A user-visible, location-type foreground service, started only from visible UI. */
public class TrackingService extends Service implements LocationListener {
    static final String CHANNEL="work_location";
    private static final int ID=100;
    private LocationManager locations;
    private WorkController controller;
    private final Handler handler=new Handler(Looper.getMainLooper());
    private final Runnable heartbeat=new Runnable(){public void run(){
        if(!controller.tracking()){controller.pause("Tracking interrupted. Open Workday to refresh and restore work tracking.");stopSelf();return;}
        controller.sync();
        getSystemService(NotificationManager.class).notify(ID,notification(controller.queued>0?"Working · "+controller.queued+" location point(s) waiting to sync":"Working · location updates about every 30 seconds"));
        handler.postDelayed(this,10000);
    }};
    public static void channel(Context context){
        NotificationChannel channel=new NotificationChannel(CHANNEL,"Work location tracking",NotificationManager.IMPORTANCE_LOW);
        channel.setDescription("Visible while your checked-in work session is tracked.");channel.setShowBadge(false);
        context.getSystemService(NotificationManager.class).createNotificationChannel(channel);
    }
    @Override public void onCreate(){super.onCreate();controller=WorkforceApp.controller(this);locations=(LocationManager)getSystemService(LOCATION_SERVICE);channel(this);}
    private Notification notification(String message){
        PendingIntent open=PendingIntent.getActivity(this,0,new Intent(this,MainActivity.class),PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE);
        return new Notification.Builder(this,CHANNEL).setSmallIcon(R.drawable.ic_location).setContentTitle("Work location tracking").setContentText(message).setContentIntent(open)
            .setOngoing(true).setOnlyAlertOnce(true).setCategory(Notification.CATEGORY_SERVICE)
            .addAction(new Notification.Action.Builder(null,"Open Workday",open).build()).build();
    }
    @Override public int onStartCommand(Intent intent,int flags,int startId){
        if(!controller.tracking()){stopSelf();return START_NOT_STICKY;}
        try{
            if(Build.VERSION.SDK_INT>=29)startForeground(ID,notification("Tracking your checked-in work session"),ServiceInfo.FOREGROUND_SERVICE_TYPE_LOCATION);
            else startForeground(ID,notification("Tracking your checked-in work session"));
            if(checkSelfPermission(Manifest.permission.ACCESS_FINE_LOCATION)!=PackageManager.PERMISSION_GRANTED)throw new SecurityException("Precise location permission is required.");
            locations.removeUpdates(this);
            if(locations.getAllProviders().contains(LocationManager.GPS_PROVIDER))locations.requestLocationUpdates(LocationManager.GPS_PROVIDER,30000,0,this,Looper.getMainLooper());
            if(locations.getAllProviders().contains(LocationManager.NETWORK_PROVIDER))locations.requestLocationUpdates(LocationManager.NETWORK_PROVIDER,30000,0,this,Looper.getMainLooper());
            handler.removeCallbacks(heartbeat);handler.post(heartbeat);
        }catch(Exception e){controller.pause("Tracking could not start. Allow precise location and open the app to resume.");stopSelf();}
        return START_NOT_STICKY; // Never silently restart location after a force stop/process death.
    }
    @Override public void onLocationChanged(Location location){controller.captured(location);}
    @Override public void onProviderDisabled(String provider){controller.message="Device location is disabled or unavailable. Turn it on to continue tracking.";controller.notifyUi();}
    @Override public void onProviderEnabled(String provider){controller.message="Location is enabled. Waiting for a fresh position.";controller.notifyUi();}
    @Override public void onStatusChanged(String provider,int status,Bundle extras){}
    @Override public void onDestroy(){handler.removeCallbacksAndMessages(null);if(locations!=null)locations.removeUpdates(this);stopForeground(STOP_FOREGROUND_REMOVE);if(controller!=null&&controller.wanted)controller.pause("Android stopped tracking. Open Workday and tap Restore work tracking.");super.onDestroy();}
    @Override public IBinder onBind(Intent intent){return null;}
}
