// Issuer API client, used only by code under src/issuer/. This is the
// browser half of the issuer-hosted challenge (the 3-D Secure pattern): voice
// audio and passkey assertions go from here straight to the issuer and never
// pass through the merchant. Must not import anything from src/lib/.
const ISSUER_URL = __ISSUER_URL__;

export class IssuerApiError extends Error {
  // userMessage: the issuer's own wording for the person, when it gave one
  // (e.g. "Hold the sound a little longer"), safe to show as-is.
  constructor(message, status, userMessage = null) {
    super(message);
    this.status = status;
    this.userMessage = userMessage;
  }
}

async function request(path, { method = "GET", body, form } = {}) {
  const res = await fetch(`${ISSUER_URL}${path}`, {
    method,
    // A FormData body sets its own multipart Content-Type with the boundary.
    headers: body === undefined ? {} : { "Content-Type": "application/json" },
    body: form ?? (body === undefined ? undefined : JSON.stringify(body)),
  });
  if (!res.ok) {
    const detail = await res.json().then((j) => j.detail, () => null);
    throw new IssuerApiError(
      `issuer ${method} ${path} failed with HTTP ${res.status}${detail ? `: ${JSON.stringify(detail)}` : ""}`,
      res.status,
      typeof detail === "string" ? detail : null,
    );
  }
  return res.json();
}

export const getHealth = () => request("/healthz");
export const getSession = (sessionId) => request(`/v1/sessions/${encodeURIComponent(sessionId)}`);
export const getCardholders = (sessionId) => request(`/v1/sessions/${encodeURIComponent(sessionId)}/cardholders`);
export const extendSession = (sessionId) =>
  request(`/v1/sessions/${encodeURIComponent(sessionId)}/extend`, { method: "POST" });
const sessionPath = (sessionId) => `/v1/sessions/${encodeURIComponent(sessionId)}`;

// Who is paying: returns the voice challenge, or says the passkey is needed.
export const identifyCardholder = (sessionId, userId) =>
  request(`${sessionPath(sessionId)}/identify`, { method: "POST", body: { user_id: userId } });

// The challenge takes, in the order the bank asked for them.
export function submitVoice(sessionId, wavs) {
  const form = new FormData();
  wavs.forEach((wav, i) => form.append("audio", wav, `take-${i + 1}.wav`));
  return request(`${sessionPath(sessionId)}/voice`, { method: "POST", form });
}

// Passkey at checkout: request options, then send the signed assertion.
export const getPasskeyOptions = (sessionId) =>
  request(`${sessionPath(sessionId)}/passkey/options`, { method: "POST" });
export const submitPasskey = (sessionId, credential) =>
  request(`${sessionPath(sessionId)}/passkey`, { method: "POST", body: { credential } });

// Passkey registration (the bank's own app).
const passkeyPath = (userId) => `/v1/passkeys/${encodeURIComponent(userId)}`;
export const getPasskeyCount = (userId) => request(passkeyPath(userId));
export const getRegistrationOptions = (userId) =>
  request(`${passkeyPath(userId)}/register/options`, { method: "POST" });
export const submitRegistration = (userId, credential) =>
  request(`${passkeyPath(userId)}/register/verify`, { method: "POST", body: { credential } });

// --- Enrollment (the bank's own app) ---
const enrollPath = (userId) => `/v1/enroll/${encodeURIComponent(userId)}`;
const labelPath = (userId, label) => `${enrollPath(userId)}/labels/${encodeURIComponent(label)}`;

export const getEnrollment = (userId) => request(enrollPath(userId));
export function uploadSample(userId, label, wav) {
  const form = new FormData();
  form.append("label", label);
  form.append("audio", wav, "recording.wav");
  return request(`${enrollPath(userId)}/samples`, { method: "POST", form });
}
export const finalizeLabel = (userId, label) => request(`${labelPath(userId, label)}/finalize`, { method: "POST" });
export const startLabelOver = (userId, label) => request(labelPath(userId, label), { method: "DELETE" });
