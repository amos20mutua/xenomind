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

test("sends the public YouTube URI to Gemini and reads Interactions steps", async () => {
  await withApiKey("test-gemini-key", async () => {
    const originalFetch = globalThis.fetch;
    let requestBody;
    let requestKey;
    globalThis.fetch = async (url, init) => {
      assert.equal(url, "https://generativelanguage.googleapis.com/v1beta/interactions");
      requestBody = JSON.parse(init.body);
      requestKey = init.headers["x-goog-api-key"];
      return Response.json({
        status: "completed",
        steps: [{ type: "model_output", content: [{ type: "text", text: "First line\nSecond line" }] }]
      });
    };
    try {
      const response = await transcribeLyrics(post({ videoUrl, languageHint: "Swahili" }), { ip: "198.51.100.3" });
      const body = await response.json();
      assert.equal(response.status, 200);
      assert.equal(body.lyrics, "First line\nSecond line");
      assert.equal(requestKey, "test-gemini-key");
      assert.equal(requestBody.model, "gemini-3.8-flash");
      assert.equal(requestBody.store, false);
      assert.equal(requestBody.input.find((item) => item.type === "video").uri, videoUrl);
      assert.match(requestBody.input.find((item) => item.type === "text").text, /Swahili/);
      assert.doesNotMatch(JSON.stringify(body), /test-gemini-key/);
    } finally {
      globalThis.fetch = originalFetch;
    }
  });
});

test("returns Gemini's safe diagnostic when the API rejects a request", async () => {
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
      const response = await transcribeLyrics(post({ videoUrl }), { ip: "198.51.100.4" });
      const body = await response.json();
      assert.equal(response.status, 502);
      assert.match(body.message, /Video URL is not public/);
      assert.doesNotMatch(body.message, /AIza/);
      assert.doesNotMatch(JSON.stringify(body), /test-gemini-key/);
    } finally {
      globalThis.fetch = originalFetch;
      console.error = originalError;
    }
  });
});

test("returns the legacy text output shape when it is served by a compatibility endpoint", async () => {
  await withApiKey("test-gemini-key", async () => {
    const originalFetch = globalThis.fetch;
    globalThis.fetch = async () => Response.json({
      status: "completed",
      outputs: [{ type: "text", text: "Legacy response" }]
    });
    try {
      const response = await transcribeLyrics(post({ videoUrl }), { ip: "198.51.100.6" });
      assert.equal(response.status, 200);
      assert.equal((await response.json()).lyrics, "Legacy response");
    } finally {
      globalThis.fetch = originalFetch;
    }
  });
});

test("turns an upstream timeout into a clear retry message", async () => {
  await withApiKey("test-gemini-key", async () => {
    const originalFetch = globalThis.fetch;
    globalThis.fetch = async () => {
      const error = new Error("upstream timed out");
      error.name = "AbortError";
      throw error;
    };
    try {
      const response = await transcribeLyrics(post({ videoUrl }), { ip: "198.51.100.7" });
      assert.equal(response.status, 504);
      assert.match((await response.json()).message, /too long to analyze/i);
    } finally {
      globalThis.fetch = originalFetch;
    }
  });
});

test("rejects malformed YouTube links before contacting Gemini", async () => {
  await withApiKey("test-gemini-key", async () => {
    const originalFetch = globalThis.fetch;
    globalThis.fetch = async () => { throw new Error("Gemini should not be called"); };
    try {
      const response = await transcribeLyrics(
        post({ videoUrl: "https://youtu.be/not-a-valid-id" }),
        { ip: "198.51.100.5" }
      );
      assert.equal(response.status, 400);
    } finally {
      globalThis.fetch = originalFetch;
    }
  });
});
