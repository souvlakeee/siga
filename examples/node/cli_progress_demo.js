const cliProgress = require("cli-progress");
const bar = new cliProgress.SingleBar({}, cliProgress.Presets.shades_classic);
bar.start(60, 0);
let i = 0;
const t = setInterval(() => { bar.increment(); if (++i === 60) { clearInterval(t); bar.stop(); } }, 80);
