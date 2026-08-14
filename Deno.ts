// Run with: deno run --allow-read --allow-write --allow-env Deno.ts <command> [args]
const cmd = Deno.args[0] ?? "analyze";
const args = Deno.args.slice(1);
const proc = new Deno.Command("python3", {
  args: ["scripts/skillforge.py", cmd, ...args],
});
const out = await proc.output();
console.log(new TextDecoder().decode(out.stdout));
if (out.code !== 0) Deno.exit(out.code);
