// Shopping-only capture. Kept separate from the issuer surface to preserve
// the merchant/issuer import boundary. Produces 16 kHz mono PCM WAV.

export const TARGET_RATE = 16000;   // mirrors api/config.py SHOP_SAMPLE_RATE
export const MIN_SECONDS = 0.3;     // enough audio for a short shopping word
export const MAX_SECONDS = 10;      // mirrors api/config.py SHOP_AUDIO_MAX_SECONDS

// Browser voice processing reshapes the signal differently from one take to
// the next, which makes the same person's recordings look less alike. Off.
const CONSTRAINTS = {
  audio: { channelCount: 1, echoCancellation: false, noiseSuppression: false, autoGainControl: false },
};

export class MicrophoneError extends Error {}

// Thrown when a take is too short to use, with a message that says what to do.
// Caught before upload, so a quick tap-tap gets advice instead of an error.
export class TooShortError extends Error {}
const TOO_SHORT = `That was too short. Keep recording a little longer, at least ${MIN_SECONDS} seconds.`;

export async function startRecording({ onLevel } = {}) {
  let stream;
  try {
    stream = await navigator.mediaDevices.getUserMedia(CONSTRAINTS);
  } catch (err) {
    const blocked = err.name === "NotAllowedError" || err.name === "SecurityError";
    throw new MicrophoneError(blocked
      ? "Microphone access is blocked. Allow the microphone for this site in your browser, then try again."
      : "No microphone was found. Connect a headset or microphone, then try again.");
  }

  let recorder;
  let meterCtx = null;
  let stopped;
  const chunks = [];
  let frame = 0;
  try {
    recorder = new MediaRecorder(stream);
    recorder.ondataavailable = (e) => {
      if (e.data.size > 0) chunks.push(e.data);
    };
    stopped = new Promise((resolve) => {
      recorder.onstop = resolve;
    });

    // Input level for the visual meter only; the upload is the decoded recording.
    meterCtx = new AudioContext();
    const analyser = meterCtx.createAnalyser();
    analyser.fftSize = 1024;
    meterCtx.createMediaStreamSource(stream).connect(analyser);
    const samples = new Float32Array(analyser.fftSize);
    const tick = () => {
      analyser.getFloatTimeDomainData(samples);
      let sum = 0;
      for (const s of samples) sum += s * s;
      onLevel?.(Math.sqrt(sum / samples.length));
      frame = requestAnimationFrame(tick);
    };
    if (onLevel) tick();

    recorder.start();
  } catch (err) {
    // The microphone was granted: release it, or it stays on through every retry.
    cancelAnimationFrame(frame);
    stream.getTracks().forEach((t) => t.stop());
    meterCtx?.close().catch((closeErr) => console.warn("meter context did not close", closeErr));
    throw new MicrophoneError(`Recording could not start on this device (${err.name}). Please try again.`);
  }

  let result = null;
  function stop() {
    // Idempotent: the Stop button and the time limit may both call it.
    result ??= (async () => {
      if (recorder.state !== "inactive") recorder.stop();
      await stopped;
      cancelAnimationFrame(frame);
      stream.getTracks().forEach((t) => t.stop());
      // Not awaited: closing the meter must never be able to block saving.
      meterCtx.close().catch((err) => console.warn("meter context did not close", err));
      if (chunks.length === 0) throw new TooShortError(TOO_SHORT);
      const blob = new Blob(chunks, { type: recorder.mimeType });
      let mono;
      try {
        mono = await toMono16k(await blob.arrayBuffer());
      } catch (err) {
        // A tap-tap too quick to contain a whole audio frame does not decode.
        console.warn("recording did not decode", err);
        throw new TooShortError(TOO_SHORT);
      }
      if (mono.length / TARGET_RATE < MIN_SECONDS) throw new TooShortError(TOO_SHORT);
      // The auto-stop timer fires a few milliseconds after the limit; trim so
      // the merchant's duration check never rejects a take that hit the limit.
      mono = mono.subarray(0, MAX_SECONDS * TARGET_RATE);
      return { wav: encodeWav(mono, TARGET_RATE), seconds: mono.length / TARGET_RATE };
    })();
    return result;
  }
  return { stop };
}

// Exported so the conversion path can be checked on its own (it needs no
// live microphone), separately from capture.
export async function toMono16k(encoded) {
  // An OfflineAudioContext needs no audio hardware and nothing to close, and
  // decodeAudioData resamples to the context's rate: the result is 16 kHz.
  const decodeCtx = new OfflineAudioContext(1, 1, TARGET_RATE);
  const audio = await decodeCtx.decodeAudioData(encoded);
  if (audio.sampleRate !== TARGET_RATE) {
    throw new Error(`decoded at ${audio.sampleRate} Hz, expected ${TARGET_RATE} Hz`);
  }
  if (audio.numberOfChannels === 1) return audio.getChannelData(0);
  // Downmix by averaging channels.
  const mono = new Float32Array(audio.length);
  for (let c = 0; c < audio.numberOfChannels; c++) {
    const channel = audio.getChannelData(c);
    for (let i = 0; i < mono.length; i++) mono[i] += channel[i] / audio.numberOfChannels;
  }
  return mono;
}

export function encodeWav(samples, rate) {
  const bytesPerSample = 2;
  const buffer = new ArrayBuffer(44 + samples.length * bytesPerSample);
  const view = new DataView(buffer);
  const text = (offset, s) => [...s].forEach((c, i) => view.setUint8(offset + i, c.charCodeAt(0)));
  text(0, "RIFF");
  view.setUint32(4, 36 + samples.length * bytesPerSample, true);
  text(8, "WAVE");
  text(12, "fmt ");
  view.setUint32(16, 16, true);              // PCM chunk size
  view.setUint16(20, 1, true);               // PCM format
  view.setUint16(22, 1, true);               // mono
  view.setUint32(24, rate, true);
  view.setUint32(28, rate * bytesPerSample, true);
  view.setUint16(32, bytesPerSample, true);
  view.setUint16(34, 16, true);              // bits per sample
  text(36, "data");
  view.setUint32(40, samples.length * bytesPerSample, true);
  let offset = 44;
  for (const s of samples) {
    const clamped = Math.max(-1, Math.min(1, s));
    view.setInt16(offset, clamped < 0 ? clamped * 0x8000 : clamped * 0x7fff, true);
    offset += bytesPerSample;
  }
  return new Blob([buffer], { type: "audio/wav" });
}
