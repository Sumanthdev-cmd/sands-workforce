package in.sandssoftware.workforce;

import android.app.job.JobParameters;
import android.app.job.JobService;

/** OS-owned, connectivity-aware retry for token rotation; not a notification polling loop. */
public final class PushRegistrationJob extends JobService {
    private volatile boolean stopped;
    @Override public boolean onStartJob(JobParameters parameters) {
        stopped=false;
        WorkforceApp.push(this).register(retry->{if(!stopped)jobFinished(parameters,retry);});
        return true;
    }
    @Override public boolean onStopJob(JobParameters parameters) {stopped=true;return true;}
}
