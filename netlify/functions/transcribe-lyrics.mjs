import { createHmac, timingSafeEqual } from "node:crypto";

const YOUTUBE_HOSTS = new Set([
  "youtube.com",
  "m.youtube.com",
  "music.youtube.com",
  "youtube-nocookie.com",
  "youtu.be"
]);
const MAX_REQUEST_BYTES = 4096;
const MAX_LYRIC_CHARACTERS = 50000;
const RATE_LIMIT_WINDOW_MS = 15000;
const JOB_TOKEN_LIFETIME_MS = 20 * 60 * 1000;
const recentRequests = new Map();

async function readLimitedBody(request) {
  if (!request.body) return "";
  const reader = request.body.getReader();
  const chunks = [];
  let byteLength = 0;
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    byteLength += value.byteLength;
    if (byteLength > MAX_REQUEST_BYTES) {
      await reader.cancel();
      throw new RangeError("Request body is too large.");
    }
    chunks.push(value);
  }
  const bytes = new Uint8Array(byteLength);
  let offset = 0;
  for (const chunk of chunks) {
    bytes.set(chunk, offset);
    offset += chunk.byteLength;
  }
  return new TextDecoder("utf-8", { fatal: true }).decode(bytes);
}

function jsonResponse(body, status = 200, extraHeaders = {}) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store",
      ...extraHeaders
    }
  });
}

function youtubeVideoId(value) {
  try {
    const url = new URL(value);
    const host = url.hostname.toLowerCase().replace(/^www\./, "");
    if (url.protocol !== "https:" || !YOUTUBE_HOSTS.has(host)) return "";
    let id = "";
    if (host === "youtu.be") {
      id = url.pathname.split("/").filter(Boolean)[0] || "";
    } else {
      id = url.searchParams.get("v") || "";
      if (!id) {
        const match = url.pathname.match(/^\/(?:shorts|embed|live)\/([^/?]+)/);
        id = match ? match[1] : "";
      }
    }
    return /^[A-Za-z0-9_-]{11}$/.test(id) ? id : "";
  } catch (_error) {
    return "";
  }
}

function claimRateLimit(ip) {
  const now = Date.now();
  for (const [key, timestamp] of recentRequests) {
    if (now - timestamp >= RATE_LIMIT_WINDOW_MS) recentRequests.delete(key);
  }
  const key = ip || "unknown";
  const previous = recentRequests.get(key);
  if (previous && now - previous < RATE_LIMIT_WINDOW_MS) {
    return Math.ceil(RATE_LIMIT_WINDOW_MS - (now - previous));
  }
  recentRequests.set(key, now);
  if (recentRequests.size > 5000) {
    const oldestKey = recentRequests.keys().next().value;
    if (oldestKey !== undefined) recentRequests.delete(oldestKey);
  }
  return 0;
}

function extractOutputText(data) {
  if (!data || typeof data !== "object") return "";
  if (typeof data.output_text === "string") return data.output_text.trim();
  const stepText = (Array.isArray(data.steps) ? data.steps : [])
    .filter((step) => step && step.type === "model_output" && Array.isArray(step.content))
    .flatMap((step) => step.content)
    .filter((item) => item && item.type === "text" && typeof item.text === "string")
    .map((item) => item.text)
    .join("\n")
    .trim();
  if (stepText) return stepText;
  return (Array.isArray(data.outputs) ? data.outputs : [])
    .filter((item) => item && item.type === "text" && typeof item.text === "string")
    .map((item) => item.text)
    .join("\n")
    .trim();
}

function safeGeminiError(result) {
  const error = result && result.error && typeof result.error === "object" ? result.error : {};
  const message = typeof error.message === "string"
    ? error.message
    : result && typeof result.message === "string" ? result.message : "";
  return {
    code: Number.isSafeInteger(error.code) ? error.code : undefined,
    status: typeof error.status === "string" ? error.status.slice(0, 80) : undefined,
    message: message
      .replace(/AIza[0-9A-Za-z_-]{20,}/g, "[redacted API key]")
      .replace(/[\r\n\t]+/g, " ")
      .replace(/\s+/g, " ")
      .trim()
      .slice(0, 280)
  };
}

