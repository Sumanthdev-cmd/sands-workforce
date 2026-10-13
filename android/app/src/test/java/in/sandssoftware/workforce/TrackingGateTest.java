package in.sandssoftware.workforce;
import org.junit.Test;
import static org.junit.Assert.*;

public class TrackingGateTest {
    private final long wall=1800000000000L,elapsed=90000000L;
    @Test public void neverCollectsBeforeConfirmedCheckIn(){TrackingGate g=new TrackingGate();assertFalse(g.allows("shift",wall,elapsed));}
    @Test public void confirmedShiftOnlyAllowsOwnSessionAndWindow(){TrackingGate g=new TrackingGate();g.confirm("shift",wall,wall+3600000,wall,elapsed);assertTrue(g.allows("shift",wall+30000,elapsed+30000));assertFalse(g.allows("other",wall+30000,elapsed+30000));assertFalse(g.allows("shift",wall-1,elapsed+30000));assertFalse(g.allows("shift",wall+3600001,elapsed+30000));}
    @Test public void checkoutRejectsAlreadyQueuedCallback(){TrackingGate g=new TrackingGate();g.confirm("shift",wall,wall+3600000,wall,elapsed);g.stop();assertFalse(g.allows("shift",wall+1,elapsed+1));}
    @Test public void offlineLeaseExpiresEvenIfWallClockChanges(){TrackingGate g=new TrackingGate();g.confirm("shift",wall,wall+3600000,wall,elapsed);assertFalse(g.allows("shift",wall+30,elapsed+TrackingGate.LEASE_MS));}
    @Test public void verificationCanExtendLeaseButNotShiftEnd(){TrackingGate g=new TrackingGate();g.confirm("shift",wall,wall+3600000,wall,elapsed);g.confirm("shift",wall,wall+3600000,wall+600000,elapsed+600000);assertTrue(g.active(elapsed+1000000));g.confirm("shift",wall,wall+3600000,wall+3599999,elapsed+3599999);assertFalse(g.active(elapsed+3600000));}
    @Test public void freshProcessMustReverifyEvenIfAttendanceWasSaved(){TrackingGate before=new TrackingGate();before.confirm("shift",wall,wall+3600000,wall,elapsed);TrackingGate after=new TrackingGate();assertFalse(after.active(elapsed));}
    @Test public void futureAndMissingSessionsFailClosed(){TrackingGate g=new TrackingGate();g.confirm("shift",wall+60000,wall+3600000,wall,elapsed);assertFalse(g.active(elapsed));g.confirm("",wall,wall+3600000,wall,elapsed);assertFalse(g.active(elapsed));}
}
