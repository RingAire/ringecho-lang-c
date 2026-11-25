/**
 * ringecho-lang.org/dist — stable distribution entry for RingEcho releases.
 *
 *   GET /dist/index.txt                 published versions, one per line
 *   GET /dist/v<ver>/<asset>            302 to the GitHub release asset
 *
 * The asset name is validated against the published pattern before the
 * redirect, so this endpoint can never become an open redirector. Both the
 * compiler repository name and the storage host can change here without
 * touching rvm.
 */

const RELEASE_BASE = "https://github.com/RingAire/ringecho-lang-c/releases/download";
const RELEASES_API = "https://api.github.com/repos/RingAire/ringecho-lang-c/releases?per_page=100";
const VERSION = /^v\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?$/;
const ASSET = /^ringecho-\d+\.\d+\.\d+(?:-[0-9A-Za-z.-]+)?-(?:windows|linux|macos)-(?:x86|x64|arm64)\.(?:zip|tar\.gz)$/;
const INDEX_TTL_SECONDS = 300;

export default {
  async fetch(request) {
    const url = new URL(request.url);
    if (request.method !== "GET" && request.method !== "HEAD") {
      return new Response("method not allowed\n", {
        status: 405,
        headers: { allow: "GET, HEAD" },
      });
    }
    if (url.pathname === "/dist/index.txt") return index(request);

    const match = url.pathname.match(/^\/dist\/(v[^/]+)\/([^/]+)$/);
    if (!match || !VERSION.test(match[1]) || !ASSET.test(match[2])) {
      return new Response("not found\n", { status: 404 });
    }
    return Response.redirect(`${RELEASE_BASE}/${match[1]}/${match[2]}`, 302);
  },
};

async function index(request) {
  const cache = caches.default;
  const cached = await cache.match(request);
  if (cached) return cached;

  let response;
  try {
    response = await fetch(RELEASES_API, {
      headers: {
        accept: "application/vnd.github+json",
        "user-agent": "ringecho-dist",
      },
    });
  } catch {
    return new Response("upstream unreachable\n", { status: 502 });
  }
  if (!response.ok) {
    return new Response(`upstream error ${response.status}\n`, { status: 502 });
  }

  const releases = await response.json();
  const versions = releases
    .map((release) => release.tag_name)
    .filter((tag) => VERSION.test(tag))
    .map((tag) => tag.slice(1));

  const body = versions.length ? versions.join("\n") + "\n" : "";
  const result = new Response(body, {
    headers: {
      "content-type": "text/plain; charset=utf-8",
      "cache-control": `public, max-age=${INDEX_TTL_SECONDS}`,
    },
  });
  await cache.put(request, result.clone());
  return result;
}
