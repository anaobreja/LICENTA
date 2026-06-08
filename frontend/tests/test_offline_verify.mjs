/**
 * Tests pentru verifyOfflineToken — verificare offline a tokenurilor
 * de prezentare cu Web Crypto API (Ed25519).
 *
 * Rulare:
 *   cd frontend
 *   node tests/test_offline_verify.mjs
 *
 * De ce script ad-hoc in loc de vitest/jest:
 *   - Aceasta este singura componenta JS care necesita teste cu Web Crypto.
 *   - Nu vrem sa adaugam un test runner intreg (vitest + jsdom + config)
 *     pentru un singur fisier.
 *   - Node 24+ are nativ crypto.subtle cu algoritmul Ed25519 (la fel ca
 *     browserul Chrome 120+ / Firefox 130+), deci putem testa exact codul
 *     care va rula in productie, fara polyfill-uri.
 *   - Daca testele cresc, migram la vitest.
 *
 * Cuprins:
 *   1. Token valid semnat de backend -> { valid: true, payload }
 *   2. Token cu payload modificat -> { valid: false, reason: 'Semnatura...' }
 *   3. Token cu exp in trecut -> { valid: false, reason: 'Token expirat...' }
 *   4. Token corupt (format invalid) -> { valid: false, reason }
 *   5. Token semnat cu alta cheie -> { valid: false }
 *   6. Cache localStorage: a doua chemare nu apeleaza /verification-key
 */

import { strict as assert } from 'node:assert'
import { generateKeyPairSync, sign as nodeSign, createPublicKey } from 'node:crypto'

// =============================================================================
// Setup: shims pentru ce verifyOfflineToken se asteapta sa gaseasca in browser
// =============================================================================

// localStorage shim — un Map simplu
class LocalStorageShim {
  constructor() { this._store = new Map() }
  getItem(k) { return this._store.has(k) ? this._store.get(k) : null }
  setItem(k, v) { this._store.set(k, String(v)) }
  removeItem(k) { this._store.delete(k) }
  clear() { this._store.clear() }
}
globalThis.localStorage = new LocalStorageShim()
globalThis.window = { crypto: globalThis.crypto }

// =============================================================================
// Mock fetch — interceptam apelurile la /api/verification-key.
// Asteptam ca verifyOfflineToken sa intoarca raspuns mock cu cheia noastra.
// =============================================================================
const fetchCalls = []
let mockKeyResponse = null

globalThis.fetch = async (url, options) => {
  fetchCalls.push({ url: String(url), options })
  if (String(url).includes('/verification-key')) {
    return {
      ok: true,
      status: 200,
      headers: { get: () => 'application/json' },
      json: async () => mockKeyResponse,
    }
  }
  throw new Error(`Unmocked fetch: ${url}`)
}

// =============================================================================
// Import modulul testat. api.js a fost adaptat sa accepte import.meta.env
// undefined (in Node nu exista Vite, deci foloseste fallback '/api').
// =============================================================================
const apiModule = await import('../src/services/api.js')
const { verifyOfflineToken, clearVerificationKeyCache, getVerificationKey } = apiModule

// =============================================================================
// Helpers: simulam ce face backend-ul cu signing.py.
// JSON canonical (sort_keys, separators compacti) + semnatura Ed25519.
// =============================================================================
function canonicalJson(payload) {
  // sort_keys recursive nu e necesar pentru testele noastre — payload-urile
  // sunt obiecte plate. JSON.stringify cu replacer sorteaza cheile.
  const sortedKeys = Object.keys(payload).sort()
  const sortedObj = {}
  for (const k of sortedKeys) sortedObj[k] = payload[k]
  // Eliminam spatiile prin separators=(',', ':') — JSON.stringify default
  // foloseste ', ' si ': ' DACA pasezi indent, dar fara indent e deja compact.
  return JSON.stringify(sortedObj)
}

