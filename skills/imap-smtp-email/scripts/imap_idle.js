#!/usr/bin/env node
'use strict';

var Imap = require('imap');
var simpleParser = require('mailparser').simpleParser;
var fs = require('fs');
var path = require('path');
var os = require('os');
var config = require('./config');

var POLL_INTERVAL_MS = 60 * 1000;
var STATE_FILE = path.join(os.tmpdir(), 'email_watcher_state.json');

var imap = null;
var isClosing = false;
var lastSeenUid = 0;
var savedUidValidity = null;

function log(msg) {
  var d = new Date();
  var ts = d.toISOString().substring(0, 19).replace('T', ' ');
  console.log('[' + ts + '] ' + msg);
}

function loadState() {
  try {
    if (fs.existsSync(STATE_FILE)) {
      var s = JSON.parse(fs.readFileSync(STATE_FILE, 'utf8'));
      lastSeenUid = s.uid || 0;
      savedUidValidity = s.uidValidity || null;
      log('Loaded state: lastSeenUid=' + lastSeenUid + ', uidValidity=' + (savedUidValidity || 'n/a'));
    }
  } catch (e) {}
}

function saveState(uid, uidValidity) {
  if (uid > lastSeenUid) lastSeenUid = uid;
  if (uidValidity) savedUidValidity = uidValidity;
  try {
    fs.writeFileSync(STATE_FILE, JSON.stringify({
      uid: lastSeenUid,
      uidValidity: savedUidValidity,
      time: new Date().toISOString()
    }), 'utf8');
  } catch (e) {}
}

function createImap() {
  var cfg = config.imap;
  return new Imap({
    user: cfg.user,
    password: cfg.pass,
    host: cfg.host,
    port: cfg.port,
    tls: cfg.tls !== false,
    tlsOptions: { rejectUnauthorized: cfg.rejectUnauthorized !== false },
    id: { name: 'openclaw-email-watcher', version: '1.1' }
  });
}

function fetchByUid(uids, callback) {
  if (!uids || uids.length === 0) {
    callback && callback();
    return;
  }

  var uidList = uids.join(',');
  log('Fetching messages UID ' + uidList);

  var pending = 0;
  var done = false;
  var fetched = [];

  var f = imap.fetch(uidList, {
    bodies: 'HEADER.FIELDS (FROM SUBJECT DATE MESSAGE-ID)',
    markSeen: false
  });

  f.on('message', function(msg) {
    pending++;
    var email = { uid: 0, from: 'unknown', subject: '(no subject)', date: '', messageId: '' };
    var bodyParsed = false;

    msg.on('attributes', function(attrs) {
      if (attrs && attrs.uid) email.uid = attrs.uid;
    });

    msg.on('body', function(stream) {
      simpleParser(stream, {}, function(err, parsed) {
        bodyParsed = true;
        if (err) {
          email.subject = '(parse error)';
        } else {
          var from = parsed.from;
          if (from) {
            if (from.text) email.from = from.text;
            else if (from.value && from.value[0]) email.from = from.value[0].address || from.value[0].name || 'unknown';
          }
          email.subject = parsed.subject || '(no subject)';
          email.date = parsed.date ? parsed.date.toISOString() : '';
          email.messageId = parsed.messageId || '';
        }
      });
    });

    msg.once('end', function() {
      setTimeout(function() {
        fetched.push(email);
        pending--;
        if (done && pending === 0) processFetched(fetched, callback);
      }, bodyParsed ? 0 : 200);
    });
  });

  f.once('error', function(err) {
    log('Fetch error: ' + err.message);
    callback && callback();
  });

  f.once('end', function() {
    done = true;
    if (pending === 0) processFetched(fetched, callback);
  });
}

function processFetched(emails, callback) {
  if (!emails || emails.length === 0) {
    callback && callback();
    return;
  }

  emails.sort(function(a, b) { return (a.uid || 0) - (b.uid || 0); });

  for (var i = 0; i < emails.length; i++) {
    var email = emails[i];
    log('----------------------------------------');
    log('NEW EMAIL RECEIVED');
    log('  UID: ' + email.uid);
    log('  From: ' + email.from);
    log('  Subject: ' + email.subject);
    log('  Date: ' + email.date);
    log('----------------------------------------');

    var event = {
      event: 'new_email',
      uid: email.uid,
      from: email.from,
      subject: email.subject,
      date: email.date,
      messageId: email.messageId || '',
      time: new Date().toISOString()
    };
    console.log('EVENT:' + JSON.stringify(event));

    saveState(email.uid, savedUidValidity);
  }

  callback && callback();
}

