const ProgressBar = require("progress");
const bar = new ProgressBar("downloading [:bar] :percent :etas", { total: 60 });
const t = setInterval(() => { bar.tick(); if (bar.complete) clearInterval(t); }, 80);
