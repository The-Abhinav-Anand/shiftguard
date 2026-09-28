import { cp, mkdir, rm } from "node:fs/promises";
import { fileURLToPath } from "node:url";
import path from "node:path";

const frontendRoot = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const source = path.join(frontendRoot, "dist");
const destination = path.resolve(frontendRoot, "..", "shiftguard", "static");

await rm(destination, { recursive: true, force: true });
await mkdir(path.dirname(destination), { recursive: true });
await cp(source, destination, { recursive: true });
process.stdout.write(`Copied built same-origin frontend to ${destination}\n`);
