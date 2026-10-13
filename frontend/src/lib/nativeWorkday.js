// The existing Android bridge is restricted to the first-party top-level page.
export function isNativeWorkday() {
  return window.location.origin === "https://app.sandssoftware.in"
    && typeof window.WorkforceNative?.postMessage === "function";
}

export function openNativeWorkday() {
  if (!isNativeWorkday()) return false;
  window.WorkforceNative.postMessage(JSON.stringify({id: "attendance", action: "workday"}));
  return true;
}
