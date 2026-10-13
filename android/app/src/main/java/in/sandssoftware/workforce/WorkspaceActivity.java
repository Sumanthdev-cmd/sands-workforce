package in.sandssoftware.workforce;

import android.annotation.SuppressLint;
import android.app.*;
import android.content.*;
import android.graphics.Color;
import android.graphics.Typeface;
import android.graphics.drawable.GradientDrawable;
import android.net.Uri;
import android.net.http.SslError;
import android.os.*;
import android.print.PrintManager;
import android.view.*;
import android.webkit.*;
import android.widget.*;
import androidx.webkit.*;
import org.json.*;
import java.io.*;
import java.util.*;

/** Existing cloud workspace, with only the exact first-party origin granted a bridge. */
public class WorkspaceActivity extends Activity {
    private WebView web;
    private TextView status;
    private WorkController work;
    private ValueCallback<Uri[]> files;
    private boolean map,pageLoadError;
    private String identity;
    private final Handler handler=new Handler(Looper.getMainLooper());
    private final Runnable mapRefresh=new Runnable(){public void run(){if(map&&!isFinishing()){loadMap();handler.postDelayed(this,60000);}}};

    @SuppressLint("SetJavaScriptEnabled")
    @Override public void onCreate(Bundle state){
        super.onCreate(state);work=WorkforceApp.controller(this);identity=work.api.identity();map=getIntent().getBooleanExtra("map",false);
        if(Build.VERSION.SDK_INT>=33)getOnBackInvokedDispatcher().registerOnBackInvokedCallback(android.window.OnBackInvokedDispatcher.PRIORITY_DEFAULT,this::goBack);
        if(!work.api.loggedIn()){finish();return;}
        String alertBinding=getIntent().getStringExtra("push_binding");
        if(alertBinding!=null&&!WorkforceApp.push(this).currentBinding(alertBinding)){finish();return;}
        LinearLayout frame=new LinearLayout(this);frame.setOrientation(LinearLayout.VERTICAL);frame.setBackgroundColor(0xfff4f6fb);
        frame.setOnApplyWindowInsetsListener((v,i)->{v.setPadding(i.getSystemWindowInsetLeft(),i.getSystemWindowInsetTop(),i.getSystemWindowInsetRight(),i.getSystemWindowInsetBottom());return i;});
        LinearLayout toolbar=new LinearLayout(this);toolbar.setGravity(Gravity.CENTER_VERTICAL);toolbar.setPadding(dp(8),dp(4),dp(8),dp(4));toolbar.setBackgroundColor(Color.WHITE);
        Button back=toolbarButton("‹ Workday");back.setOnClickListener(v->finish());toolbar.addView(back,new LinearLayout.LayoutParams(-2,-2));
        TextView title=new TextView(this);title.setText(map?"Team map":"Workspace");title.setTextSize(14);title.setTextColor(0xff596983);title.setGravity(Gravity.CENTER);title.setTypeface(null,Typeface.BOLD);toolbar.addView(title,new LinearLayout.LayoutParams(0,-2,1));
        Button reload=toolbarButton("Refresh");reload.setOnClickListener(v->{setStatus("Refreshing…");if(map)loadMap();else web.reload();});toolbar.addView(reload,new LinearLayout.LayoutParams(-2,-2));frame.addView(toolbar);
        status=new TextView(this);setStatus("Opening secure workspace…");status.setTextSize(13);status.setTextColor(0xff596983);status.setPadding(dp(12),dp(6),dp(12),dp(6));frame.addView(status);
        web=new WebView(this);frame.addView(web,new LinearLayout.LayoutParams(-1,0,1));setContentView(frame);
        WebSettings s=web.getSettings();s.setJavaScriptEnabled(true);s.setDomStorageEnabled(true);s.setAllowFileAccess(false);s.setAllowContentAccess(false);s.setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);s.setSupportMultipleWindows(true);s.setUseWideViewPort(true);s.setLoadWithOverviewMode(true);
        CookieManager.getInstance().setAcceptThirdPartyCookies(web,false);WebView.setWebContentsDebuggingEnabled(false);
        WebViewAssetLoader assets=new WebViewAssetLoader.Builder().addPathHandler("/assets/",new WebViewAssetLoader.AssetsPathHandler(this)).build();
        web.setWebViewClient(new WebViewClient(){
            @Override public void onPageStarted(WebView view,String url,android.graphics.Bitmap icon){pageLoadError=false;setStatus("Loading workspace…");}
            @Override public boolean shouldOverrideUrlLoading(WebView view,WebResourceRequest req){
                if(!req.isForMainFrame())return false;
                Uri uri=req.getUrl();
                if(trusted(uri)){return false;}
                if(map&&"appassets.androidplatform.net".equals(uri.getHost())&&"https".equals(uri.getScheme()))return false;
                external(uri);return true;
            }
            @Override public WebResourceResponse shouldInterceptRequest(WebView view,WebResourceRequest req){
                if(map)return assets.shouldInterceptRequest(req.getUrl());
                Uri u=req.getUrl();String p=u.getPath()==null?"":u.getPath();
                if(trusted(u)&&("/api/v1/auth/refresh".equals(p)||blockedAttendance(p))){
                    return new WebResourceResponse("application/json","UTF-8",409,"Use Workday",Collections.emptyMap(),new ByteArrayInputStream("{\"detail\":\"Use the Android Workday screen for attendance.\"}".getBytes()));
                }
                return null;
            }
            @Override public void onPageFinished(WebView view,String url){if(pageLoadError)return;if(map)setStatus("Organisation map · refreshes every minute");else status.setVisibility(View.GONE);}
            @Override public void onReceivedSslError(WebView view,SslErrorHandler h,SslError error){h.cancel();pageLoadError=true;setStatus("Cannot verify this website's HTTPS certificate. Connection blocked.");}
            @Override public void onReceivedError(WebView view,WebResourceRequest r,WebResourceError e){if(r.isForMainFrame()){pageLoadError=true;setStatus("Unable to load the page. Check your connection and tap Refresh.");}}
        });
        web.setWebChromeClient(new WebChromeClient(){
            @Override public boolean onShowFileChooser(WebView w,ValueCallback<Uri[]> callback,FileChooserParams p){
                if(files!=null)files.onReceiveValue(null);files=callback;
                Intent choose=new Intent(Intent.ACTION_OPEN_DOCUMENT).addCategory(Intent.CATEGORY_OPENABLE).setType("*/*");choose.putExtra(Intent.EXTRA_ALLOW_MULTIPLE,p.getMode()==FileChooserParams.MODE_OPEN_MULTIPLE);
                try{startActivityForResult(choose,40);return true;}catch(ActivityNotFoundException e){files=null;return false;}
            }
            @Override public void onGeolocationPermissionsShowPrompt(String origin,GeolocationPermissions.Callback callback){
                if(!trusted(Uri.parse(origin))||!work.tracking()){callback.invoke(origin,false,false);setStatus("Use Workday to check in and enable work location first.");return;}
                callback.invoke(origin,true,false);
            }
            @Override public boolean onCreateWindow(WebView parent,boolean dialog,boolean userGesture,Message result){
                if(!userGesture)return false;
                WebView child=new WebView(WorkspaceActivity.this);child.getSettings().setJavaScriptEnabled(true);child.getSettings().setAllowFileAccess(false);child.getSettings().setMixedContentMode(WebSettings.MIXED_CONTENT_NEVER_ALLOW);
                child.setWebViewClient(new WebViewClient(){@Override public boolean shouldOverrideUrlLoading(WebView v,WebResourceRequest r){if(r.isForMainFrame()&&"https".equals(r.getUrl().getScheme())){external(r.getUrl());return true;}return false;}@Override public void onReceivedSslError(WebView v,SslErrorHandler h,SslError e){h.cancel();}});
                AlertDialog preview=new AlertDialog.Builder(WorkspaceActivity.this).setTitle("Document preview").setView(child).setPositiveButton("Close",null).setNeutralButton("Print / PDF",(d,w)->print(child)).create();preview.setOnDismissListener(d->child.destroy());preview.show();preview.getWindow().setLayout(-1,-1);
                ((WebView.WebViewTransport)result.obj).setWebView(child);result.sendToTarget();return true;
            }
        });
        web.setDownloadListener((url,agent,disposition,type,length)->{
            if(url.startsWith("https://"))external(Uri.parse(url));
            else setStatus("For this generated download, use Print / PDF or open the website in your browser.");
        });
        if(map){web.loadUrl("https://appassets.androidplatform.net/assets/map.html");handler.postDelayed(mapRefresh,1200);return;}
        if(!WebViewFeature.isFeatureSupported(WebViewFeature.WEB_MESSAGE_LISTENER)||!WebViewFeature.isFeatureSupported(WebViewFeature.DOCUMENT_START_SCRIPT)){
            setStatus("Update Android System WebView / Chrome to open the embedded workspace. Native work tracking is still available.");return;
        }
        WebViewCompat.addWebMessageListener(web,"WorkforceNative",Collections.singleton(ApiClient.ORIGIN),(view,m,origin,isMain,reply)->{
            if(!isMain||!trusted(origin)||!identity.equals(work.api.identity()))return;
            try{
                JSONObject req=new JSONObject(m.getData());String action=req.optString("action"),id=req.optString("id");
                if("workday".equals(action)){finish();return;}
                if("print".equals(action)){print(web);return;}
                if("logout".equals(action)){work.logout(error->{reply(reply,id,null,error);if(error!=null){work.message=error;work.notifyUi();}finish();});return;}
                if("refresh".equals(action))work.io.execute(()->{
                    try{JSONObject tokens=work.api.refresh();runOnUiThread(()->{if(identity.equals(work.api.identity()))reply(reply,id,tokens,null);});}
                    catch(Exception e){runOnUiThread(()->reply(reply,id,null,WorkController.friendly(e)));}
                });
            }catch(Exception ignored){setStatus("Workspace request was not understood. Please refresh.");}
        });
        WebViewCompat.addDocumentStartJavaScript(web,bridgeScript(work.api.session(),work.api.vendor()),Collections.singleton(ApiClient.ORIGIN));
        String route=getIntent().getStringExtra("route");
        web.loadUrl(ApiClient.ORIGIN+(route==null?(work.api.vendor()?"/vendor":"/dashboard"):PushPolicy.route(route,work.api.vendor())));
    }
    int dp(int value){return (int)(value*getResources().getDisplayMetrics().density);}
    Button toolbarButton(String label){Button b=new Button(this);b.setText(label);b.setAllCaps(false);b.setTextSize(14);b.setTextColor(0xff245dee);b.setMinHeight(dp(48));b.setMinimumHeight(dp(48));b.setPadding(dp(8),dp(8),dp(8),dp(8));GradientDrawable bg=new GradientDrawable();bg.setColor(0xffe8efff);bg.setCornerRadius(dp(10));b.setBackground(bg);b.setStateListAnimator(null);return b;}
    void setStatus(String message){status.setText(message);status.setVisibility(View.VISIBLE);}
    static boolean trusted(Uri uri){return "https".equals(uri.getScheme())&&"app.sandssoftware.in".equals(uri.getHost())&&(uri.getPort()==-1||uri.getPort()==443)&&uri.getUserInfo()==null;}
    static boolean blockedAttendance(String p){return p.equals("/api/v1/auth/login")||p.equals("/api/v1/vendor-portal/auth/login")||p.equals("/api/v1/attendance/check-in")||p.equals("/api/v1/attendance/check-out")||p.equals("/api/v1/attendance/auto-evaluate")||p.equals("/api/v1/vendor-portal/attendance/check-in")||p.equals("/api/v1/vendor-portal/attendance/check-out");}
    void reply(JavaScriptReplyProxy p,String id,JSONObject data,String error){if(isDestroyed())return;try{p.postMessage(new JSONObject().put("id",id).put("data",data==null?JSONObject.NULL:data).put("error",error==null?JSONObject.NULL:error).toString());}catch(Exception ignored){}}
    static String bridgeScript(JSONObject tokens,boolean vendor){
        String setup=vendor?"localStorage.removeItem('sands_access_token');localStorage.removeItem('sands_refresh_token');localStorage.setItem('sands_vendor_access_token',t.access_token);":"localStorage.removeItem('sands_vendor_access_token');localStorage.setItem('sands_access_token',t.access_token);localStorage.setItem('sands_refresh_token',t.refresh_token||'');";
        return "(()=>{if(window!==top||location.origin!=="+JSONObject.quote(ApiClient.ORIGIN)+")return;const t="+tokens+";"+setup+
            "const pending=new Map();let next=0;function call(action){return new Promise((resolve,reject)=>{const id=String(++next);const timer=setTimeout(()=>{pending.delete(id);reject(new Error('Android request timed out. Return to Workday and retry.'));},40000);pending.set(id,{resolve,reject,timer});WorkforceNative.postMessage(JSON.stringify({id,action}));});}WorkforceNative.onmessage=e=>{const m=JSON.parse(e.data),p=pending.get(m.id);if(!p)return;clearTimeout(p.timer);pending.delete(m.id);m.error?p.reject(new Error(m.error)):p.resolve(m.data);};"+
            "const original=window.fetch.bind(window);window.fetch=async(input,init)=>{const r=new Request(input,init),u=new URL(r.url);if(u.origin===location.origin){if(u.pathname==='/api/v1/auth/refresh'){const result=await call('refresh');return new Response(JSON.stringify(result),{status:200,headers:{'Content-Type':'application/json'}});}if(['/api/v1/auth/logout','/api/v1/vendor-portal/auth/logout'].includes(u.pathname)){await call('logout');return new Response(null,{status:204});}if(['/api/v1/auth/login','/api/v1/vendor-portal/auth/login','/api/v1/attendance/check-in','/api/v1/attendance/check-out','/api/v1/attendance/auto-evaluate','/api/v1/vendor-portal/attendance/check-in','/api/v1/vendor-portal/attendance/check-out'].includes(u.pathname)){WorkforceNative.postMessage(JSON.stringify({id:'workday',action:'workday'}));throw new Error('Use the Android Workday screen for sign-in and attendance.');}}return original(r);};window.print=()=>WorkforceNative.postMessage(JSON.stringify({id:'print',action:'print'}));})();";
    }
    void loadMap(){work.io.execute(()->{try{Object rows=work.api.call("/mobile/live","GET",null);String json=JSONObject.quote(rows.toString());runOnUiThread(()->{if(!isDestroyed())web.evaluateJavascript("window.showPeople&&window.showPeople(JSON.parse("+json+"))",null);});}catch(Exception e){runOnUiThread(()->setStatus(WorkController.friendly(e)));}});}
    void external(Uri uri){if(!"https".equals(uri.getScheme())){setStatus("Only secure HTTPS links can be opened.");return;}try{startActivity(new Intent(Intent.ACTION_VIEW,uri).addCategory(Intent.CATEGORY_BROWSABLE));}catch(ActivityNotFoundException e){setStatus("No browser is installed to open this link.");}}
    void print(WebView view){((PrintManager)getSystemService(PRINT_SERVICE)).print("Workforce document",view.createPrintDocumentAdapter("Workforce document"),null);}
    @Override protected void onResume(){super.onResume();if(work!=null&&!identity.equals(work.api.identity()))finish();}
    @Override protected void onActivityResult(int request,int result,Intent data){super.onActivityResult(request,result,data);if(request!=40||files==null)return;ArrayList<Uri> selected=new ArrayList<>();if(result==RESULT_OK&&data!=null){if(data.getClipData()!=null){for(int i=0;i<data.getClipData().getItemCount();i++)selected.add(data.getClipData().getItemAt(i).getUri());}else if(data.getData()!=null)selected.add(data.getData());}files.onReceiveValue(selected.isEmpty()?null:selected.toArray(new Uri[0]));files=null;}
    private void goBack(){if(web!=null&&web.canGoBack())web.goBack();else finish();}
    // API 33+ uses the platform predictive-back callback registered above.
    @SuppressLint("GestureBackNavigation")
    @Override public void onBackPressed(){goBack();}
    @Override protected void onDestroy(){handler.removeCallbacksAndMessages(null);if(files!=null)files.onReceiveValue(null);if(web!=null){web.stopLoading();web.destroy();}super.onDestroy();}
}
