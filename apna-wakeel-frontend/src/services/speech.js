// -----------------------------------------------------------------------------
// SPEECH-TO-TEXT SERVICE
// This is the only file that talks to a speech recognizer. It gives the
// authenticated voice workspace one small interface:
//
//   const recognizer = createSpeechRecognizer("ur");
//   recognizer.supported                -> true/false, check before showing the mic
//   recognizer.start({ onInterim, onFinal, onError, onEnd })
//   recognizer.stop()
//
// Browser speech recognition and synthesis are used because this project has
// no backend audio transcription or speech generation endpoints.
//
// LANGUAGE CODES: this file expects the app's own codes ("en", "ur") and maps
// them to whatever the engine needs (BCP-47 tags for the browser engine).
// -----------------------------------------------------------------------------

const PROVIDER = import.meta.env?.VITE_STT_PROVIDER || "browser";

const BROWSER_LANG_TAGS = {
  en: "en-US",
  ur: "ur-PK",
  roman_urdu: "en-IN",
};

export function normalizeSpeechLanguage(languageCode) {
  if (languageCode === "ur") return "ur";
  if (languageCode === "roman_urdu") return "roman_urdu";
  return "en";
}

function getBrowserEngine() {
  if (typeof window === "undefined") return null;
  return window.SpeechRecognition || window.webkitSpeechRecognition || null;
}

function browserRecognizer(langCode) {
  const Engine = getBrowserEngine();
  let recognition = null;
  let canceled = false;
  let errorOccurred = false;
  let finalDelivered = false;
  let callbacks = null;
  let finalText = "";
  let latestTranscript = "";

  return {
    supported: !!Engine,

    start(handlers) {
      if (!Engine) {
        handlers.onError?.({ type: "unsupported" });
        return;
      }
      canceled = false;
      errorOccurred = false;
      finalDelivered = false;
      finalText = "";
      latestTranscript = "";
      callbacks = handlers;

      try {
        recognition = new Engine();
        recognition.lang = BROWSER_LANG_TAGS[langCode] || BROWSER_LANG_TAGS[normalizeSpeechLanguage(langCode)];
        recognition.continuous = true;
        recognition.interimResults = true;

        recognition.onresult = (event) => {
          if (canceled) return;
          let interim = "";
          const finalChunks = [];
          for (let i = 0; i < event.results.length; i++) {
            const result = event.results[i];
            const chunk = result[0]?.transcript?.trim() || "";
            if (result.isFinal) {
              if (chunk) finalChunks.push(chunk);
            } else {
              interim += `${interim ? " " : ""}${chunk}`;
            }
          }
          finalText = finalChunks.join(" ");
          latestTranscript = `${finalText} ${interim}`.trim();
          handlers.onInterim?.(latestTranscript);
        };

        recognition.onerror = (event) => {
          if (canceled) return;
          errorOccurred = true;
          const errorType = event.error === "not-allowed" || event.error === "permission-denied" || event.error === "service-not-allowed"
            ? "permission-denied"
            : event.error === "no-speech"
              ? "no-speech"
              : event.error === "audio-capture"
                ? "audio-capture"
                : "unknown";
          handlers.onError?.({ type: errorType, detail: event.error });
        };

        recognition.onend = () => {
          if (canceled) return;
          if (!errorOccurred && !finalDelivered) {
            finalDelivered = true;
            if (latestTranscript) handlers.onFinal?.(latestTranscript);
          }
          handlers.onEnd?.();
        };

        recognition.start();
      } catch (error) {
        errorOccurred = true;
        handlers.onError?.({ type: "unknown", detail: String(error) });
      }
    },

    stop() {
      try {
        recognition?.stop();
      } catch (error) {
        callbacks?.onError?.({ type: "unknown", detail: String(error) });
      }
    },

    cancel() {
      canceled = true;
      try {
        recognition?.abort();
      } catch (error) {
        callbacks?.onError?.({ type: "unknown", detail: String(error) });
      }
    },
  };
}

// eslint-disable-next-line no-unused-vars
function apiRecognizer(langCode) {
  // ---- Fill this in once the team's speech-to-text endpoint exists ----
  // Expected shape, to match the rest of services/api.js:
  //   POST /api/speech-to-text   (multipart audio, field "audio", plus "language")
  //   returns { text: "..." }
  //
  // A typical implementation records audio with MediaRecorder, then on stop()
  // uploads the recorded blob and calls onFinal(data.text).
  return {
    supported: false,
    start({ onError }) {
      onError({ type: "unsupported" });
    },
    stop() {},
  };
}

export function createSpeechRecognizer(langCode) {
  if (PROVIDER === "api") {
    const api = apiRecognizer(langCode);
    if (api.supported) return api;
  }
  return browserRecognizer(langCode);
}

