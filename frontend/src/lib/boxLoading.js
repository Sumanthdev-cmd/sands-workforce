export const statusLabels = {DRAFT: "Draft", PENDING_MD: "Awaiting MD approval", APPROVED: "Approved · unpaid", REJECTED: "Rejected", PAID: "Disbursed"};
export function localDate() {
  const now = new Date();
  return `${now.getFullYear()}-${String(now.getMonth()+1).padStart(2,"0")}-${String(now.getDate()).padStart(2,"0")}`;
}
export function newRequestId() {
  // getRandomValues also supports the older WebViews used on Android 8.
  const bytes = crypto.getRandomValues(new Uint8Array(16));
  bytes[6] = (bytes[6] & 15) | 64;
  bytes[8] = (bytes[8] & 63) | 128;
  const hex = Array.from(bytes, b => b.toString(16).padStart(2,"0")).join("");
  return `${hex.slice(0,8)}-${hex.slice(8,12)}-${hex.slice(12,16)}-${hex.slice(16,20)}-${hex.slice(20)}`;
}
export function cents(value) {
  const text = String(value).trim();
  if (!/^\d+(\.\d{1,2})?$/.test(text)) return null;
  const [whole, fraction=""] = text.split(".");
  const amount = Number(whole)*100 + Number(fraction.padEnd(2,"0"));
  return Number.isSafeInteger(amount) && amount <= 100000000 ? amount : null;
}
export function boxCount(value) {
  if (!/^\d+$/.test(String(value).trim())) return null;
  const count = Number(value);
  return Number.isSafeInteger(count) && count >= 1 && count <= 1000000 ? count : null;
}
export function calculatedCosts(form) {
  const rate = cents(form.loading_rate), count = boxCount(form.loading_box_count);
  const loading = rate === null || count === null ? null : rate*count;
  const transportRate = cents(form.transport_rate), transportCount = boxCount(form.transport_box_count);
  const transport = form.vehicle_type === "OWN" ? 0 :
    transportRate === null || transportCount === null ? null : transportRate*transportCount;
  return {loading, transport, total: loading === null || transport === null ? null : loading+transport};
}
export const money = value => value == null ? "—" : new Intl.NumberFormat("en-IN", {style:"currency",currency:"INR",minimumFractionDigits:2}).format(Number(value));
export const moneyCents = value => value == null ? "—" : money(value/100);
