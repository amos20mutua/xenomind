import test from "node:test";
import assert from "node:assert/strict";
import transcribeLyrics from "./netlify/functions/transcribe-lyrics.mjs";

const videoUrl = "https://www.youtube.com/watch?v=9hE5-98ZeCg";

function post(body, ip = "198.51.100.10") {
  return new Request("https://xenomind.example/api/transcribe-lyrics", {
    method: "POST",
    headers: {
      "content-type": "application/json",
      origin: "https://xenomind.example"
    },
    body: JSON.stringify(body)
  });
}

async function withApiKey(value, callback) {
  const previous = process.env.GEMINI_API_KEY;
  if (value === undefined) delete process.env.GEMINI_API_KEY;
  else process.env.GEMINI_API_KEY = value;
  try { return await callback(); }
  finally {
    if (previous === undefined) delete process.env.GEMINI_API_KEY;
    else process.env.GEMINI_API_KEY = previous;
  }
}

async function startJob(ip) {
  const originalFetch = globalThis.fetch;
  globalThis.fetch = async (url) => {
    if (String(url).includes("youtube/v3/videos")) {
      return Response.json({ items: [{ status: { privacyStatus: "public" }, snippet: { title: "Song", description: "No lyric section." } }] });
    }
    return Response.json({ id: "v1_abcdefghijk123456789", status: "in_progress" });
  };
  try {
    const response = await transcribeLyrics(post({ videoUrl }, ip), { ip });
    return { response, body: await response.json() };
  } finally {
    globalThis.fetch = originalFetch;
  }
}

test("rejects non-POST requests", async () => {
  const response = await transcribeLyrics(
    new Request("https://xenomind.example/api/transcribe-lyrics"),
    { ip: "198.51.100.1" }
  );
  assert.equal(response.status, 405);
  assert.equal(response.headers.get("allow"), "POST");
});

test("reports a missing Functions key without exposing server configuration", async () => {
  await withApiKey(undefined, async () => {
    const response = await transcribeLyrics(post({ videoUrl }), { ip: "198.51.100.2" });
    const body = await response.json();
    assert.equal(response.status, 503);
    assert.match(body.message, /GEMINI_API_KEY|setup/i);
    assert.equal("apiKey" in body, false);
  });
});

test("starts a signed background job using Google's current REST revision", async () => {
  await withApiKey("test-gemini-key", async () => {
    const originalFetch = globalThis.fetch;
    let requestBody;
    let requestHeaders;
    globalThis.fetch = async (url, init) => {
      if (String(url).includes("youtube/v3/videos")) {
        return Response.json({ items: [{ status: { privacyStatus: "public" }, snippet: { title: "Song", description: "No lyric section." } }] });
      }
      assert.equal(url, "https://generativelanguage.googleapis.com/v1beta/interactions");
      assert.equal(init.method, "POST");
      requestBody = JSON.parse(init.body);
      requestHeaders = init.headers;
      return Response.json({ id: "v1_abcdefghijk123456789", status: "in_progress" });
    };
    try {
      const response = await transcribeLyrics(post({ videoUrl, languageHint: "Swahili" }), { ip: "198.51.100.3" });
      const body = await response.json();
      assert.equal(response.status, 202);
      assert.equal(body.status, "in_progress");
      assert.match(body.jobToken, /^[A-Za-z0-9_-]+\.[A-Za-z0-9_-]+$/);
      assert.equal(body.lyricsSearchUrl, "https://www.google.com/search?q=Song%20lyrics");
      assert.equal(requestHeaders["x-goog-api-key"], "test-gemini-key");
      assert.equal(requestHeaders["Api-Revision"], "2026-05-20");
      assert.equal(requestBody.model, "gemini-3.8-flash");
      assert.equal(requestBody.store, true);
      assert.equal(requestBody.background, true);
      assert.equal(requestBody.input.find((item) => item.type === "video").uri, videoUrl);
      assert.match(requestBody.input.find((item) => item.type === "text").text, /Swahili/);
      assert.doesNotMatch(JSON.stringify(body), /test-gemini-key/);
    } finally {
      globalThis.fetch = originalFetch;
    }
  });
});

test("imports a clearly labeled lyrics block from the public video description immediately", async () => {
  await withApiKey("test-gemini-key", async () => {
    const originalFetch = globalThis.fetch;
    globalThis.fetch = async (url) => {
      assert.match(String(url), /^https:\/\/www\.googleapis\.com\/youtube\/v3\/videos/);
      return Response.json({ items: [{
        id: "9hE5-98ZeCg",
        status: { privacyStatus: "public" },
        snippet: {
          title: "Band song",
          channelTitle: "Band",
          description: "New single out now.\n\nLyrics:\nFirst clear line\nSecond clear line\nThird clear line\nFourth clear line\n\nSubscribe for more."
        }
      }] });
    };
    try {
      const response = await transcribeLyrics(post({ videoUrl }, "198.51.100.17"), { ip: "198.51.100.17" });
      const body = await response.json();
      assert.equal(response.status, 200);
      assert.equal(body.status, "completed");
      assert.equal(body.source, "youtube_description");
      assert.equal(body.videoTitle, "Band song");
      assert.equal(body.channelTitle, "Band");
      assert.equal(body.lyrics, "First clear line\nSecond clear line\nThird clear line\nFourth clear line");
    } finally {
      globalThis.fetch = originalFetch;
    }
  });
});

