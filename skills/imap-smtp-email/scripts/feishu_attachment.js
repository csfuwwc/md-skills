#!/usr/bin/env node
/**
 * Download Feishu Bitable attachment by file_token
 * Usage: node feishu_attachment.js <file_token> <filepath>
 */

const fs = require('fs');
const path = require('path');
const https = require('https');
const dotenv = require('dotenv');

dotenv.config();
const APP_ID = process.env.FEISHU_APP_ID || process.env.LARK_APP_ID;
const APP_SECRET = process.env.FEISHU_APP_SECRET || process.env.LARK_APP_SECRET;

async function getTenantToken() {
  return new Promise((resolve, reject) => {
    const data = JSON.stringify({ app_id: APP_ID, app_secret: APP_SECRET });
    const req = https.request({
      hostname: 'open.feishu.cn',
      path: '/open-apis/auth/v3/tenant_access_token/internal',
      method: 'POST',
      headers: { 'Content-Type': 'application/json', 'Content-Length': data.length }
    }, (res) => {
      let body = '';
      res.on('data', d => body += d);
      res.on('end', () => {
        try { resolve(JSON.parse(body).tenant_access_token); }
        catch (e) { reject(e); }
      });
    });
    req.on('error', reject);
    req.write(data);
    req.end();
  });
}

async function downloadFile(token, fileToken, outputPath) {
  return new Promise((resolve, reject) => {
    const url = `https://open.feishu.cn/open-apis/drive/v1/medias/${fileToken}/download`;
    const req = https.get(url, {
      headers: { 'Authorization': `Bearer ${token}` }
    }, (res) => {
      if (res.statusCode === 302 || res.statusCode === 301) {
        // Follow redirect
        const redirectUrl = new URL(res.headers.location, url);
        https.get(redirectUrl, (res2) => {
          const ws = fs.createWriteStream(outputPath);
          res2.pipe(ws);
          ws.on('finish', () => resolve(outputPath));
          ws.on('error', reject);
        }).on('error', reject);
      } else if (res.statusCode === 200) {
        const ws = fs.createWriteStream(outputPath);
        res.pipe(ws);
        ws.on('finish', () => resolve(outputPath));
        ws.on('error', reject);
      } else {
        reject(new Error(`HTTP ${res.statusCode}`));
      }
    });
    req.on('error', reject);
  });
}

async function main() {
  const fileToken = process.argv[2];
  const outputPath = process.argv[3];

  if (!fileToken || !outputPath) {
    console.error('Usage: node feishu_attachment.js <file_token> <filepath>');
    process.exit(1);
  }
  if (!APP_ID || !APP_SECRET) {
    console.error(JSON.stringify({
      success: false,
      error: 'Missing FEISHU_APP_ID/FEISHU_APP_SECRET (or LARK_APP_ID/LARK_APP_SECRET)'
    }));
    process.exit(1);
  }

  try {
    const token = await getTenantToken();
    const saved = await downloadFile(token, fileToken, outputPath);
    console.log(JSON.stringify({ success: true, path: saved }));
  } catch (err) {
    console.error(JSON.stringify({ success: false, error: err.message }));
    process.exit(1);
  }
}

main();