function retryDelayFrom(result, response) {
  const header = Number(response.headers.get("retry-after"));
    if (Number.isFinite(header) && header > 0) return Math.min(Math.ceil(header * 1000), 24 * 60 * 60 * 1000);
  const details = result && result.error && Array.isArray(result.error.details) ? result.error.details : [];
  for (const detail of details) {
    if (!detail || !String(detail["@type"] || "").endsWith("RetryInfo")) continue;
    const value = String(detail.retryDelay || "");
    const match = value.match(/^(\d+(?:\.\d+)?)s$/);
    if (match) return Math.min(Math.ceil(Number(match[1]) * 1000), 24 * 60 * 60 * 1000);
  }
  return 0;
}

function isDailyOrSpendLimit(result) {
  const error = result && result.error && typeof result.error === "object" ? result.error : {};
  const text = [error.status, error.message, ...(Array.isArray(error.details) ? error.details.map((item) => JSON.stringify(item)) : [])]
    .filter(Boolean).join(" ").toLowerCase();
  return /daily|per.day|requests per day|tokens per day|quota_exceeded|daily limit|spend limit|billing|credits/.test(text);
}

function createJobToken(interactionId, apiKey) {
  const payload = Buffer.from(JSON.stringify({
    id: interactionId,
    expiresAt: Date.now() + JOB_TOKEN_LIFETIME_MS
  })).toString("base64url");
  const signature = createHmac("sha256", apiKey).update(payload).digest("base64url");
  return payload + "." + signature;
}

function readJobToken(token, apiKey) {
  if (typeof token !== "string" || token.length > 2048) return "";
  const separator = token.lastIndexOf(".");
  if (separator < 1) return "";
  const payload = token.slice(0, separator);
  const providedSignature = token.slice(separator + 1);
  const expectedSignature = createHmac("sha256", apiKey).update(payload).digest("base64url");
  const providedBytes = Buffer.from(providedSignature);
  const expectedBytes = Buffer.from(expectedSignature);
  if (providedBytes.length !== expectedBytes.length || !timingSafeEqual(providedBytes, expectedBytes)) return "";
  try {
    const decoded = JSON.parse(Buffer.from(payload, "base64url").toString("utf8"));
    if (!decoded || !/^(?:v1|int)_[A-Za-z0-9_-]{6,200}$/.test(decoded.id || "")
      || !Number.isSafeInteger(decoded.expiresAt) || decoded.expiresAt < Date.now()) return "";
    return decoded.id;
  } catch (_error) {
    return "";
  }
}

async function readGeminiResponse(response) {
  try {
    const result = await response.json();
    return result && typeof result === "object" && !Array.isArray(result) ? result : {};
  } catch (_error) {
    return {};
  }
}

async function callGemini(apiKey, path, options = {}) {
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), options.timeoutMs || 12000);
  try {
    const response = await fetch("https://generativelanguage.googleapis.com/v1beta/interactions" + path, {
      method: options.method || "GET",
      headers: {
        "x-goog-api-key": apiKey,
        "Api-Revision": "2026-05-20",
        ...(options.body ? { "Content-Type": "application/json" } : {})
      },
      ...(options.body ? { body: JSON.stringify(options.body) } : {}),
      signal: controller.signal
    });
    return { response, result: await readGeminiResponse(response) };
  } finally {
    clearTimeout(timeout);
  }
}

async function deleteInteraction(interactionId, apiKey) {
  try {
    const { response } = await callGemini(apiKey, "/" + encodeURIComponent(interactionId), {
      method: "DELETE",
      timeoutMs: 8000
    });
    if (!response.ok && response.status !== 404) {
      console.error("XENOMIND Gemini interaction deletion failed.", JSON.stringify({ httpStatus: response.status }));
    }
    return response.ok || response.status === 404;
  } catch (error) {
    console.error("XENOMIND Gemini interaction deletion failed.", error && error.name || "unknown error");
    return false;
  }
}

