// pbar shim for Node: report cli-progress / progress values to pbar, unchanged apps.
// `pbar run --shim` loads this via NODE_OPTIONS=--require. It wraps the libraries
// as they are required and sends `pbar set` at most 4 times a second. Any error
// disables it quietly: the app must never notice.
"use strict";
const Module = require("module");
const { spawn, spawnSync } = require("child_process");

const BIN = process.env.PBAR_BIN;
let last = { t: 0, v: null };

function report(value) {
  try {
    const v = Math.max(0, Math.min(1, value));
    const now = Date.now();
    if (v < 1 && (now - last.t < 250 || v === last.v)) return;
    last = { t: now, v };
    const args = ["set", v.toFixed(4)];
    const opts = { stdio: "ignore", env: { ...process.env, PBAR_SRC: "shim" } };
    // the last report waits, so 100% lands before the app exits and `pbar end` runs
    if (v >= 1) spawnSync(BIN, args, opts);
    else spawn(BIN, args, { ...opts, detached: true }).unref();
  } catch (_) {}
}

function after(proto, name, frac) {
  const orig = proto && proto[name];
  if (typeof orig !== "function" || orig.__pbar) return;
  const wrapped = function (...args) {
    const out = orig.apply(this, args);
    try { const v = frac(this); if (v != null && isFinite(v)) report(v); } catch (_) {}
    return out;
  };
  wrapped.__pbar = true;
  proto[name] = wrapped;
}

const patches = {
  "cli-progress": (m) => {
    const frac = (b) => (b.total ? b.value / b.total : null);
    for (const n of ["update", "increment", "stop"]) after(m.SingleBar && m.SingleBar.prototype, n, frac);
    // a MultiBar's bars are GenericBar instances
    for (const n of ["update", "increment"]) after(m.GenericBar && m.GenericBar.prototype, n, frac);
  },
  progress: (m) => {
    const frac = (b) => (b.total ? b.curr / b.total : null);
    for (const n of ["tick", "update"]) after(m.prototype, n, frac);
  },
};

if (BIN && process.env.PBAR_SHIM === "1") {
  const load = Module._load;
  const done = new Set();
  Module._load = function (request, ...rest) {
    const mod = load.call(this, request, ...rest);
    if (patches[request] && !done.has(request)) {
      try { patches[request](mod); done.add(request); } catch (_) {}
    }
    return mod;
  };
}
