package in.sandssoftware.workforce;

import org.json.*;
import javax.net.ssl.HttpsURLConnection;
import java.net.URL;
import java.nio.charset.StandardCharsets;
import java.io.*;
import java.util.Locale;

/** One refresh owner for native service and embedded workspace; no stored passwords. */
public final class ApiClient {
    public static final String ORIGIN = "https://app.sandssoftware.in";
    public static final String BASE = ORIGIN + "/api/v1";
    private final SecureStore store;
    private volatile JSONObject session;
    public ApiClient(SecureStore s) { store=s; session=store.object("session"); }
    public JSONObject session() { try { return new JSONObject(session.toString()); } catch (Exception e) { return new JSONObject(); } }
    public boolean loggedIn() { return !session.optString("access_token").isEmpty(); }
    public boolean vendor() { return "vendor".equals(session.optString("kind")); }
    public String kind() { return vendor()?"vendor":"employee"; }
    public String identity() { return session.optString("organization_code") + ":" + kind() + ":" + session.optString("code"); }
    private void save() { store.put("session",session.toString()); }
    public synchronized void clear() { session=new JSONObject(); store.remove("session"); }
    public synchronized void login(String org, String code, String password, boolean vendor) throws Exception {
        JSONObject body=new JSONObject().put("organization_code",org.trim().toUpperCase(Locale.ROOT))
            .put(vendor?"vendor_code":"employee_code",code.trim().toUpperCase(Locale.ROOT)).put("password",password);
        JSONObject data=(JSONObject) raw(vendor?"/vendor-portal/auth/login":"/auth/login","POST",body,"");
        data.put("kind",vendor?"vendor":"employee").put("code",code.trim().toUpperCase(Locale.ROOT)).put("organization_code",org.trim().toUpperCase(Locale.ROOT));
        session=data; save();
    }
    public synchronized Object call(String path, String method, JSONObject body) throws Exception {
        try { return raw(path,method,body,session.optString("access_token")); }
        catch (ApiException e) {
            if (e.status!=401 || vendor() || session.optString("refresh_token").isEmpty()) throw e;
            refresh();
            return raw(path,method,body,session.optString("access_token"));
        }
    }
    public synchronized JSONObject refresh() throws Exception {
        if (vendor()) return session();
        if (session.optString("refresh_token").isEmpty()) throw new ApiException(401,"Please sign in again.");
        JSONObject data=(JSONObject)raw("/auth/refresh","POST",new JSONObject().put("refresh_token",session.getString("refresh_token")),"");
        JSONObject updated=session();
        for (String key:new String[]{"access_token","refresh_token","expires_in","must_change_password"}) if(data.has(key))updated.put(key,data.get(key));
        session=updated;
        save(); return session();
    }
    public synchronized void logout() throws Exception {
        if(vendor())call("/vendor-portal/auth/logout","POST",null);
        else call("/auth/logout","POST",new JSONObject().put("refresh_token",session.optString("refresh_token")));
        clear();
    }
    private Object raw(String path,String method,JSONObject body,String token) throws Exception {
        if(!path.startsWith("/") || path.startsWith("//") || path.contains(".."))throw new IOException("Invalid API path.");
        HttpsURLConnection conn=(HttpsURLConnection)new URL(BASE+path).openConnection();
        conn.setConnectTimeout(12000); conn.setReadTimeout(18000); conn.setInstanceFollowRedirects(false);
        conn.setRequestMethod(method); conn.setRequestProperty("Accept","application/json");
        if(!token.isEmpty())conn.setRequestProperty("Authorization","Bearer "+token);
        try {
            if(body!=null){conn.setDoOutput(true);conn.setRequestProperty("Content-Type","application/json");try(OutputStream out=conn.getOutputStream()){out.write(body.toString().getBytes(StandardCharsets.UTF_8));}}
            int status=conn.getResponseCode();
            InputStream stream=status>=400?conn.getErrorStream():conn.getInputStream();
            String text="";
            if(stream!=null)try(InputStream in=stream;ByteArrayOutputStream out=new ByteArrayOutputStream()){
                byte[] bytes=new byte[8192];int n;while((n=in.read(bytes))!=-1){out.write(bytes,0,n);if(out.size()>4*1024*1024)throw new IOException("Response is too large.");}text=out.toString(StandardCharsets.UTF_8.name());
            }
            Object parsed=null;try{if(!text.trim().isEmpty())parsed=new JSONTokener(text).nextValue();}catch(Exception ignored){}
            if(status<200||status>=300)throw new ApiException(status,errorText(parsed,status));
            return parsed==JSONObject.NULL?null:parsed;
        } finally { conn.disconnect(); }
    }
    static String errorText(Object value,int status) {
        if(value instanceof JSONObject){JSONObject o=(JSONObject)value;return errorText(o.opt("detail")!=null?o.opt("detail"):o.opt("message"),status);}
        if(value instanceof JSONArray){StringBuilder b=new StringBuilder();JSONArray a=(JSONArray)value;for(int i=0;i<a.length();i++){JSONObject x=a.optJSONObject(i);if(x!=null)b.append(x.optString("msg","Invalid information")).append(". ");}if(b.length()>0)return b.toString();}
        if(value instanceof String && !((String)value).trim().isEmpty()&&!((String)value).trim().startsWith("<"))return (String)value;
        if(status==401)return "Your session expired. Sign in again.";
        if(status==404)return "This feature is not available on the server. Ask Admin to install the matching server update.";
        return "The server could not complete the request ("+status+"). Please try again.";
    }
    public static final class ApiException extends IOException { public final int status; public ApiException(int code,String text){super(text);status=code;} }
}
