# LICENTA — Platformă Digitală Identitate & Bilete Feroviare

## Arhitectură

| Serviciu | Port | Tehnologie |
|----------|------|------------|
| Backend API | 8000 | FastAPI + PostgreSQL |
| Frontend dev server | 5173 | React + Vite |

## Pornire locală

```powershell
# Backend
cd d:\LICENTA\backend
python -m uvicorn app.main:app --reload --port 8000

# Frontend
cd d:\LICENTA\frontend
npm run dev
```

Acces local: **http://localhost:5173**

---

## Testare pe telefon

### Opțiunea 1 — Rețea locală (Wi-Fi comun)

Vite rulează cu `host: true` în `vite.config.js`, deci e accesibil pe toate interfețele.

1. Găsește IP-ul calculatorului:
   ```powershell
   Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.IPAddress -notlike '127.*' }
   # Wi-Fi: 192.168.137.184 (se poate schimba)
   ```
2. Pe telefon (același Wi-Fi): `http://192.168.137.184:5173`
3. Dacă apare eroare "Invalid Host header", adaugă IP-ul în `allowedHosts` din `vite.config.js`

### Opțiunea 2 — VS Code Dev Tunnels (HTTPS public, pentru cameră/QR)

Camera pe telefon necesită **HTTPS** — Dev Tunnels oferă asta gratuit din VS Code.

**Setup:**
1. În VS Code → tab **PORTS** (jos) → **Add Port** → introdu `5173`
   - ⚠️ Trebuie să fie portul **5173** (Vite), NU 8000 (backend direct)
2. Click dreapta pe port → **Port Visibility** → **Public**
3. Copiază URL-ul generat (ex: `https://c9q8rq05-5173.euw.devtunnels.ms/`)
4. Pe telefon: deschide acel URL

**Cum funcționează:**
```
Telefon → https://<id>-5173.euw.devtunnels.ms/
              ↓
          Vite (port 5173)   ← proxy →   FastAPI (port 8000)
```
Vite proxy-uiește toate cererile `/api/*` spre `http://127.0.0.1:8000` — telefonul nu trebuie să acceseze backend-ul direct.

**Dacă apare "Blocked request":**
Adaugă domeniul în `vite.config.js` → `allowedHosts`:
```js
'.devtunnels.ms'   // wildcard pentru toate subdomeniile Dev Tunnels
```

### Opțiunea 3 — ngrok

```powershell
ngrok http 5173
```
Adaugă URL-ul ngrok (ex: `glance-handshake-episode.ngrok-free.dev`) în `allowedHosts`.

---

## Hosts configurate în vite.config.js

```
localhost, 127.0.0.1          — dezvoltare locală
172.20.10.13                  — IP hotspot iPhone (se schimbă)
192.168.137.184               — IP Wi-Fi local curent
glance-handshake-episode.ngrok-free.dev  — tunel ngrok
.devtunnels.ms                — wildcard VS Code Dev Tunnels
```

---

## Bază de date

```
Host: localhost:5432
DB:   railway_db
User: railway / railway_dev
```

## Credențiale test

Userii cu documente aprobate sunt în `source_documents` cu `status='approved'`.
Backfill credentiale `identity_verified` rulat la 2026-06-12.