function quotaResponse(result, retryAfterMs) {
  const isPersistentLimit = isDailyOrSpendLimit(result);
  const suggestedRetryMs = retryAfterMs || (isPersistentLimit ? 0 : 2000);
  const retryable = !isPersistentLimit && suggestedRetryMs <= 20000;
  let message;
  if (isPersistentLimit) {
    message = "Gemini's project quota or spend limit is exhausted. Check the active limits and billing for this API key in Google AI Studio; retrying will not help until the limit resets or is raised."
      + (retryAfterMs >= 60000 ? " Gemini estimates the wait at about " + Math.ceil(retryAfterMs / 60000) + " minutes." : "");
  } else if (suggestedRetryMs > 0) {
    message = "Gemini is temporarily limiting requests. "
      + (suggestedRetryMs >= 60000 ? "Wait about " + Math.ceil(suggestedRetryMs / 60000) + " minutes" : "Wait about " + Math.ceil(suggestedRetryMs / 1000) + " seconds")
      + " and try again.";
  } else {
    message = "Gemini returned a 429 request limit. Check the Gemini API limits in Google AI Studio; this may be a temporary capacity limit or a project quota.";
  }
  return jsonResponse({ message, retryable, retryAfterMs: retryable ? suggestedRetryMs : undefined }, 429,
    suggestedRetryMs > 0 ? { "Retry-After": String(Math.ceil(suggestedRetryMs / 1000)) } : {});
}

function upstreamFailure(response, result) {
  const geminiError = safeGeminiError(result);
  console.error("XENOMIND Gemini video request failed.", JSON.stringify({
    httpStatus: response.status,
    apiCode: geminiError.code,
    apiStatus: geminiError.status,
    message: geminiError.message
  }));
  if (response.status === 429) return quotaResponse(result, retryDelayFrom(result, response));
  if (response.status === 401 || response.status === 403) {
    return jsonResponse({
      message: "Gemini rejected the server key or its API access. Check that GEMINI_API_KEY is enabled for Netlify Functions and that the Gemini API is available to that key."
    }, 502);
  }
  if (response.status === 400 || response.status === 404) {
    return jsonResponse({
      message: geminiError.message
        ? "Gemini rejected this video request: " + geminiError.message
        : "Gemini could not analyze this video. Confirm the video is public and try again."
    }, 502);
  }
  if (response.status === 503 || response.status === 500) {
    return jsonResponse({
      message: "Gemini is temporarily overloaded. The video was not queued; try again in a little while.",
      retryable: true,
      retryAfterMs: 2000
    }, 503, { "Retry-After": "2" });
  }
  return jsonResponse({
    message: geminiError.message
      ? "Gemini returned an error: " + geminiError.message
      : "Gemini is temporarily unavailable. Try again later."
  }, 502);
}

