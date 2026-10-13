package in.sandssoftware.workforce;
import android.app.Application;
import android.content.Context;

public class WorkforceApp extends Application {
    private WorkController controller;
    private PushManager push;
    @Override public void onCreate(){super.onCreate();controller=new WorkController(this);push=new PushManager(this,controller);}
    public static WorkController controller(Context c){return ((WorkforceApp)c.getApplicationContext()).controller;}
    public static PushManager push(Context c){return ((WorkforceApp)c.getApplicationContext()).push;}
}
