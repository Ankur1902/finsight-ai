// Encodes out/walkthrough.webm to MP4, speed-ramping the idle windows logged by record.js
// (waiting on responses/navigation) so the final cut stays tight.
const fs = require("fs");
const path = require("path");
const { execFileSync } = require("child_process");
const OUT = path.join(__dirname, "out");
const src = path.join(OUT, "walkthrough.webm");
const dur = parseFloat(execFileSync("ffprobe", ["-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", src]).toString());
const idle = JSON.parse(fs.readFileSync(path.join(OUT, "idle.json"), "utf8")).filter(([a, b]) => b - a > 1.2).sort((x, y) => x[0] - y[0]);
const KEEP = 0.9; // seconds of each idle window that remain (sped up)
const parts = [];
let cursor = 0;
for (const [a, b] of idle) {
  if (a > cursor) parts.push({ a: cursor, b: a, speed: 1 });
  parts.push({ a, b, speed: (b - a) / KEEP });
  cursor = b;
}
if (cursor < dur) parts.push({ a: cursor, b: dur, speed: 1 });
const f = parts.map((p, i) => `[0:v]trim=start=${p.a}:end=${p.b},setpts=(PTS-STARTPTS)/${p.speed.toFixed(3)}[v${i}]`);
const filter = f.join(";") + `;${parts.map((_, i) => `[v${i}]`).join("")}concat=n=${parts.length}:v=1:a=0,fps=30,` +
  `fade=t=in:st=0:d=0.6,format=yuv420p[out]`;
const out = path.join(OUT, "finsight-demo.mp4");
execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-i", src, "-filter_complex", filter, "-map", "[out]",
  "-c:v", "libx264", "-preset", "slow", "-crf", "27", "-movflags", "+faststart", out]);
console.log("encoded", out, execFileSync("ffprobe", ["-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", out]).toString().trim() + "s");
