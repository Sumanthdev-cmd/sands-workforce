package in.sandssoftware.workforce;

/** Pure, monotonic-time privacy boundary. Never restores an active lease from disk. */
public final class TrackingGate {
    public static final long LEASE_MS = 15 * 60 * 1000L;
    private String session = "";
    private long start, end, validUntilElapsed;
    private boolean enabled;

    public synchronized void confirm(String id, long checkIn, long maximumEnd, long wallNow, long elapsedNow) {
        if (id == null || id.isEmpty() || checkIn <= 0 || maximumEnd <= wallNow || checkIn > wallNow + 30000) {
            stop(); return;
        }
        session = id; start = checkIn; end = maximumEnd;
        validUntilElapsed = elapsedNow + Math.min(LEASE_MS, maximumEnd - wallNow);
        enabled = true;
    }
    public synchronized boolean allows(String id, long capturedAt, long elapsedNow) {
        return enabled && session.equals(id) && elapsedNow < validUntilElapsed && capturedAt >= start && capturedAt <= end;
    }
    public synchronized boolean active(long elapsedNow) { return enabled && elapsedNow < validUntilElapsed; }
    public synchronized void stop() { enabled = false; validUntilElapsed = 0; }
}
