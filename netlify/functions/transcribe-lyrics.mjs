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

function jsonResponse(body, status = 200) {
  return new Response(JSON.stringify(body), {
    status,
    headers: {
      "Content-Type": "application/json; charset=utf-8",
      "Cache-Control": "no-store"
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
  if (previous && now - previous < RATE_LIMIT_WINDOW_MS) return false;
  recentRequests.set(key, now);
  if (recentRequests.size > 5000) {
    const oldestKey = recentRequests.keys().next().value;
    if (oldestKey !== undefined) recentRequests.delete(oldestKey);
  }
  return true;
}

function extractOutputText(data) {
  if (!data || typeof data !== "object") return "";
  if (typeof data.output_text === "string") return data.output_text.trim();
  return (Array.isArray(data.steps) ? data.steps : [])
    .filter((step) => step && step.type === "model_output" && Array.isArray(step.content))
    .flatMap((step) => step.content)
    .filter((item) => item && item.type === "text" && typeof item.text === "string")
    .map((item) => item.text)
    .join("\n")
    .trim();
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
  if (contentType !== "application/json") {
    return jsonResponse({ message: "Send the request as JSON." }, 415);
  }
  const contentLengthHeader = request.headers.get("content-length");
  if (contentLengthHeader !== null) {
    const contentLength = Number(contentLengthHeader);
    if (!Number.isSafeInteger(contentLength) || contentLength < 0) {
      return jsonResponse({ message: "The request size could not be read." }, 400);
    }
    if (contentLength > MAX_REQUEST_BYTES) {
      return jsonResponse({ message: "The request is too large." }, 413);
    }
  }
  const apiKey = process.env.GEMINI_API_KEY;
  if (!apiKey) {
    return jsonResponse({
      message: "Lyric generation is not set up yet. Ask the site owner to finish setup; band members do not need to sign in."
    }, 503);
  }
  let body;
  try {
    const rawBody = await readLimitedBody(request);
    body = JSON.parse(rawBody);
  } catch (error) {
    if (error instanceof RangeError) {
      return jsonResponse({ message: "The request is too large." }, 413);
    }
    return jsonResponse({ message: "The request could not be read." }, 400);
  }
  if (!body || typeof body !== "object" || Array.isArray(body)) {
    return jsonResponse({ message: "The request could not be read." }, 400);
  }

  const videoId = youtubeVideoId(String(body.videoUrl || ""));
  if (!videoId) {
    return jsonResponse({ message: "Use a public YouTube video link." }, 400);
  }
  if (!claimRateLimit(context.ip)) {
    return jsonResponse({ message: "Please wait a few seconds before generating another lyric draft." }, 429);
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
  const controller = new AbortController();
  const timeout = setTimeout(() => controller.abort(), 55000);

  try {
    const upstream = await fetch("https://generativelanguage.googleapis.com/v1beta/interactions", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "x-goog-api-key": apiKey
      },
      body: JSON.stringify({
        model: "gemini-3.8-flash",
        store: false,
        input: [
          { type: "text", text: prompt },
          { type: "video", uri: "https://www.youtube.com/watch?v=" + videoId }
        ],
        generation_config: {
          thinking_level: "low",
          max_output_tokens: 16000
        }
      }),
      signal: controller.signal
    });
    let result = {};
    try { result = await upstream.json(); }
    catch (_error) { /* Use the status-based message below. */ }

    if (!upstream.ok) {
      const message = upstream.status === 429
        ? "The lyric generator is at its request limit. Try again later."
        : upstream.status === 400 || upstream.status === 404
          ? "This video could not be analyzed. Check the link and make sure the video is public."
          : upstream.status === 401 || upstream.status === 403
            ? "The lyric generator's server key is invalid or does not have API access."
            : "The lyric generator is temporarily unavailable. Try again later.";
      return jsonResponse({ message }, upstream.status === 429 ? 429 : 502);
    }
    if (!result || typeof result !== "object" || Array.isArray(result)) {
      return jsonResponse({ message: "The lyric generator returned an unreadable response." }, 502);
    }
    if (result.status && result.status !== "completed") {
      return jsonResponse({ message: "The lyric draft did not finish. Try again or use a shorter video." }, 502);
    }
    const lyrics = extractOutputText(result);
    if (!lyrics) {
      return jsonResponse({ message: "No clear vocals were detected in this video." }, 422);
    }
    if (lyrics.length > MAX_LYRIC_CHARACTERS) {
      return jsonResponse({ message: "The lyric draft is too long for one note. Use a shorter video." }, 422);
    }
    return jsonResponse({ lyrics });
  } catch (error) {
    if (error && error.name === "AbortError") {
      return jsonResponse({ message: "The video took too long to analyze. Try again or use a shorter video." }, 504);
    }
    console.error("XENOMIND lyric generation request failed.", error && error.name || "unknown error");
    return jsonResponse({ message: "The lyric generator is temporarily unavailable. Try again later." }, 502);
  } finally {
    clearTimeout(timeout);
  }
};