function b64url(buf) {
  return Buffer.from(buf).toString('base64')
    .replace(/\+/g, '-').replace(/\//g, '_').replace(/=+$/, '')
}

function makeToken(privateKey, payload) {
  const canonical = canonicalJson(payload)
  const signature = nodeSign(null, Buffer.from(canonical), privateKey)
  return b64url(canonical) + '.' + b64url(signature)
}

function publicKeyToRawBase64(privateKey) {
  const pubKey = createPublicKey(privateKey)
  const der = pubKey.export({ type: 'spki', format: 'der' })
  // Pentru Ed25519, ultimii 32 bytes din SPKI sunt cheia raw
  const raw = der.subarray(der.length - 32)
  return raw.toString('base64')
}

function publicKeyToPem(privateKey) {
  const pubKey = createPublicKey(privateKey)
  return pubKey.export({ type: 'spki', format: 'pem' })
}

// =============================================================================
// Test runner minimalist
// =============================================================================
const tests = []
function test(name, fn) { tests.push({ name, fn }) }

async function runAll() {
  let passed = 0, failed = 0
  for (const { name, fn } of tests) {
    try {
      // Reset state intre teste
      clearVerificationKeyCache()
      fetchCalls.length = 0
      await fn()
      console.log(`  PASS  ${name}`)
      passed++
    } catch (e) {
      console.log(`  FAIL  ${name}`)
      console.log(`        ${e.message}`)
      if (e.stack) console.log(e.stack.split('\n').slice(1, 4).map(l => '        ' + l).join('\n'))
      failed++
    }
  }
  console.log(`\n${passed} passed, ${failed} failed`)
  process.exit(failed > 0 ? 1 : 0)
}

// =============================================================================
// Fixture: o pereche de chei + un payload tipic
// =============================================================================
const { privateKey, publicKey } = generateKeyPairSync('ed25519')
mockKeyResponse = {
  algorithm: 'Ed25519',
  kid: '1234567890abcdef',
  pem: publicKeyToPem(privateKey),
  raw_base64: publicKeyToRawBase64(privateKey),
  usage: 'verify',
}

const futureIso = () => new Date(Date.now() + 180_000).toISOString()
const pastIso = () => new Date(Date.now() - 60_000).toISOString()

function validPayload(overrides = {}) {
  return {
    sub: 42,
    pid: 1,
    card: 7,
    holder: 'Demo User',
    claims: ['student_verified'],
    issuer: 'UPB',
    iat: new Date().toISOString(),
    exp: futureIso(),
    kid: '1234567890abcdef',
    ...overrides,
  }
}

// =============================================================================
// TESTS
// =============================================================================

test('verifies a valid signed token', async () => {
  const payload = validPayload()
  const token = makeToken(privateKey, payload)
  const result = await verifyOfflineToken(token)
  assert.equal(result.valid, true, `Expected valid=true, got: ${JSON.stringify(result)}`)
  assert.equal(result.payload.holder, 'Demo User')
  assert.equal(result.payload.issuer, 'UPB')
})

test('rejects token with modified payload (tampered)', async () => {
  const payload = validPayload()
  const token = makeToken(privateKey, payload)
  // Modificam o litera in payload
  const [head, sig] = token.split('.')
  const idx = Math.floor(head.length / 2)
  const newChar = head[idx] === 'A' ? 'B' : 'A'
  const badHead = head.slice(0, idx) + newChar + head.slice(idx + 1)
  const result = await verifyOfflineToken(badHead + '.' + sig)
  assert.equal(result.valid, false)
  assert.match(result.reason, /semnatura/i)
})

test('rejects token with modified signature', async () => {
  const payload = validPayload()
  const token = makeToken(privateKey, payload)
  const [head, sig] = token.split('.')
  const idx = Math.floor(sig.length / 2)
  const newChar = sig[idx] === 'A' ? 'B' : 'A'
  const badSig = sig.slice(0, idx) + newChar + sig.slice(idx + 1)
  const result = await verifyOfflineToken(head + '.' + badSig)
  assert.equal(result.valid, false)
  assert.match(result.reason, /semnatura/i)
})

test('rejects token with exp in the past', async () => {
  const payload = validPayload({ exp: pastIso() })
  const token = makeToken(privateKey, payload)
  const result = await verifyOfflineToken(token)
  assert.equal(result.valid, false)
  assert.match(result.reason, /expirat/i)
  assert.ok(result.payload, 'Trebuie sa returnam totusi payload-ul pentru context UI')
})

test('rejects token signed with a DIFFERENT key', async () => {
  // Generam o a doua cheie, semnam cu ea, dar pastram cheia "oficiala"
  // in mock-ul de /verification-key.
  const { privateKey: otherKey } = generateKeyPairSync('ed25519')
  const token = makeToken(otherKey, validPayload())
  const result = await verifyOfflineToken(token)
  assert.equal(result.valid, false)
  assert.match(result.reason, /semnatura/i)
})

test('rejects malformed token: missing separator', async () => {
  const result = await verifyOfflineToken('not-a-valid-token-format')
  assert.equal(result.valid, false)
  assert.match(result.reason, /format|separator/i)
})

test('rejects malformed token: too many segments', async () => {
  const result = await verifyOfflineToken('a.b.c')
  assert.equal(result.valid, false)
  assert.match(result.reason, /format|segment/i)
})

test('rejects malformed token: signature wrong length', async () => {
  // Payload valid, dar signature scurta (5 bytes in loc de 64)
  const payload = validPayload()
  const canonical = canonicalJson(payload)
  const shortSig = Buffer.alloc(5, 0xFF)
  const token = b64url(canonical) + '.' + b64url(shortSig)
  const result = await verifyOfflineToken(token)
  assert.equal(result.valid, false)
  assert.match(result.reason, /semnatura|64 bytes/i)
})

test('rejects null/undefined input', async () => {
  const r1 = await verifyOfflineToken(null)
  assert.equal(r1.valid, false)
  const r2 = await verifyOfflineToken(undefined)
  assert.equal(r2.valid, false)
})

test('caches verification key — second call does not refetch', async () => {
  // Prima chemare -> 1 fetch la /verification-key
  await getVerificationKey()
  const firstCount = fetchCalls.filter(c => c.url.includes('/verification-key')).length
  assert.equal(firstCount, 1, `Expected 1 fetch, got ${firstCount}`)

  // A doua chemare (cache hit) -> tot 1 fetch
  await getVerificationKey()
  const secondCount = fetchCalls.filter(c => c.url.includes('/verification-key')).length
  assert.equal(secondCount, 1, `Cache nu functioneaza: ${secondCount} fetch-uri, asteptam 1`)
})

test('force=true bypasses cache', async () => {
  await getVerificationKey()
  await getVerificationKey({ force: true })
  const count = fetchCalls.filter(c => c.url.includes('/verification-key')).length
  assert.equal(count, 2, `force=true ar trebui sa refetch-uiasca: ${count}`)
})

test('clearVerificationKeyCache invalidates cache', async () => {
  await getVerificationKey()
  clearVerificationKeyCache()
  await getVerificationKey()
  const count = fetchCalls.filter(c => c.url.includes('/verification-key')).length
  assert.equal(count, 2)
})

// =============================================================================
// Base64URL edge cases
//
// b64urlToBytes este o functie *interna* in api.js (nu exportata), dar este
// fundatia pe care sta verifyOfflineToken: orice bug aici corupe payload-ul
// sau semnatura inainte sa ajunga la crypto.subtle.verify.
//
// O testam INDIRECT, construind tokenuri reale cu input base64url "tricky":
//   - lungimi care necesita 0/1/2 caractere de padding '='
//   - caractere specifice base64url ('-' si '_') care difera de base64 standard
//   - canonical JSON cu unicode (caractere non-ASCII care produc bytes 0x80+)
//
// Daca b64urlToBytes ar avea un bug (de ex. nu inlocuieste '_', sau adauga
// padding gresit), una din variantele de mai jos ar esua la verificare crypto.
// =============================================================================

// Genereaza un payload de o lungime data, astfel incat lungimea JSON-ului
// canonical sa fie L mod 3 == target (0, 1 sau 2). Asta forteaza diferite
// scenarii de padding base64.
function payloadForB64Padding(targetMod3) {
  // Construim un holder de lungime variabila pana cand JSON-ul canonical
  // ajunge la lungimea dorita mod 3.
  for (let extra = 0; extra < 30; extra++) {
    const candidate = validPayload({ holder: 'A'.repeat(extra) })
    const len = canonicalJson(candidate).length
    if (len % 3 === targetMod3) return candidate
  }
  throw new Error(`Nu am gasit payload cu len%3==${targetMod3}`)
}

test('handles b64url with 0 padding chars (len divisible by 3)', async () => {
  const payload = payloadForB64Padding(0)
  assert.equal(canonicalJson(payload).length % 3, 0, 'precondition')
  const token = makeToken(privateKey, payload)
  const result = await verifyOfflineToken(token)
  assert.equal(result.valid, true, `padding=0: ${JSON.stringify(result)}`)
})

test('handles b64url with 1 padding char (len % 3 == 2)', async () => {
  const payload = payloadForB64Padding(2)
  assert.equal(canonicalJson(payload).length % 3, 2, 'precondition')
  const token = makeToken(privateKey, payload)
  const result = await verifyOfflineToken(token)
  assert.equal(result.valid, true, `padding=1: ${JSON.stringify(result)}`)
})

test('handles b64url with 2 padding chars (len % 3 == 1)', async () => {
  const payload = payloadForB64Padding(1)
  assert.equal(canonicalJson(payload).length % 3, 1, 'precondition')
  const token = makeToken(privateKey, payload)
  const result = await verifyOfflineToken(token)
  assert.equal(result.valid, true, `padding=2: ${JSON.stringify(result)}`)
})

test('handles unicode in payload (forces high-bit bytes through b64url)', async () => {
  // Caractere romanesti -> bytes UTF-8 >= 0x80 -> stress test pentru
  // ca atob() + Uint8Array() sa nu strice nimic.
  const payload = validPayload({
    holder: 'Ștefan Țăndărică',
    issuer: 'Universitatea „Babeș-Bolyai" Cluj',
  })
  const token = makeToken(privateKey, payload)
  const result = await verifyOfflineToken(token)
  assert.equal(result.valid, true, `unicode: ${JSON.stringify(result)}`)
  assert.equal(result.payload.holder, 'Ștefan Țăndărică')
  assert.equal(result.payload.issuer, 'Universitatea „Babeș-Bolyai" Cluj')
})

test('rejects token where b64url contains invalid characters', async () => {
  // '!' nu e valid in base64url. atob() ar trebui sa arunce sau sa produca
  // bytes corupti — oricum, verificarea trebuie sa esueze cu valid=false,
  // nu cu o exceptie scapata.
  const payload = validPayload()
  const token = makeToken(privateKey, payload)
  const corrupted = token.replace(/[A-Za-z]/, '!')  // injectam ! intr-un loc valid
  const result = await verifyOfflineToken(corrupted)
  assert.equal(result.valid, false)
  // Nu impunem un reason exact — diferite browsere arunca mesaje diferite din atob().
  assert.ok(typeof result.reason === 'string' && result.reason.length > 0)
})

test('b64stdToBytes: raw_base64 cu padding "=" e procesat corect', async () => {
  // raw_base64 al unei chei Ed25519 = 32 bytes -> 44 caractere base64 standard
  // cu UN SINGUR '=' la final (32 bytes * 8 / 6 = 42.67 -> 43 chars + 1 padding).
  // Verificam ca b64stdToBytes tolereaza padding-ul standard (cu '+' si '/').
  const rawB64 = publicKeyToRawBase64(privateKey)
  assert.ok(
    rawB64.endsWith('=') && !rawB64.endsWith('=='),
    `Asteptam exact 1 padding '=' pentru cheia de 32 bytes, am primit: ${rawB64}`
  )
  assert.equal(rawB64.length, 44, `Lungime base64 cheie Ed25519 trebuie sa fie 44, este ${rawB64.length}`)

  // Re-fortam mock-ul cu aceasta cheie si verificam ca verifyOfflineToken
  // o decode-eaza corect. (clearVerificationKeyCache deja apelat in runAll.)
  mockKeyResponse = {
    ...mockKeyResponse,
    raw_base64: rawB64,
  }
  const token = makeToken(privateKey, validPayload())
  const result = await verifyOfflineToken(token)
  assert.equal(result.valid, true, `b64std cu padding: ${JSON.stringify(result)}`)
})

test('round-trip: token semnat de "backend" -> verifyOfflineToken returneaza payload original', async () => {
  const original = validPayload({
    sub: 999,
    holder: 'Maria Popescu',
    claims: ['student_verified', 'doctoral_verified'],
    issuer: 'ASE',
  })
  const token = makeToken(privateKey, original)
  const result = await verifyOfflineToken(token)
  assert.equal(result.valid, true)
  assert.equal(result.payload.sub, 999)
  assert.equal(result.payload.holder, 'Maria Popescu')
  assert.deepEqual(result.payload.claims, ['student_verified', 'doctoral_verified'])
  assert.equal(result.payload.issuer, 'ASE')
})

// =============================================================================
// Run
// =============================================================================
console.log('Running verifyOfflineToken tests...\n')
runAll()