function checkMailbox() {
  if (isClosing || !imap || imap.state !== 'authenticated') return;

  var box = imap._box || {};
  var uidValidity = box.uidvalidity || null;

  if (savedUidValidity && uidValidity && savedUidValidity !== uidValidity) {
    log('UIDVALIDITY changed (' + savedUidValidity + ' -> ' + uidValidity + '), resetting state');
    lastSeenUid = 0;
  }
  if (uidValidity) savedUidValidity = uidValidity;

  var criteria = lastSeenUid > 0 ? [['UID', (lastSeenUid + 1) + ':*']] : ['ALL'];

  imap.search(criteria, function(err, uids) {
    if (err) {
      log('Search error: ' + err.message);
      return;
    }

    if (!uids || uids.length === 0) {
      log('Mailbox check: no new messages (lastSeenUid=' + lastSeenUid + ')');
      saveState(lastSeenUid, savedUidValidity);
      return;
    }

    var newUids = uids.filter(function(uid) { return uid > lastSeenUid; }).sort(function(a, b) { return a - b; });

    if (newUids.length === 0) {
      log('Mailbox check: no new messages (lastSeenUid=' + lastSeenUid + ')');
      saveState(lastSeenUid, savedUidValidity);
      return;
    }

    log('Found ' + newUids.length + ' new message(s) by UID');
    fetchByUid(newUids, function() {
      log('Done processing new messages');
      saveState(lastSeenUid, savedUidValidity);
    });
  });
}

function setupImap() {
  imap = createImap();

  imap.on('ready', function() {
    log('Connected to ' + config.imap.host);

    imap.openBox(config.imap.mailbox || 'INBOX', true, function(err, box) {
      if (err) {
        log('Failed to open mailbox: ' + err.message);
        imap.end();
        return;
      }

      var uidValidity = box.uidvalidity || null;
      if (savedUidValidity && uidValidity && savedUidValidity !== uidValidity) {
        log('UIDVALIDITY mismatch on open, resetting uid cursor');
        lastSeenUid = 0;
      }
      savedUidValidity = uidValidity || savedUidValidity;

      log('Watching ' + (config.imap.mailbox || 'INBOX') + ' (uidValidity=' + (savedUidValidity || 'n/a') + ', lastSeenUid=' + lastSeenUid + ')');

      checkMailbox();

      var poll = setInterval(function() {
        if (isClosing) {
          clearInterval(poll);
          return;
        }
        checkMailbox();
      }, POLL_INTERVAL_MS);
    });
  });

  imap.on('mail', function(seqno) {
    log('Mail event (seqno~=' + seqno + ') - checking for new mail by UID');
    checkMailbox();
  });

  imap.on('expunge', function(seqno) {
    log('Message ' + seqno + ' expunged');
  });

  imap.on('error', function(err) {
    log('IMAP error: ' + err.message);
  });

  imap.on('close', function() {
    log('Connection closed');
    if (!isClosing) {
      log('Reconnecting in 30 seconds...');
      setTimeout(function() {
        if (!isClosing) setupImap();
      }, 30000);
    }
  });

  imap.connect();
}

console.log('');
console.log('  IMAP Email Watcher (UID Tracking)');
console.log('  Server:   ' + config.imap.host + ':' + config.imap.port);
console.log('  User:     ' + config.imap.user);
console.log('  Mailbox:  ' + (config.imap.mailbox || 'INBOX'));
console.log('  Poll:     every ' + (POLL_INTERVAL_MS / 1000) + 's');
console.log('  Ctrl+C   to stop');
console.log('');

loadState();

process.on('SIGINT', function() {
  log('Shutting down...');
  isClosing = true;
  if (imap) imap.end();
  process.exit(0);
});

setupImap();