test("polls a signed background job and reads its completed lyrics", async () => {
  await withApiKey("test-gemini-key", async () => {
    const { response: started, body: startBody } = await startJob("198.51.100.11");
    assert.equal(started.status, 202);
    const originalFetch = globalThis.fetch;
    globalThis.fetch = async (url, init) => {
      assert.match(url, /\/v1beta\/interactions\/v1_abcdefghijk123456789$/);
      assert.equal(init.method, "GET");
      return Response.json({
        status: "completed",
        steps: [{ type: "model_output", content: [{ type: "text", text: "First line\nSecond line" }] }]
      });
    };
    try {
      const response = await transcribeLyrics(post({ action: "poll", jobToken: startBody.jobToken }, "198.51.100.11"), {});
      const body = await response.json();
      assert.equal(response.status, 200);
      assert.equal(body.status, "completed");
      assert.equal(body.lyrics, "First line\nSecond line");
    } finally {
      globalThis.fetch = originalFetch;
    }
  });
});

test("deletes a finished interaction when the browser acknowledges receipt", async () => {
  await withApiKey("test-gemini-key", async () => {
    const { body: startBody } = await startJob("198.51.100.12");
    const originalFetch = globalThis.fetch;
    globalThis.fetch = async (_url, init) => {
      assert.equal(init.method, "DELETE");
      assert.equal(init.headers["Api-Revision"], "2026-05-20");
      return new Response(null, { status: 204 });
    };
    try {
      const response = await transcribeLyrics(post({ action: "cleanup", jobToken: startBody.jobToken }, "198.51.100.12"), {});
      assert.equal(response.status, 200);
      assert.equal((await response.json()).deleted, true);
    } finally {
      globalThis.fetch = originalFetch;
    }
  });
});

test("distinguishes daily project quota exhaustion from transient rate limits", async () => {
  await withApiKey("test-gemini-key", async () => {
    const originalFetch = globalThis.fetch;
    const originalError = console.error;
    globalThis.fetch = async () => Response.json({
      error: {
        code: 429,
        status: "RESOURCE_EXHAUSTED",
        message: "Quota exceeded for requests per day"
      }
    }, { status: 429 });
    console.error = () => {};
    try {
      const response = await transcribeLyrics(post({ videoUrl }, "198.51.100.13"), { ip: "198.51.100.13" });
      const body = await response.json();
      assert.equal(response.status, 429);
      assert.equal(body.retryable, false);
      assert.match(body.message, /project quota|spend limit/i);
    } finally {
      globalThis.fetch = originalFetch;
      console.error = originalError;
    }
  });
});

test("offers one brief automatic retry for an unspecified 429 rate limit", async () => {
  await withApiKey("test-gemini-key", async () => {
    const originalFetch = globalThis.fetch;
    const originalError = console.error;
    globalThis.fetch = async () => Response.json({
      error: { code: 429, status: "RESOURCE_EXHAUSTED", message: "Temporary capacity limit" }
    }, { status: 429 });
    console.error = () => {};
    try {
      const response = await transcribeLyrics(post({ videoUrl }, "198.51.100.14"), { ip: "198.51.100.14" });
      const body = await response.json();
      assert.equal(response.status, 429);
      assert.equal(body.retryable, true);
      assert.equal(body.retryAfterMs, 2000);
    } finally {
      globalThis.fetch = originalFetch;
      console.error = originalError;
    }
  });
});

test("rejects forged job tokens and malformed YouTube links without calling Gemini", async () => {
  await withApiKey("test-gemini-key", async () => {
    const originalFetch = globalThis.fetch;
    globalThis.fetch = async () => { throw new Error("Gemini should not be called"); };
    try {
      const forgedToken = await transcribeLyrics(post({ action: "poll", jobToken: "forged.token" }), {});
      assert.equal(forgedToken.status, 400);
      const invalidUrl = await transcribeLyrics(
        post({ videoUrl: "https://youtu.be/not-a-valid-id" }, "198.51.100.15"),
        { ip: "198.51.100.15" }
      );
      assert.equal(invalidUrl.status, 400);
    } finally {
      globalThis.fetch = originalFetch;
    }
  });
});

test("redacts provider API keys from user-facing errors", async () => {
  await withApiKey("test-gemini-key", async () => {
    const originalFetch = globalThis.fetch;
    const originalError = console.error;
    globalThis.fetch = async () => Response.json({
      error: {
        code: 400,
        status: "INVALID_ARGUMENT",
        message: "Video URL is not public; key was AIza123456789012345678901234567890123"
      }
    }, { status: 400 });
    console.error = () => {};
    try {
      const response = await transcribeLyrics(post({ videoUrl }, "198.51.100.16"), { ip: "198.51.100.16" });
      const body = await response.json();
      assert.equal(response.status, 502);
      assert.match(body.message, /Video URL is not public/);
      assert.doesNotMatch(JSON.stringify(body), /AIza|test-gemini-key/);
    } finally {
      globalThis.fetch = originalFetch;
      console.error = originalError;
    }
  });
});
