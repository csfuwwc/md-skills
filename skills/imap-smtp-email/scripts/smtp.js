#!/usr/bin/env node

/**
 * SMTP Email CLI
 * Send email via SMTP protocol. Works with Gmail, Outlook, 163.com, and any standard SMTP server.
 * Supports attachments, HTML content, and multiple recipients.
 */

const nodemailer = require('nodemailer');
const path = require('path');
const os = require('os');
const fs = require('fs');
const config = require('./config');
const SEND_STATE_FILE = path.join(os.homedir(), '.config', 'imap-smtp-email', 'send_state.json');

function sleep(ms) {
  return new Promise(resolve => setTimeout(resolve, ms));
}

function parseIntOpt(value, fallback) {
  const n = parseInt(value, 10);
  return Number.isFinite(n) ? n : fallback;
}

function isGmailSmtp() {
  return (config.smtp.host || '').toLowerCase().includes('gmail.com');
}

function splitRecipients(value) {
  if (!value) return [];
  return String(value).split(',').map(s => s.trim()).filter(Boolean);
}

function getRecipientCount(options) {
  return (
    splitRecipients(options.to).length +
    splitRecipients(options.cc).length +
    splitRecipients(options.bcc).length
  );
}

function loadSendState() {
  try {
    if (fs.existsSync(SEND_STATE_FILE)) {
      return JSON.parse(fs.readFileSync(SEND_STATE_FILE, 'utf8'));
    }
  } catch (_) {}
  return {};
}

function saveSendState(state) {
  const dir = path.dirname(SEND_STATE_FILE);
  if (!fs.existsSync(dir)) fs.mkdirSync(dir, { recursive: true, mode: 0o700 });
  fs.writeFileSync(SEND_STATE_FILE, JSON.stringify(state, null, 2), { mode: 0o600 });
}

function accountKey() {
  return `${config.smtp.host || 'smtp'}::${config.smtp.user || 'user'}`;
}

function getGuardrailConfig(options) {
  const gmail = isGmailSmtp();
  return {
    minIntervalMs: parseIntOpt(options['min-interval-ms'], gmail ? 5000 : 1000),
    maxPerHour: parseIntOpt(options['max-per-hour'], gmail ? 120 : 500),
    maxPer24h: parseIntOpt(options['max-per-24h'], gmail ? 400 : 2000),
    maxRecipientsPerMessage: parseIntOpt(options['max-recipients'], gmail ? 50 : 100),
  };
}

function pruneHistory(arr, nowMs) {
  if (!Array.isArray(arr)) return [];
  const dayAgo = nowMs - 24 * 60 * 60 * 1000;
  return arr.filter(ts => typeof ts === 'number' && ts >= dayAgo);
}

function checkAndPrepareSend(options) {
  const nowMs = Date.now();
  const cfg = getGuardrailConfig(options);
  const recipients = getRecipientCount(options);
  const state = loadSendState();
  const key = accountKey();
  const entry = state[key] || { sends: [], blockedUntil: 0, lastSendAt: 0 };
  entry.sends = pruneHistory(entry.sends, nowMs);

  if (entry.blockedUntil && nowMs < entry.blockedUntil) {
    const mins = Math.ceil((entry.blockedUntil - nowMs) / 60000);
    throw new Error(`Sending is temporarily blocked by safety guard for this account. Retry in about ${mins} minute(s).`);
  }

  if (recipients > cfg.maxRecipientsPerMessage) {
    throw new Error(`Recipient count (${recipients}) exceeds safe limit (${cfg.maxRecipientsPerMessage}). Split into smaller batches.`);
  }

  const hourAgo = nowMs - 60 * 60 * 1000;
  const sentLastHour = entry.sends.filter(ts => ts >= hourAgo).length;
  if (sentLastHour >= cfg.maxPerHour) {
    throw new Error(`Rate limit reached: ${sentLastHour} emails sent in last hour (limit ${cfg.maxPerHour}).`);
  }

  if (entry.sends.length >= cfg.maxPer24h) {
    throw new Error(`Daily rolling limit reached: ${entry.sends.length} emails in last 24h (limit ${cfg.maxPer24h}).`);
  }

  const waitMs = Math.max(0, (entry.lastSendAt || 0) + cfg.minIntervalMs - nowMs);
  return { state, key, entry, waitMs };
}

