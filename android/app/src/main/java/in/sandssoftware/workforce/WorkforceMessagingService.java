package in.sandssoftware.workforce;

import com.google.firebase.messaging.FirebaseMessagingService;
import com.google.firebase.messaging.RemoteMessage;

public final class WorkforceMessagingService extends FirebaseMessagingService {
    @Override public void onNewToken(String token) {WorkforceApp.push(this).tokenChanged(token);}
    @Override public void onMessageReceived(RemoteMessage message) {
        // Render immediately. No network request, check-in or location service is started.
        WorkforceApp.push(this).received(message.getData());
    }
}