async function handleStart(body, context, apiKey) {
  const videoId = youtubeVideoId(String(body.videoUrl || ""));
  if (!videoId) return jsonResponse({ message: "Use a public YouTube video link." }, 400);
  const retryAfterMs = claimRateLimit(context && context.ip);
  if (retryAfterMs) {
    return jsonResponse({
      message: "Please wait a few seconds before generating another lyric draft.",
      retryable: true,
      retryAfterMs
    }, 429, { "Retry-After": String(Math.ceil(retryAfterMs / 1000)) });
  }
  const languageHint = String(body.languageHint || "")
    .replace(/[\u0000-\u001f\u007f]/g, " ")
    .trim()
    .slice(0, 100);
  const prompt = [
    "Create a working lyric transcription draft for musicians rehearsing this song.",
    "Transcribe only words that are actually sung or spoken in the audio, in their original language and in the order heard.",
    "Do not summarize, translate, complete missing lines from memory, or add explanations, speaker labels, or music descriptions.",
    "Keep repeated lyrics repeated. Put each vocal phrase on its own line.",
    "Mark words you cannot confidently hear as [unclear] rather than guessing.",
    languageHint ? "Language or pronunciation hint from the band: " + languageHint : ""
  ].filter(Boolean).join("\n");
  const requestBody = {
    model: "gemini-3.8-flash",
    store: true,
    background: true,
    input: [
      { type: "text", text: prompt },
      { type: "video", uri: "https://www.youtube.com/watch?v=" + videoId }
    ],
    generation_config: {
      thinking_level: "low",
      max_output_tokens: 16000
    }
  };

  let created;
  try {
    created = await callGemini(apiKey, "", { method: "POST", body: requestBody });
  } catch (error) {
    if (error && error.name === "AbortError") {
      return jsonResponse({
        message: "Gemini did not confirm that the analysis was queued. Check the connection and try again; no lyric draft was returned."
      }, 504);
    }
    console.error("XENOMIND lyric generation request failed.", error && error.name || "unknown error");
    return jsonResponse({ message: "The lyric generator is temporarily unavailable. Try again later." }, 502);
  }
  if (!created.response.ok) return upstreamFailure(created.response, created.result);

  const interactionId = typeof created.result.id === "string" ? created.result.id : "";
  if (!/^(?:v1|int)_[A-Za-z0-9_-]{6,200}$/.test(interactionId)) {
    return jsonResponse({ message: "Gemini did not return a valid background job. Try again later." }, 502);
  }
  const jobToken = createJobToken(interactionId, apiKey);
  if (created.result.status === "completed") {
    const lyrics = extractOutputText(created.result);
    await deleteInteraction(interactionId, apiKey);
    if (!lyrics) return jsonResponse({ message: "No clear vocals were detected in this video." }, 422);
    if (lyrics.length > MAX_LYRIC_CHARACTERS) {
      return jsonResponse({ message: "The lyric draft is too long for one note. Use a shorter video." }, 422);
    }
    return jsonResponse({ status: "completed", lyrics });
  }
  if (!["queued", "in_progress"].includes(created.result.status)) {
    const error = safeGeminiError(created.result).message;
    await deleteInteraction(interactionId, apiKey);
    return jsonResponse({
      message: error ? "The lyric draft could not be started: " + error : "The lyric draft could not be started. Try again later."
    }, 502);
  }
  return jsonResponse({ status: created.result.status, jobToken, pollAfterMs: 2500 }, 202);
}

async function handlePoll(body, apiKey) {
  const interactionId = readJobToken(body.jobToken, apiKey);
  if (!interactionId) return jsonResponse({ message: "This lyric analysis session has expired. Start the import again." }, 400);
  let polled;
  try {
    polled = await callGemini(apiKey, "/" + encodeURIComponent(interactionId));
  } catch (error) {
    if (error && error.name === "AbortError") {
      return jsonResponse({
        status: "in_progress",
        retryable: true,
        retryAfterMs: 4000
      }, 503, { "Retry-After": "4" });
    }
    console.error("XENOMIND Gemini status check failed.", error && error.name || "unknown error");
    return jsonResponse({ status: "in_progress", retryable: true, retryAfterMs: 4000 }, 503);
  }
  if (!polled.response.ok) {
    if ([429, 500, 502, 503, 504].includes(polled.response.status)) {
      const retryAfterMs = retryDelayFrom(polled.result, polled.response) || 4000;
      if (polled.response.status === 429 && isDailyOrSpendLimit(polled.result)) {
        return quotaResponse(polled.result, retryAfterMs);
      }
      return jsonResponse({
        status: "in_progress",
        retryable: true,
        retryAfterMs: Math.min(retryAfterMs, 15000)
      }, 503);
    }
    await deleteInteraction(interactionId, apiKey);
    if (polled.response.status === 404) {
      return jsonResponse({ message: "Gemini no longer has this lyric analysis. Start the import again." }, 410);
    }
    return upstreamFailure(polled.response, polled.result);
  }

  const status = String(polled.result.status || "");
  if (status === "queued" || status === "in_progress") {
    return jsonResponse({ status, pollAfterMs: 3500 }, 202);
  }
  if (status === "completed") {
    const lyrics = extractOutputText(polled.result);
    if (!lyrics) {
      await deleteInteraction(interactionId, apiKey);
      return jsonResponse({ message: "No clear vocals were detected in this video." }, 422);
    }
    if (lyrics.length > MAX_LYRIC_CHARACTERS) {
      await deleteInteraction(interactionId, apiKey);
      return jsonResponse({ message: "The lyric draft is too long for one note. Use a shorter video." }, 422);
    }
    return jsonResponse({ status: "completed", lyrics });
  }

  const completionError = safeGeminiError(polled.result).message;
  await deleteInteraction(interactionId, apiKey);
  if (/429|resource_exhausted|rate.limit|quota|capacity/i.test(completionError)) {
    return jsonResponse({
      message: "Gemini could not start this video analysis because of a request limit. Check the API limits in Google AI Studio, wait for the limit to reset, then try again."
    }, 429);
  }
  console.error("XENOMIND Gemini interaction did not complete.", JSON.stringify({ status: status.slice(0, 80), message: completionError }));
  return jsonResponse({
    message: completionError
      ? "The lyric draft did not finish: " + completionError
      : "The lyric draft did not finish. Try a shorter public video or check the Gemini API limits."
  }, 502);
}