function markSendSuccess(state, key, entry) {
  const nowMs = Date.now();
  entry.lastSendAt = nowMs;
  entry.sends = pruneHistory(entry.sends, nowMs);
  entry.sends.push(nowMs);
  entry.blockedUntil = 0;
  state[key] = entry;
  saveSendState(state);
}

function maybeMarkBlocked(state, key, entry, err) {
  const msg = String(err && err.message ? err.message : err || '').toLowerCase();
  const isSuspicious =
    /daily user sending quota exceeded|rate limit|too many|temporar|suspicious|5\.7\.[01]|4\.7\.0|421|450|452|454/.test(msg);
  if (!isSuspicious) return;

  // Conservative: 24h for clear quota/suspension signals, otherwise 30m.
  const longBlock = /quota exceeded|reached a limit|limit for sending email|24 hour/.test(msg);
  entry.blockedUntil = Date.now() + (longBlock ? 24 * 60 * 60 * 1000 : 30 * 60 * 1000);
  state[key] = entry;
  saveSendState(state);
}

function validateReadPath(inputPath) {
  let realPath;
  try {
    realPath = fs.realpathSync(inputPath);
  } catch {
    realPath = path.resolve(inputPath);
  }

  if (!config.allowedReadDirs.length) {
    throw new Error('ALLOWED_READ_DIRS not set in .env. File read operations are disabled.');
  }

  const allowedDirs = config.allowedReadDirs.map(d =>
    path.resolve(d.replace(/^~/, os.homedir()))
  );

  const allowed = allowedDirs.some(dir =>
    realPath === dir || realPath.startsWith(dir + path.sep)
  );

  if (!allowed) {
    throw new Error(`Access denied: '${inputPath}' is outside allowed read directories`);
  }

  return realPath;
}

// Parse command-line arguments
function parseArgs() {
  const args = process.argv.slice(2);
  const command = args[0];
  const options = {};
  const positional = [];

  for (let i = 1; i < args.length; i++) {
    const arg = args[i];
    if (arg.startsWith('--')) {
      const key = arg.slice(2);
      const value = args[i + 1];
      if (options[key] !== undefined) {
        // Already set: convert to array or append
        if (Array.isArray(options[key])) {
          options[key].push(value);
        } else {
          options[key] = [options[key], value];
        }
      } else {
        if (value && !value.startsWith('--')) {
          options[key] = value;
        } else {
          options[key] = true;
        }
      }
      if (value && !value.startsWith('--')) i++;
    } else {
      positional.push(arg);
    }
  }

  return { command, options, positional };
}

// Create SMTP transporter
function createTransporter() {
  if (!config.smtp.host || !config.smtp.user || !config.smtp.pass) {
    throw new Error('Missing SMTP configuration. Check your config at ~/.config/imap-smtp-email/.env');
  }

  return nodemailer.createTransport({
    host: config.smtp.host,
    port: config.smtp.port,
    secure: config.smtp.secure,
    auth: {
      user: config.smtp.user,
      pass: config.smtp.pass,
    },
    tls: {
      rejectUnauthorized: config.smtp.rejectUnauthorized,
    },
  });
}

// Send email
async function sendEmail(options) {
  const guard = checkAndPrepareSend(options);
  if (guard.waitMs > 0) {
    await sleep(guard.waitMs);
  }

  const transporter = createTransporter();

  // Verify connection
  try {
    await transporter.verify();
    console.error('SMTP server is ready to send');
  } catch (err) {
    throw new Error(`SMTP connection failed: ${err.message}`);
  }

  const mailOptions = {
    from: options.from || config.smtp.from,
    to: options.to,
    cc: options.cc || undefined,
    bcc: options.bcc || undefined,
    subject: options.subject || '(no subject)',
    text: options.text || undefined,
    html: options.html || undefined,
    attachments: options.attachments || [],
  };

  // If neither text nor html provided, use default text
  if (!mailOptions.text && !mailOptions.html) {
    mailOptions.text = options.body || '';
  }

  try {
    const info = await transporter.sendMail(mailOptions);
    markSendSuccess(guard.state, guard.key, guard.entry);
    return {
      success: true,
      messageId: info.messageId,
      response: info.response,
      to: mailOptions.to,
    };
  } catch (err) {
    maybeMarkBlocked(guard.state, guard.key, guard.entry, err);
    throw err;
  }
}

