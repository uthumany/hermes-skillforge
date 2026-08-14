// Run with: bun run main.bun.js <command> [args]
import { spawnSync } from "bun";
const cmd = process.argv[2] ?? "analyze";
const args = process.argv.slice(3);
const res = spawnSync({ cmd: "python3", args: ["scripts/skillforge.py", cmd, ...args] });
console.log(res.stdout.toString());
if (res.exitCode !== 0) process.exit(res.exitCode);