let speechRequestId = 0;

function isSectionHeading(line, labels) {
  const normalizedLine = line.trim().replace(/:\s*$/, "").toLocaleLowerCase();
  return Object.values(labels).some((label) => label && normalizedLine === String(label).trim().replace(/:\s*$/, "").toLocaleLowerCase());
}

export function cleanSpeechText(text, labels = {}) {
  const excludedSections = [labels.caseSummary, labels.officialReferences].filter(Boolean);
  const removableHeadings = Object.values(labels).filter(Boolean);
  const blocks = String(text || "").split(/\n\s*\n/);
  const cleanedBlocks = blocks.flatMap((block) => {
    const lines = block.split("\n");
    if (excludedSections.some((heading) => isSectionHeading(lines[0], { heading }))) return [];
    return [lines.filter((line) => !isSectionHeading(line, Object.fromEntries(removableHeadings.map((heading, index) => [index, heading])))).join("\n")];
  });

  return cleanedBlocks.join(" ")
    .replace(/```[\s\S]*?```/g, " ")
    .replace(/\[([^\]]+)\]\(https?:\/\/[^)]+\)/g, "$1")
    .replace(/https?:\/\/\S+/g, " ")
    .replace(/<[^>]+>/g, " ")
    .replace(/^\s{0,3}#{1,6}\s*/gm, "")
    .replace(/[*_~`]/g, "")
    .replace(/^\s*(?:[-*+]\s+|\d+[.)]\s+)/gm, "")
    .replace(/[ \t]+/g, " ")
    .replace(/\s*\n\s*/g, " ")
    .replace(/\s{2,}/g, " ")
    .trim();
}

export function splitSpeechText(text, maxLength = 240) {
  const remaining = String(text || "").trim();
  if (!remaining) return [];
  const chunks = [];
  let rest = remaining;

  while (rest.length > maxLength) {
    let boundary = Math.max(
      rest.lastIndexOf(". ", maxLength),
      rest.lastIndexOf("? ", maxLength),
      rest.lastIndexOf("! ", maxLength),
      rest.lastIndexOf("۔ ", maxLength),
      rest.lastIndexOf("؟ ", maxLength),
      rest.lastIndexOf(" ", maxLength),
    );
    if (boundary < maxLength * 0.55) boundary = maxLength;
    chunks.push(rest.slice(0, boundary).trim());
    rest = rest.slice(boundary).trim();
  }

  if (rest) chunks.push(rest);
  return chunks;
}

export function stopSpeaking() {
  speechRequestId += 1;
  if (typeof window !== "undefined") window.speechSynthesis?.cancel?.();
}

export function speakText(text, languageCode, handlers = {}, labels = {}) {
  if (typeof window === "undefined" || !window.speechSynthesis || !window.SpeechSynthesisUtterance) {
    throw new Error("tts-unavailable");
  }
  const spokenText = cleanSpeechText(text, labels);
  const chunks = splitSpeechText(spokenText);
  if (!chunks.length) throw new Error("tts-empty");

  const normalizedLanguage = normalizeSpeechLanguage(languageCode);
  const voices = window.speechSynthesis.getVoices?.() || [];
  const targetLocale = BROWSER_LANG_TAGS[normalizedLanguage].toLowerCase();
  const voice = voices.find((item) => item.lang?.toLowerCase().replace("_", "-") === targetLocale)
    || voices.find((item) => item.lang?.toLowerCase().replace("_", "-").startsWith(`${targetLocale.slice(0, 2)}-`));
  if (normalizedLanguage === "ur" && voices.length > 0 && !voice) throw new Error("tts-language-unavailable");

  const requestId = ++speechRequestId;
  window.speechSynthesis.cancel();
  let chunkIndex = 0;
  const speakNextChunk = () => {
    if (requestId !== speechRequestId) return;
    const utterance = new window.SpeechSynthesisUtterance(chunks[chunkIndex]);
    utterance.lang = BROWSER_LANG_TAGS[normalizedLanguage];
    utterance.rate = 0.95;
    utterance.pitch = 1;
    if (voice) utterance.voice = voice;
    utterance.onstart = (event) => {
      if (requestId === speechRequestId && chunkIndex === 0) handlers.onStart?.(event);
    };
    utterance.onend = (event) => {
      if (requestId !== speechRequestId) return;
      chunkIndex += 1;
      if (chunkIndex < chunks.length) speakNextChunk();
      else handlers.onEnd?.(event);
    };
    utterance.onerror = (event) => {
      if (requestId === speechRequestId) handlers.onError?.(event);
    };
    window.speechSynthesis.speak(utterance);
  };
  speakNextChunk();
  return () => {
    if (requestId === speechRequestId) stopSpeaking();
  };
}