// Read file content for attachments
function readAttachment(filePath) {
  // Feishu file_token (alphanumeric, typically 27-40 chars)
  if (/^[A-Za-z0-9]{20,}$/.test(filePath)) {
    return { isFeishuToken: true, fileToken: filePath };
  }
  // Feishu download URL
  if (filePath.startsWith('https://open.feishu.cn/open-apis/drive/')) {
    return { isFeishuUrl: true, url: filePath };
  }
  validateReadPath(filePath);
  if (!fs.existsSync(filePath)) {
    throw new Error(`Attachment file not found: ${filePath}`);
  }
  return {
    filename: path.basename(filePath),
    path: path.resolve(filePath),
  };
}

// Download Feishu attachment to temp file
async function downloadFeishuAttachment(fileToken, destPath) {
  const { execSync } = require('child_process');
  const scriptPath = require('path').join(__dirname, 'feishu_attachment.js');
  const result = execSync(`node "${scriptPath}" "${fileToken}" "${destPath}"`, { encoding: 'utf8' });
  const parsed = JSON.parse(result);
  if (!parsed.success) throw new Error(parsed.error);
  return parsed.path;
}

// Download Feishu URL attachment (extract token from URL, use feishu_attachment.js)
async function downloadFeishuUrlAttachment(url, destPath) {
  const match = url.match(/\/medias\/([A-Za-z0-9]+)\/download/);
  if (!match) throw new Error('Invalid Feishu download URL');
  return downloadFeishuAttachment(match[1], destPath);
}

// Send email with file content
async function sendEmailWithContent(options) {
  const tempFiles = [];
  // Handle attachments
  if (options.attach) {
    const attachFiles = Array.isArray(options.attach)
      ? options.attach
      : options.attach.split(',').map(f => f.trim());
    
    // Resolve Feishu attachments to local files first
    const os = require('os');
    const resolvedPaths = [];
    for (const f of attachFiles) {
      const att = readAttachment(f);
      if (att.isFeishuToken) {
        const tmpDir = config.allowedWriteDirs[0] || '/tmp';
        const tmpFile = require('path').join(tmpDir, `feishu_att_${Date.now()}_${Math.random().toString(36).slice(2)}`);
        try {
          await downloadFeishuAttachment(att.fileToken, tmpFile);
          resolvedPaths.push({ filename: require('path').basename(tmpFile), path: tmpFile, _tmp: tmpFile });
          tempFiles.push(tmpFile);
        } catch (err) {
          throw new Error(`Failed to download Feishu attachment ${f}: ${err.message}`);
        }
      } else if (att.isFeishuUrl) {
        const tmpDir = config.allowedWriteDirs[0] || '/tmp';
        const tmpFile = require('path').join(tmpDir, `feishu_att_${Date.now()}_${Math.random().toString(36).slice(2)}`);
        try {
          await downloadFeishuUrlAttachment(att.url, tmpFile);
          resolvedPaths.push({ filename: require('path').basename(tmpFile), path: tmpFile, _tmp: tmpFile });
          tempFiles.push(tmpFile);
        } catch (err) {
          throw new Error(`Failed to download Feishu attachment from URL: ${err.message}`);
        }
      } else {
        resolvedPaths.push(att);
      }
    }
    
    options.attachments = resolvedPaths;
  }

  try {
    return await sendEmail(options);
  } finally {
    for (const tmp of tempFiles) {
      try { require('fs').unlinkSync(tmp); } catch (e) {}
    }
  }
}

// Test SMTP connection
async function testConnection() {
  const transporter = createTransporter();

  try {
    await transporter.verify();
    const info = await transporter.sendMail({
      from: config.smtp.from || config.smtp.user,
      to: config.smtp.user,
      subject: 'SMTP Connection Test',
      text: 'This is a test email from the IMAP/SMTP email skill.',
      html: '<p>This is a <strong>test email</strong> from the IMAP/SMTP email skill.</p>',
    });

    return {
      success: true,
      message: 'SMTP connection successful',
      messageId: info.messageId,
    };
  } catch (err) {
    throw new Error(`SMTP test failed: ${err.message}`);
  }
}

