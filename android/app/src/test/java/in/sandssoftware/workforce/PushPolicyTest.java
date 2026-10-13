package in.sandssoftware.workforce;
import org.junit.Test;
import static org.junit.Assert.*;
import java.util.*;

public class PushPolicyTest {
    final String binding="998effda-4680-40aa-ad16-d04037df857d";
    final String event="ea75cb48-d0d0-47c4-a0df-10f20b766fcb";
    Map<String,String> message(){return Map.of("schema","sands.alert.v1","binding_id",binding,"event_id",event);}
    @Test public void currentAccountCanReceive(){assertTrue(PushPolicy.accepts(message(),binding,true));}
    @Test public void loggedOutAndPreviousLoginAreRejected(){
        assertFalse(PushPolicy.accepts(message(),binding,false));
        assertFalse(PushPolicy.accepts(message(),UUID.randomUUID().toString(),true));
        assertFalse(PushPolicy.accepts(message(),"",true));
    }
    @Test public void malformedMessagesAreRejected(){
        assertFalse(PushPolicy.accepts(Map.of(),binding,true));
        assertFalse(PushPolicy.accepts(Map.of("schema","sands.alert.v1","binding_id",binding,"event_id","bad"),binding,true));
    }
    @Test public void urlsCannotEscapeFirstPartyWorkspace(){
        for(String value:List.of("https://evil.test/", "//evil.test", "/module/../login", "/module/%2f%2fevil.test", "/module/payroll\\evil"))
            assertEquals("/module/notifications",PushPolicy.route(value,false));
        assertEquals("/module/payroll?queue=1",PushPolicy.route("/module/payroll?queue=1",false));
    }
    @Test public void vendorCannotOpenEmployeeRoute(){assertEquals("/vendor",PushPolicy.route("/module/payroll",true));}
}
