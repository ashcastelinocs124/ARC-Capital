import assert from "node:assert/strict";
const m = await import("./middleware.ts");
const api = "https://x.test/api/admin/agents/catalog.json";
const req = (auth, url = api, extra = {}) =>
  new Request(url, { ...extra, headers: { ...(auth ? { authorization: auth } : {}), ...(extra.headers || {}) } });
const basic = (u, p) => "Basic " + btoa(`${u}:${p}`);
const passed = (r) => r.headers.get("x-middleware-next") === "1";
const signIn = (password, type = "application/json") =>
  m.default(new Request("https://x.test/api/admin/session", { method: "POST", headers: { "content-type": type }, body: JSON.stringify({ password }) }));

process.env.ADMIN_PASSWORD = "s3cret:with:colons";
// Basic auth (curl/scripts)
assert.equal((await m.default(req())).status, 401);                                  // no credentials
assert.equal((await m.default(req(basic("a", "wrong")))).status, 401);               // wrong password
assert.equal((await m.default(req("Basic !!!notbase64"))).status, 401);              // garbage header
assert.equal((await m.default(req("Bearer abc"))).status, 401);                      // wrong scheme
assert.ok(passed(await m.default(req(basic("anyone", "s3cret:with:colons")))));      // right password (contains colons)
assert.ok(passed(await m.default(req(basic("", "s3cret:with:colons")))));
assert.equal((await m.default(req())).headers.get("www-authenticate"), null);        // never trigger the browser popup

// pages redirect to the sign-in page; the sign-in page itself is open
const page = await m.default(req(null, "https://x.test/admin?tab=x"));
assert.equal(page.status, 302);
assert.equal(page.headers.get("location"), "/admin/login?next=%2Fadmin%3Ftab%3Dx");
assert.ok(passed(await m.default(req(null, "https://x.test/admin/login"))));
assert.equal((await m.default(req(null, "https://x.test/admin/chunks/docs-1.js"))).status, 401); // code chunk: 401, not a redirect

// sign-in → cookie → access
assert.equal((await signIn("wrong")).status, 401);
assert.equal((await signIn("s3cret:with:colons", "text/plain")).status, 415);         // forms can't post JSON
const ok = await signIn("s3cret:with:colons");
assert.equal(ok.status, 200);
const set = ok.headers.get("set-cookie");
assert.match(set, /^arc_admin=\d+\.[\w-]+; Path=\/; Max-Age=43200; HttpOnly; Secure; SameSite=Lax$/);
const jar = set.split(";")[0];
assert.ok(passed(await m.default(req(null, api, { headers: { cookie: `x=1; ${jar}` } }))));
assert.equal((await m.default(req(null, "https://x.test/api/admin/session", { headers: { cookie: jar } }))).status, 200);
const [, value] = jar.split("=");
const [exp, sig] = value.split(".");
assert.equal((await m.default(req(null, api, { headers: { cookie: `arc_admin=${Number(exp) + 1}.${sig}` } }))).status, 401); // tampered expiry
const past = Math.floor(Date.now() / 1000) - 10;
assert.equal((await m.default(req(null, api, { headers: { cookie: `arc_admin=${past}.${await m.sign(past, "s3cret:with:colons")}` } }))).status, 401); // expired
process.env.ADMIN_PASSWORD = "new-password";                                       // password change signs everyone out
assert.equal((await m.default(req(null, api, { headers: { cookie: jar } }))).status, 401);
assert.match((await m.default(new Request("https://x.test/api/admin/logout", { method: "POST" }))).headers.get("set-cookie"), /Max-Age=0/);

delete process.env.ADMIN_PASSWORD;                                                  // unset = deny everything (fail closed)
assert.equal((await m.default(req(basic("a", "")))).status, 401);
assert.equal((await m.default(req(basic("a", "undefined")))).status, 401);
assert.equal((await signIn("")).status, 503);
process.env.ADMIN_PASSWORD = "";                                                    // empty = deny too
assert.equal((await m.default(req(basic("a", "")))).status, 401);
console.log("middleware: all checks passed");