// Display accounts in a formatted table
function displayAccounts(accounts, configPath) {
  // Handle no config file case
  if (!configPath) {
    console.error('No configuration file found.');
    console.error('Run "bash setup.sh" to configure your email account.');
    process.exit(1);
  }

  // Handle no accounts case
  if (accounts.length === 0) {
    console.error(`No accounts configured in ${configPath}`);
    process.exit(0);
  }

  // Display header with config path
  console.log(`Configured accounts (from ${configPath}):\n`);

  // Calculate column widths
  const maxNameLen = Math.max(7, ...accounts.map(a => a.name.length)); // 7 = 'Account'.length
  const maxEmailLen = Math.max(5, ...accounts.map(a => a.email.length)); // 5 = 'Email'.length
  const maxImapLen = Math.max(4, ...accounts.map(a => a.imapHost.length)); // 4 = 'IMAP'.length
  const maxSmtpLen = Math.max(4, ...accounts.map(a => a.smtpHost.length)); // 4 = 'SMTP'.length

  // Table header
  const header = `  ${padRight('Account', maxNameLen)}  ${padRight('Email', maxEmailLen)}  ${padRight('IMAP', maxImapLen)}  ${padRight('SMTP', maxSmtpLen)}  Status`;
  console.log(header);

  // Separator line
  const separator = '  ' + '─'.repeat(maxNameLen) + '  ' + '─'.repeat(maxEmailLen) + '  ' + '─'.repeat(maxImapLen) + '  ' + '─'.repeat(maxSmtpLen) + '  ' + '────────────────';
  console.log(separator);

  // Table rows
  for (const account of accounts) {
    const statusIcon = account.isComplete ? '✓' : '⚠';
    const statusText = account.isComplete ? 'Complete' : 'Incomplete';
    const row = `  ${padRight(account.name, maxNameLen)}  ${padRight(account.email, maxEmailLen)}  ${padRight(account.imapHost, maxImapLen)}  ${padRight(account.smtpHost, maxSmtpLen)}  ${statusIcon} ${statusText}`;
    console.log(row);
  }

  // Footer
  console.log(`\n  ${accounts.length} account${accounts.length > 1 ? 's' : ''} total`);
}

// Helper: right-pad a string to a fixed width
function padRight(str, len) {
  return (str + ' '.repeat(len)).slice(0, len);
}

// Main CLI handler
async function main() {
  const { command, options, positional } = parseArgs();

  try {
    let result;

    switch (command) {
      case 'send':
        if (!options.to) {
          throw new Error('Missing required option: --to <email>');
        }
        if (!options.subject && !options['subject-file']) {
          throw new Error('Missing required option: --subject <text> or --subject-file <file>');
        }

        // Read subject from file if specified
        if (options['subject-file']) {
          validateReadPath(options['subject-file']);
          options.subject = fs.readFileSync(options['subject-file'], 'utf8').trim();
        }

        // Read body from file if specified
        if (options['body-file']) {
          validateReadPath(options['body-file']);
          const content = fs.readFileSync(options['body-file'], 'utf8');
          if (options['body-file'].endsWith('.html') || options.html) {
            options.html = content;
          } else {
            options.text = content;
          }
        } else if (options['html-file']) {
          validateReadPath(options['html-file']);
          options.html = fs.readFileSync(options['html-file'], 'utf8');
        } else if (options.body) {
          options.text = options.body;
        }

        result = await sendEmailWithContent(options);
        break;

      case 'test':
        result = await testConnection();
        break;

      case 'list-accounts':
        {
          const { listAccounts } = require('./config');
          const { accounts, configPath } = listAccounts();
          displayAccounts(accounts, configPath);
        }
        return;  // Exit early, no JSON output

      default:
        console.error('Unknown command:', command);
        console.error('Available commands: send, test, list-accounts');
        console.error('\nUsage:');
        console.error('  send   --to <email> --subject <text> [--body <text>] [--html] [--cc <email>] [--bcc <email>] [--attach <file>]');
        console.error('  send   --to <email> --subject <text> --body-file <file> [--html-file <file>] [--attach <file>]');
        console.error('  test   Test SMTP connection');
        process.exit(1);
    }

    console.log(JSON.stringify(result, null, 2));
  } catch (err) {
    console.error('Error:', err.message);
    process.exit(1);
  }
}

main();
