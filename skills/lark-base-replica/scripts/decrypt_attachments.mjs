#!/usr/bin/env node
import { createCipheriv, createDecipheriv, createHash, randomBytes } from "node:crypto";
import { access, chmod, mkdir, readFile, writeFile } from "node:fs/promises";
import path from "node:path";


function decryptAesGcm(encrypted, secret, nonce) {
  const key = Buffer.from(secret, "base64");
  const iv = Buffer.from(nonce, "base64");
  const tag = encrypted.subarray(encrypted.length - 16);
  const ciphertext = encrypted.subarray(0, encrypted.length - 16);
  const decipher = createDecipheriv("aes-256-gcm", key, iv);
  decipher.setAuthTag(tag);
  return Buffer.concat([decipher.update(ciphertext), decipher.final()]);
}


function extensionFor(data) {
  if (data.subarray(0, 8).equals(Buffer.from("89504e470d0a1a0a", "hex"))) return ".png";
  if (data.length >= 12 && data.subarray(8, 12).toString("ascii") === "WEBP") return ".webp";
  if (data.subarray(0, 2).equals(Buffer.from("ffd8", "hex"))) return ".jpg";
  throw new Error("unsupported decrypted file type");
}


function safeMetadata(mapping) {
  const { url, secret, nonce, ...safe } = mapping;
  return safe;
}


function fidelityMetadata(data) {
  const extension = extensionFor(data);
  const result = {
    format: extension.slice(1),
    plain_bytes: data.length,
    sha256: createHash("sha256").update(data).digest("hex"),
  };
  if (extension === ".png" && data.length >= 24) {
    result.width = data.readUInt32BE(16);
    result.height = data.readUInt32BE(20);
  }
  return result;
}


function selfTest() {
  const key = randomBytes(32);
  const nonce = randomBytes(12);
  const plain = Buffer.from("89504e470d0a1a0a0000000d494844520000000100000001", "hex");
  const cipher = createCipheriv("aes-256-gcm", key, nonce);
  const encrypted = Buffer.concat([cipher.update(plain), cipher.final(), cipher.getAuthTag()]);
  const actual = decryptAesGcm(encrypted, key.toString("base64"), nonce.toString("base64"));
  const metadata = fidelityMetadata(actual);
  const safe = safeMetadata({ file_token: "box_test", url: "secret-url", secret: "key", nonce: "iv" });
  if (!actual.equals(plain) || metadata.format !== "png" || metadata.width !== 1 || metadata.height !== 1) throw new Error("self-test failed");
  console.log(JSON.stringify({ ok: true, ...metadata, secret_fields_removed: !("url" in safe || "secret" in safe || "nonce" in safe) }));
}


async function downloadAll(mapPath, outputDir, concurrency) {
  const parsed = JSON.parse(await readFile(mapPath, "utf8"));
  const mappings = Array.isArray(parsed) ? parsed : [parsed];
  await mkdir(outputDir, { recursive: true });
  let cursor = 0;
  const files = [];
  const failures = [];

  async function worker() {
    while (true) {
      const index = cursor++;
      if (index >= mappings.length) return;
      const mapping = mappings[index];
      try {
        let outputPath;
        for (const extension of [".png", ".webp", ".jpg"]) {
          const candidate = path.join(outputDir, mapping.file_token + extension);
          try { await access(candidate); outputPath = candidate; break; } catch {}
        }
        let plain;
        if (outputPath) {
          plain = await readFile(outputPath);
        } else {
          const response = await fetch(mapping.url, {
            headers: { "user-agent": "Mozilla/5.0" },
            signal: AbortSignal.timeout(60_000),
          });
          if (!response.ok) throw new Error(`HTTP ${response.status}`);
          const encrypted = Buffer.from(await response.arrayBuffer());
          plain = decryptAesGcm(encrypted, mapping.secret, mapping.nonce);
          outputPath = path.join(outputDir, mapping.file_token + extensionFor(plain));
          await writeFile(outputPath, plain, { mode: 0o600 });
        }
        files.push({ ...safeMetadata(mapping), output_path: outputPath, ...fidelityMetadata(plain) });
      } catch (error) {
        failures.push({ file_token: mapping.file_token, error: String(error?.message || error) });
      }
    }
  }

  await Promise.all(Array.from({ length: concurrency }, worker));
  files.sort((left, right) => left.file_token.localeCompare(right.file_token));
  const manifestPath = path.join(outputDir, "download-manifest.json");
  await writeFile(manifestPath, JSON.stringify({ files, failures }), { mode: 0o600 });
  await chmod(manifestPath, 0o600);
  console.log(JSON.stringify({ requested: mappings.length, downloaded: files.length, failed: failures.length, manifest_path: manifestPath }));
  if (failures.length) process.exitCode = 1;
}


const args = process.argv.slice(2);
if (args[0] === "--self-test") {
  selfTest();
} else if (args.length === 3 && Number.isInteger(Number(args[2])) && Number(args[2]) > 0) {
  await downloadAll(args[0], args[1], Number(args[2]));
} else {
  console.error("usage: decrypt_attachments.mjs <mapping.json> <output-dir> <concurrency>");
  process.exitCode = 2;
}
