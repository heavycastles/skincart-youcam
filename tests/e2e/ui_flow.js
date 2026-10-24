// Browser check of the web flow against a mock-mode server: node ui_flow.js <base-url> <width>
// Prints one JSON line {ok, failures, errors}; exits 1 on any failed check.
const puppeteer = require('puppeteer-core');
const [BASE, W] = [process.argv[2], +(process.argv[3] || 1280)];
const CHROME = process.env.CHROME_PATH || '/usr/bin/google-chrome';
const sleep = ms => new Promise(r => setTimeout(r, ms));
(async () => {
  const b = await puppeteer.launch({executablePath: CHROME, headless: 'new', args: ['--no-sandbox']});
  const p = await b.newPage();
  await p.setViewport({width: W, height: 850});
  const errors = [], failures = [], requests = [];
  p.on('console', m => { if (m.type() === 'error') errors.push(m.text()); });
  p.on('pageerror', e => errors.push(e.message));
  await p.setRequestInterception(true);
  let delayNext = 0;  // ms to hold the next /tryon (simulates a slow YouCam render)
  p.on('request', r => {
    const path = new URL(r.url()).pathname;
    if (r.method() === 'POST') requests.push(path);
    if (path === '/tryon' && delayNext) { const d = delayNext; delayNext = 0; setTimeout(() => r.continue(), d); } else r.continue();
  });
  const check = (name, cond) => { if (!cond) failures.push(name); };
  const ev = (fn, ...a) => p.evaluate(fn, ...a);
  const lines = () => ev(() => [...document.querySelectorAll('#lines .line')].map(e => e.querySelector('span').innerText));
  const click = sel => ev(s => document.querySelector(s).click(), sel);
  const settle = async () => { await sleep(150); await p.waitForFunction('trying===null', {timeout: 90000}); await sleep(150); };
  const noScroll = () => ev(() => document.documentElement.scrollWidth <= innerWidth);

  await p.goto(BASE, {waitUntil: 'networkidle0'});
  check('no horizontal scroll on load', await noScroll());
  // odd files never reach the API: each gets one plain sentence
  const fs = require('fs'), os = require('os'), path = require('path');
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), 'skincart-'));
  const fixture = (name, data) => { const f = path.join(tmp, name); fs.writeFileSync(f, data); return f; };
  const tinyPng = Buffer.from('iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAIAAACQd1PeAAAADElEQVR4nGP4z8AAAAMBAQDJ/pLvAAAAAElFTkSuQmCC', 'base64');
  const upload = async (f, re, name) => {
    await (await p.$('#file')).uploadFile(f);
    await p.waitForFunction(r => new RegExp(r).test(document.getElementById('status').innerText), {timeout: 5000}, re.source).catch(() => {});
    check(name, re.test(await ev(() => document.getElementById('status').innerText)));
  };
  await upload(fixture('notes.txt', 'hello'), /isn\u2019t a photo/, 'text file is refused with a sentence');
  await upload(fixture('broken.jpg', 'not really a jpeg'), /couldn\u2019t open this file/, 'broken image is refused with a sentence');
  await upload(fixture('tiny.png', tinyPng), /too small \(1\u00d71 px\)/, 'tiny image is refused with its size');
  await upload(fixture('photo.heic', Buffer.concat([Buffer.from('\0\0\0\x18ftypheic'), Buffer.alloc(64)])), /HEIC/, 'HEIC gets the iPhone hint');
  check('odd files cost no API call', requests.filter(x => x === '/analyze').length === 0);

  // double-click on the sample = one analysis (each one would be a paid YouCam task)
  await ev(() => { const x = document.getElementById('sample'); x.click(); x.click(); });
  await p.waitForSelector('#res.show', {timeout: 30000});
  await sleep(800);
  check('sample: one analysis for a double click', requests.filter(x => x === '/analyze').length === 1);
  check('analysis is announced to screen readers', /Skin analysis ready/.test(await ev(() => document.getElementById('announce').innerText)));
  check('focus moves to the results', await ev(() => document.activeElement && document.activeElement.id === 'resHead'));
  const basket0 = await lines();
  check('routine fills the basket', basket0.length >= 3);

  // shade match, double click = one request
  await ev(() => { const x = document.getElementById('shadeBtn'); x.click(); x.click(); });
  await p.waitForSelector('#shadeRes:not([hidden])', {timeout: 30000});
  check('shade: one request for a double click', requests.filter(x => x === '/shade').length === 1);
  check('shade note is plain text, not in the units chip', !(await ev(() => document.getElementById('shadeUnits').innerText)).includes('lighting'));

  // simulation, then a lipstick must not mark the preview stale
  await click('#simBtn');
  await p.waitForSelector('#simRes:not([hidden])', {timeout: 30000});
  await sleep(200);
  const lips = await ev(() => [...document.querySelectorAll('#shades .sw')].map(e => e.id).filter(i => i.includes('LIP')));
  await click('#' + lips[0]); await settle();
  check('try-on is announced', /Try-on ready/.test(await ev(() => document.getElementById('announce').innerText)));
  check('sim not stale after a lip try-on', (await ev(() => document.getElementById('simBtn').innerText)) === 'Preview on my photo');
  // trying a second lip swaps the first one
  await click('#' + lips[1]); await settle();
  const afterLips = await lines();
  check('only the latest tried lip shade is in the basket', afterLips.filter(n => /Lip|Tint|Balm/.test(n)).length === 1);
  // re-showing an already rendered shade costs no request
  const tryons = requests.filter(x => x === '/tryon').length;
  await click('#' + lips[0]); await settle();
  check('re-trying a rendered shade reuses it', requests.filter(x => x === '/tryon').length === tryons);
  // slow try-on, then a different shade: the later click wins; the slow render is kept, so tapping it later is free
  delayNext = 1500;
  await click('#' + lips[2]); await sleep(200);
  await click('#' + lips[3]); await settle(); await sleep(2000);
  check('slow earlier try-on does not overwrite the later pick', (await ev(() => shown)) === lips[3].slice(2));
  const afterRace = requests.filter(x => x === '/tryon').length;
  await click('#' + lips[2]); await settle();
  check('superseded try-on render is reused, not re-requested', requests.filter(x => x === '/tryon').length === afterRace);
  check('basket has the shade on screen', (await lines()).filter(n => /Lip|Tint|Balm/.test(n)).length === 1);

  // remove a skincare item from the basket: card + plan + sim stay in sync
  const first = await ev(() => document.querySelector('#lines .line span').innerText);
  await click('#lines .rm'); await sleep(200);
  check('remove button drops the item', !(await lines()).includes(first));
  check('routine card follows the basket', await ev(n => [...document.querySelectorAll('.prod')].some(e => e.innerText.includes(n) && e.querySelector('.add').innerText === 'Add'), first));
  check('sim marked stale after a skincare change', (await ev(() => document.getElementById('simBtn').innerText)).startsWith('Basket changed'));

  // match card button toggles
  await click('#matchAdd'); await sleep(100);
  const fndIn = (await lines()).some(n => n.includes('Foundation'));
  await click('#matchAdd'); await sleep(100);
  check('match button toggles foundation', fndIn !== (await lines()).some(n => n.includes('Foundation')));

  // order, then a basket change hides the old receipt
  await p.type('#name', 'Test Shopper'); await p.type('#phone', '+1 555 010 0000');
  await ev(() => { const x = document.getElementById('orderBtn'); x.click(); x.click(); });
  await p.waitForSelector('#ok.show', {timeout: 10000});
  check('order: one request for a double click', requests.filter(x => x === '/orders').length === 1);
  const n = (await lines()).length, txt = await ev(() => document.getElementById('ok').innerText);
  check('receipt counts the basket', txt.includes(`${n} items`));
  check('receipt total matches basket total', txt.includes(await ev(() => document.getElementById('total').innerText)));
  await click('#lines .rm'); await sleep(100);
  check('receipt hidden after the basket changes', !(await ev(() => document.getElementById('ok').classList.contains('show'))));
  check('no horizontal scroll at the end', await noScroll());
  // mock server has no n8n / Telegram bot: the page must not claim them
  check('no n8n alert claim without n8n', !(await ev(() => document.getElementById('leadNote').innerText)).includes('trigger an n8n alert'));
  check('no live-bot claim without a bot', !(await ev(() => document.querySelector('footer').innerText)).includes("runs in the shop's Telegram bot"));
  check('no JS errors', errors.length === 0);
  console.log(JSON.stringify({ok: !failures.length, failures, errors}));
  await b.close();
  process.exit(failures.length ? 1 : 0);
})().catch(e => { console.log(JSON.stringify({ok: false, failures: ['crash: ' + e.message], errors: []})); process.exit(1); });
