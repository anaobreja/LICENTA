/**
 * Fetches actual OSM railway track geometry from Overpass API and routes
 * through it using A* pathfinding, giving Google Maps-like rail polylines.
 */

class MinHeap {
  constructor() { this._d = [] }
  push(item) {
    this._d.push(item)
    let i = this._d.length - 1
    while (i > 0) {
      const p = (i - 1) >> 1
      if (this._d[p][0] <= this._d[i][0]) break
      ;[this._d[p], this._d[i]] = [this._d[i], this._d[p]]
      i = p
    }
  }
  pop() {
    const top = this._d[0]
    const last = this._d.pop()
    if (this._d.length) {
      this._d[0] = last
      let i = 0
      for (;;) {
        const l = 2 * i + 1, r = 2 * i + 2
        let m = i
        if (l < this._d.length && this._d[l][0] < this._d[m][0]) m = l
        if (r < this._d.length && this._d[r][0] < this._d[m][0]) m = r
        if (m === i) break
        ;[this._d[i], this._d[m]] = [this._d[m], this._d[i]]
        i = m
      }
    }
    return top
  }
  get size() { return this._d.length }
}

function buildGraph(elements) {
  const nodes = new Map()
  const coords = []
  const adj = []

  const getOrAdd = (lat, lon) => {
    const key = `${lat.toFixed(5)},${lon.toFixed(5)}`
    if (!nodes.has(key)) {
      nodes.set(key, coords.length)
      coords.push([lat, lon])
      adj.push([])
    }
    return nodes.get(key)
  }

  for (const elem of elements) {
    if (elem.type !== 'way' || !elem.geometry?.length) continue
    const ids = elem.geometry.map(g => getOrAdd(g.lat, g.lon))
    for (let i = 0; i < ids.length - 1; i++) {
      adj[ids[i]].push(ids[i + 1])
      adj[ids[i + 1]].push(ids[i])
    }
  }

  return { coords, adj }
}

function nearestNode(coords, lat, lon) {
  let best = 0, bestD = Infinity
  for (let i = 0; i < coords.length; i++) {
    const dx = coords[i][0] - lat, dy = coords[i][1] - lon
    const d = dx * dx + dy * dy
    if (d < bestD) { bestD = d; best = i }
  }
  return best
}

function astar(coords, adj, startN, endN) {
  if (startN === endN) return [coords[startN]]

  const n = coords.length
  const gScore = new Float64Array(n).fill(Infinity)
  const prev = new Int32Array(n).fill(-1)
  const closed = new Uint8Array(n)
  gScore[startN] = 0

  const ex = coords[endN][0], ey = coords[endN][1]
  const h = (i) => {
    const dx = coords[i][0] - ex, dy = coords[i][1] - ey
    return Math.sqrt(dx * dx + dy * dy)
  }

  const heap = new MinHeap()
  heap.push([h(startN), startN])

  while (heap.size) {
    const [, cur] = heap.pop()
    if (closed[cur]) continue
    closed[cur] = 1

    if (cur === endN) {
      const path = []
      let nd = endN
      while (nd !== -1) { path.push(coords[nd]); nd = prev[nd] }
      return path.reverse()
    }

    for (const nb of adj[cur]) {
      if (closed[nb]) continue
      const dx = coords[cur][0] - coords[nb][0], dy = coords[cur][1] - coords[nb][1]
      const ng = gScore[cur] + Math.sqrt(dx * dx + dy * dy)
      if (ng < gScore[nb]) {
        gScore[nb] = ng
        prev[nb] = cur
        heap.push([ng + h(nb), nb])
      }
    }
  }

  return null
}

/**
 * Fetches actual railway track geometry for a route leg.
 * @param {Array<{lat: number, lon: number}>} gpsStops - ordered GPS stops along the leg
 * @param {number} padding - degrees of bbox padding (default 0.15 ≈ 16km)
 * @returns {Promise<Array<[number,number]>|null>} - [[lat,lon],...] or null on failure
 */
async function fetchSegmentGeometry(w1, w2, padding) {
  const south = Math.min(w1.lat, w2.lat) - padding
  const north = Math.max(w1.lat, w2.lat) + padding
  const west  = Math.min(w1.lon, w2.lon) - padding
  const east  = Math.max(w1.lon, w2.lon) + padding

  const query = `[out:json][timeout:20];(way[railway=rail][!service](${south},${west},${north},${east}););out geom;`
  try {
    const resp = await fetch('https://overpass-api.de/api/interpreter', {
      method: 'POST',
      headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
      body: `data=${encodeURIComponent(query)}`,
    })
    if (!resp.ok) return null
    const data = await resp.json()
    const elements = data.elements || []
    if (!elements.length) return null

    const { coords, adj } = buildGraph(elements)
    if (!coords.length) return null

    const fromN = nearestNode(coords, w1.lat, w1.lon)
    const toN   = nearestNode(coords, w2.lat, w2.lon)
    return astar(coords, adj, fromN, toN)
  } catch {
    return null
  }
}

export async function fetchLegRailGeometry(gpsStops, padding = 0.15) {
  if (!gpsStops || gpsStops.length < 2) return null

  // Exclude junction/halt waypoints — they sit on track branches and cause A* zigzags.
  const isJunction = (s) => {
    const n = (s.name || '').toLowerCase()
    return n.includes(' ram.') || n.includes(' hm.') || n.includes(' h.')
  }
  const anchors = gpsStops.filter((s, i) =>
    i === 0 || i === gpsStops.length - 1 || !isJunction(s)
  )
  const waypoints = anchors.length >= 2 ? anchors : gpsStops

  // Fetch each sub-segment in parallel with its own tight bounding box.
  // This prevents cross-contamination between distant railway branches.
  const segs = await Promise.all(
    waypoints.slice(0, -1).map((w1, i) => fetchSegmentGeometry(w1, waypoints[i + 1], padding))
  )

  const fullPath = []
  for (let i = 0; i < segs.length; i++) {
    const seg = segs[i]
    if (!seg) {
      if (fullPath.length === 0) fullPath.push([waypoints[i].lat, waypoints[i].lon])
      fullPath.push([waypoints[i + 1].lat, waypoints[i + 1].lon])
    } else {
      if (fullPath.length === 0) fullPath.push(...seg)
      else fullPath.push(...seg.slice(1))
    }
  }

  return fullPath.length >= 2 ? fullPath : null
}
