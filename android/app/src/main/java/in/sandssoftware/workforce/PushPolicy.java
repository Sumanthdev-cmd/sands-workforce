package in.sandssoftware.workforce;

import java.util.Map;
import java.util.UUID;

/** Pure policy: delayed alerts for an old login never appear for a new account. */
public final class PushPolicy {
    private PushPolicy() {}
    public static boolean accepts(Map<String,String> data, String binding, boolean loggedIn) {
        return loggedIn && uuid(binding) && "sands.alert.v1".equals(data.get("schema"))
            && binding.equals(data.get("binding_id")) && uuid(data.get("event_id"));
    }
    public static boolean uuid(String value) {
        try { return value != null && UUID.fromString(value).toString().equals(value); }
        catch (IllegalArgumentException e) { return false; }
    }
    public static String route(String value, boolean vendor) {
        if (vendor) return "/vendor";
        if (value != null && value.length() <= 250
            && value.matches("/module/[a-z0-9-]+(?:\\?[A-Za-z0-9_=&.-]+)?")
            && !value.contains("..")) return value;
        return "/module/notifications";
    }
}
