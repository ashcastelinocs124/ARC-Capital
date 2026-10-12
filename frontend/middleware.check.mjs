import assert from "node:assert/strict";
const m = await import("./middleware.ts");
const req = (auth) => new Request("https://x.test/api/admin/agents/catalog.json", { headers: auth ? { authorization: auth } : {} });
const basic = (u, p) => "Basic " + btoa(`${u}:${p}`);
process.env.ADMIN_PASSWORD = "s3cret:with:colons";
assert.equal(m.default(req()).status, 401);                                   // no credentials
assert.equal(m.default(req(basic("a", "wrong"))).status, 401);                // wrong password
assert.equal(m.default(req("Basic !!!notbase64")).status, 401);               // garbage header
assert.equal(m.default(req("Bearer abc")).status, 401);                       // wrong scheme
const ok = m.default(req(basic("anyone", "s3cret:with:colons")));             // right password (contains colons)
assert.equal(ok.headers.get("x-middleware-next"), "1");
assert.equal(m.default(req(basic("", "s3cret:with:colons"))).headers.get("x-middleware-next"), "1");
assert.ok(m.default(req()).headers.get("www-authenticate").startsWith("Basic"));
delete process.env.ADMIN_PASSWORD;                                            // unset = deny everything (fail closed)
assert.equal(m.default(req(basic("a", ""))).status, 401);
assert.equal(m.default(req(basic("a", "undefined"))).status, 401);
process.env.ADMIN_PASSWORD = "";                                              // empty = deny too
assert.equal(m.default(req(basic("a", ""))).status, 401);
console.log("middleware: all checks passed");
