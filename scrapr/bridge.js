#!/usr/bin/env node
// Bridge scrapr -> JSON (dipanggil dari Python selfbot)
// Usage: node scrapr_bridge.js <platform.method> <url>
const scrapr = require("/home/agentuser/apps/selfbot/scrapr/node_modules/@coflyn/scrapr");

const [, , action, url] = process.argv;
const [platform, method] = action.split(".");

(async () => {
  try {
    const mod = scrapr[platform];
    if (!mod) throw new Error("platform gak ada: " + platform);
    const fn = method ? mod[method] : mod.default || Object.values(mod)[0];
    if (typeof fn !== "function") throw new Error("method gak ada: " + action);
    const res = await fn(url);
    console.log(JSON.stringify(res));
  } catch (e) {
    console.log(JSON.stringify({ status: false, error: e.message }));
  }
})();