async function handleCleanup(body, apiKey) {
  const interactionId = readJobToken(body.jobToken, apiKey);
  if (!interactionId) return jsonResponse({ message: "This lyric analysis session has expired." }, 400);
  const deleted = await deleteInteraction(interactionId, apiKey);
  return deleted
    ? jsonResponse({ deleted: true })
    : jsonResponse({ message: "The lyric draft was received, but Gemini did not confirm deletion of its stored interaction." }, 502);
}

async function handleCancel(body, apiKey) {
  const interactionId = readJobToken(body.jobToken, apiKey);
  if (!interactionId) return jsonResponse({ message: "This lyric analysis session has expired." }, 400);
  try {
    await callGemini(apiKey, "/" + encodeURIComponent(interactionId) + "/cancel", {
      method: "POST",
      body: {},
      timeoutMs: 8000
    });
  } catch (_error) { /* The job may already have completed; deletion is still attempted. */ }
  const deleted = await deleteInteraction(interactionId, apiKey);
  return deleted
    ? jsonResponse({ deleted: true })
    : jsonResponse({ message: "Gemini did not confirm deletion of this lyric interaction." }, 502);
}

export default async (request, context) => {
  if (request.method !== "POST") {
    return new Response(JSON.stringify({ message: "Use POST to generate a lyric draft." }), {
      status: 405,
      headers: {
        "Content-Type": "application/json; charset=utf-8",
        "Cache-Control": "no-store",
        "Allow": "POST"
      }
    });
  }
  const origin = request.headers.get("origin");
  if (origin) {
    try {
      if (new URL(origin).origin !== new URL(request.url).origin) {
        return jsonResponse({ message: "Requests must come from this XENOMIND page." }, 403);
      }
    } catch (_error) {
      return jsonResponse({ message: "Requests must come from this XENOMIND page." }, 403);
    }
  }
  const contentType = (request.headers.get("content-type") || "").split(";", 1)[0].trim().toLowerCase();
  if (contentType !== "application/json") return jsonResponse({ message: "Send the request as JSON." }, 415);
  const contentLengthHeader = request.headers.get("content-length");
  if (contentLengthHeader !== null) {
    const contentLength = Number(contentLengthHeader);
    if (!Number.isSafeInteger(contentLength) || contentLength < 0) {
      return jsonResponse({ message: "The request size could not be read." }, 400);
    }
    if (contentLength > MAX_REQUEST_BYTES) return jsonResponse({ message: "The request is too large." }, 413);
  }
  let body;
  try {
    const rawBody = await readLimitedBody(request);
    body = JSON.parse(rawBody);
  } catch (error) {
    if (error instanceof RangeError) return jsonResponse({ message: "The request is too large." }, 413);
    return jsonResponse({ message: "The request could not be read." }, 400);
  }
  if (!body || typeof body !== "object" || Array.isArray(body)) {
    return jsonResponse({ message: "The request could not be read." }, 400);
  }
  const action = body.action || "start";
  if (!["start", "poll", "cleanup", "cancel"].includes(action)) {
    return jsonResponse({ message: "This lyric analysis action is not supported." }, 400);
  }
  const apiKey = String(process.env.GEMINI_API_KEY || "").trim();
  if (!apiKey) {
    return jsonResponse({
      message: "Lyric generation is not set up yet. Ask the site owner to finish setup; band members do not need to sign in."
    }, 503);
  }
  if (action === "poll") return handlePoll(body, apiKey);
  if (action === "cleanup") return handleCleanup(body, apiKey);
  if (action === "cancel") return handleCancel(body, apiKey);
  return handleStart(body, context, apiKey);
};
