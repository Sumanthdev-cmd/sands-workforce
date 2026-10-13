package in.sandssoftware.workforce;
import android.Manifest;
import android.app.*;
import android.content.*;
import android.content.pm.PackageManager;
import android.os.Build;

/** A reboot prompts the worker; it never starts location from the background. */
public class RestartReminder extends BroadcastReceiver {
    @Override public void onReceive(Context c,Intent i){
        if(i==null||(!Intent.ACTION_BOOT_COMPLETED.equals(i.getAction())&&!Intent.ACTION_MY_PACKAGE_REPLACED.equals(i.getAction())))return;
        if(!"true".equals(new SecureStore(c).get("resume_reminder","false")))return;
        if(Build.VERSION.SDK_INT>=33&&c.checkSelfPermission(Manifest.permission.POST_NOTIFICATIONS)!=PackageManager.PERMISSION_GRANTED)return;
        TrackingService.channel(c);
        PendingIntent open=PendingIntent.getActivity(c,2,new Intent(c,MainActivity.class),PendingIntent.FLAG_UPDATE_CURRENT|PendingIntent.FLAG_IMMUTABLE);
        c.getSystemService(NotificationManager.class).notify(101,new Notification.Builder(c,TrackingService.CHANNEL).setSmallIcon(R.drawable.ic_location).setContentTitle("Resume your work session")
            .setContentText("Your phone restarted. Open Workday to verify attendance and resume tracking.").setContentIntent(open).setAutoCancel(true).build());
    }
}
