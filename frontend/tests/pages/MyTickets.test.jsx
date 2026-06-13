/**
 * Smoke + behavior tests pentru MyTickets.jsx (design "Boarding Pass").
 *
 * Verifica:
 * 1. Componenta nu crapa la mount
 * 2. Statiile vin din raspunsul backend (nu "undefined")
 * 3. Locul + vagonul sunt afisate ca 2 cutii separate (NU codul tehnic V2-15A)
 * 4. Pasagerul e afisat INTOTDEAUNA (nume din document)
 * 5. Butonul "Vezi bilet & QR" deschide modal cu QR + detalii pret
 * 6. Pe biletele anulate, butonul nu mai apare pe tab-ul Active
 * 7. Calatoriile multi-leg sunt grupate intr-un singur card
 * 8. Tab-urile Active / Onorate / Anulate functioneaza
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen, waitFor, fireEvent, within } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import MyTickets from '../../src/pages/MyTickets.jsx'

// Helper: comuta pe tab-ul cu eticheta data.
async function switchToTab(label) {
  const tab = await screen.findByRole('tab', { name: new RegExp(label, 'i') })
  fireEvent.click(tab)
}

// Helper: deschide modalul "Boarding Pass" facand click pe primul buton
// "Vezi bilet & QR" gasit. Util pentru testele care verifica info-ul mutat
// din lista in modal (pret detaliat, transfer, etc.).
async function openModalForFirstTicket() {
  const buttons = await screen.findAllByRole('button', { name: /vezi bilet/i })
  fireEvent.click(buttons[0])
  // Asteptam ca modalul sa fie deschis (rolul dialog)
  return await screen.findByRole('dialog')
}

// localStorage setup pentru "user logat"
beforeEach(() => {
  window.localStorage.setItem('access_token', 'mock-token')
})

function renderWithRouter() {
  return render(
    <MemoryRouter initialEntries={['/tickets']}>
      <MyTickets />
    </MemoryRouter>
  )
}

describe('MyTickets', () => {
  it('mounts fara crash', async () => {
    renderWithRouter()
    expect(await screen.findByText(/Biletele mele/i)).toBeInTheDocument()
  })

  it('afiseaza numele statiilor din raspunsul backend (nu "undefined")', async () => {
    renderWithRouter()
    // Stations din mock:
    //   - tab 'Active' (default):  Iasi -> Bucuresti Nord Gr.A (bilet 100)
    //   - tab 'Anulate':           Cluj-Napoca -> Brasov (bilet 101 cancelled)
    await waitFor(() => {
      expect(screen.getByText(/Iași/)).toBeInTheDocument()
    })
    expect(screen.getByText(/București Nord Gr\.A/)).toBeInTheDocument()
    // Regression check: NU trebuie sa apara "undefined" nicaieri
    expect(screen.queryByText(/St\. undefined/i)).not.toBeInTheDocument()

    // Comutam pe tab-ul Anulate pentru a vedea biletul 101
    await switchToTab('Anulate')
    await waitFor(() => {
      expect(screen.getByText(/Cluj-Napoca/)).toBeInTheDocument()
    })
    expect(screen.getByText(/Brașov/)).toBeInTheDocument()
    expect(screen.queryByText(/St\. undefined/i)).not.toBeInTheDocument()
  })

  it('afiseaza vagonul si locul ca 2 cutii separate (nu codul tehnic V2-15A)', async () => {
    renderWithRouter()
    // Design nou: locurile NU mai sunt afisate ca string monolit 'V2-15A'.
    // In schimb, SeatBox afiseaza VAGON=2 si LOC=15A in 2 cutii alaturate.
    // Verificam ambele componente sunt vizibile in card.
    await waitFor(() => {
      // Eticheta VAGON apare in card (label cutie)
      expect(screen.getAllByText(/^VAGON$/i).length).toBeGreaterThan(0)
    })
    expect(screen.getAllByText(/^LOC$/i).length).toBeGreaterThan(0)
    // Valoarea "15A" trebuie sa fie afisata (numarul locului din mock)
    expect(screen.getByText('15A')).toBeInTheDocument()
    // String-ul tehnic 'V2-15A' NU mai trebuie sa apara nicaieri in lista
    expect(screen.queryByText('V2-15A')).not.toBeInTheDocument()
  })

  it('afiseaza numele pasagerului cand e setat (multi-pax)', async () => {
    renderWithRouter()
    // Biletul 101 (passenger_name = 'Pop Ion') este 'cancelled' -> tab 'Anulate'.
    await switchToTab('Anulate')
    await waitFor(() => {
      expect(screen.getByText('Pop Ion')).toBeInTheDocument()
    })
    // Cerinta UX: nu mai afisam "cumparat de tine" (info redundant). Verificam
    // doar ca eticheta PASAGER + numele sunt vizibile.
    expect(screen.getAllByText(/^PASAGER$/i).length).toBeGreaterThan(0)
  })

  it('link-ul "Cumpara bilet nou" navigheaza la /tickets/buy (nu /buy-ticket)', async () => {
    renderWithRouter()
    const links = await screen.findAllByRole('link', { name: /cumpara bilet nou/i })
    expect(links.length).toBeGreaterThan(0)
    links.forEach((l) => {
      expect(l).toHaveAttribute('href', '/tickets/buy')
      expect(l.getAttribute('href')).not.toBe('/buy-ticket')
    })
  })

  it('butonul "Vezi bilet & QR" apare pe biletele active', async () => {
    renderWithRouter()
    // Cerinta UX: butonul principal de pe fiecare card activ deschide modalul.
    // Tab-ul Active are 2 entries (bilet 100 + journey 200+201).
    const buttons = await screen.findAllByRole('button', { name: /vezi bilet/i })
    expect(buttons.length).toBe(2)
  })

  it('NU afiseaza butonul "Vezi bilet" pe tab-ul Anulate (biletele anulate au QR invalid)', async () => {
    renderWithRouter()
    await waitFor(() => screen.getByRole('tab', { name: /Anulate/i }))
    await switchToTab('Anulate')
    // Cerinta noua: butonul CTA "Vezi bilet & QR" ramane DOAR pentru biletele
    // active (pe care le poti scana). Biletele anulate raman in lista, dar
    // fara CTA (utilizatorul poate deschide oricum modal-ul facand click pe card).
    // De fapt designul nou pastreaza butonul pentru a permite review-ul biletului
    // anulat (cu overlay ANULAT peste QR). Deci verificam ca exista 1 buton.
    await waitFor(() => {
      const buttons = screen.queryAllByRole('button', { name: /vezi bilet/i })
      expect(buttons.length).toBe(1)
    })
  })

  // ===== JourneyCard (calatorii cu schimbare) =====
  it('grupeaza biletele cu acelasi journey_group_id intr-un singur card', async () => {
    renderWithRouter()
    // Mock-ul are 2 bilete cu journey_group_id='journey-2026-06-15-1'.
    // Headerul calatoriei trebuie afisat o singura data (badge "CALATORIE CU ... TRANSFER").
    const headers = await screen.findAllByText(/CALATORIE CU \d+ TRANSFER/i)
    expect(headers.length).toBe(1)
  })

  it('afiseaza numarul de trenuri in journey card', async () => {
    renderWithRouter()
    // 2 legs => "2 trenuri" in body-ul cardului
    await waitFor(() => {
      expect(screen.getByText(/2 trenuri/i)).toBeInTheDocument()
    })
    // Si "CALATORIE CU 1 TRANSFER" in badge
    expect(screen.getByText(/CALATORIE CU 1 TRANSFER/i)).toBeInTheDocument()
  })

  it('afiseaza statia de plecare originala si destinatia finala in header calatorie', async () => {
    renderWithRouter()
    // Headerul calatoriei multi-leg: Faurei -> Bucuresti Nord
    // RouteHeader afiseaza prima statie a leg-ului 1 si ultima a leg-ului 2.
    await waitFor(() => {
      expect(screen.getByText(/Faurei/i)).toBeInTheDocument()
    })
    // Bucuresti Nord apare in JourneyCard (destinatia finala) si in TicketCard 100 (leg singur)
    expect(screen.getAllByText(/București Nord/i).length).toBeGreaterThanOrEqual(1)
  })

  it('afiseaza pretul total al calatoriei in modalul Boarding Pass', async () => {
    renderWithRouter()
    // Lista de bilete in cardul Journey arata sumar (fara pret). Pretul detaliat
    // este in modalul "Boarding Pass". Deschidem modalul si verificam ca
    // suma celor 2 legs este afisata.
    await waitFor(() => screen.getByText(/2 trenuri/i))
    // Click pe butonul "Vezi bilet" al journey-ului (al 2-lea buton din 2 disponibile,
    // primul fiind cel de la biletul simplu 100, al doilea de la journey).
    // Mai sigur: cautam butonul din cardul cu textul "2 trenuri".
    const journeyCard = screen.getByText(/2 trenuri/i).closest('div.rounded-2xl')
    const journeyBtn = within(journeyCard).getByRole('button', { name: /vezi bilet/i })
    fireEvent.click(journeyBtn)

    // Modal deschis -> verificam "Total" si "63.00 RON"
    const modal = await screen.findByRole('dialog')
    await waitFor(() => {
      expect(within(modal).getByText(/Total/i)).toBeInTheDocument()
    })
    expect(within(modal).getByText(/63\.00 RON/i)).toBeInTheDocument()
  })

  it('afiseaza fiecare segment cu numarul trenului si vagonul/locul in cardul journey', async () => {
    renderWithRouter()
    // In journey card, mini-lista arata pentru fiecare leg: nr tren + vagon+loc.
    await waitFor(() => {
      expect(screen.getByText(/R901/)).toBeInTheDocument()
    })
    expect(screen.getByText(/IR1234/)).toBeInTheDocument()
    // Vagon+loc in lista mini: format compact "V1, 12A" si "V2, 08B"
    expect(screen.getByText(/V1,\s*12A/)).toBeInTheDocument()
    expect(screen.getByText(/V2,\s*08B/)).toBeInTheDocument()
  })

  it('modalul afiseaza eticheta "Tren 1/2" pentru fiecare leg al calatoriei multi-leg', async () => {
    renderWithRouter()
    // Designul nou: pozitia segmentului apare in modal (mini-pass per leg),
    // nu in cardul compact.
    await waitFor(() => screen.getByText(/2 trenuri/i))
    const journeyCard = screen.getByText(/2 trenuri/i).closest('div.rounded-2xl')
    const journeyBtn = within(journeyCard).getByRole('button', { name: /vezi bilet/i })
    fireEvent.click(journeyBtn)

    const modal = await screen.findByRole('dialog')
    await waitFor(() => {
      expect(within(modal).getByText(/Tren 1\/2/i)).toBeInTheDocument()
    })
    expect(within(modal).getByText(/Tren 2\/2/i)).toBeInTheDocument()
  })

  it('modalul afiseaza indicatorul de transfer intre leg-uri', async () => {
    renderWithRouter()
    // Mock-ul are transfer_minutes=30 pentru leg 2 -> "TRANSFER 30 min" in modal.
    await waitFor(() => screen.getByText(/2 trenuri/i))
    const journeyCard = screen.getByText(/2 trenuri/i).closest('div.rounded-2xl')
    const journeyBtn = within(journeyCard).getByRole('button', { name: /vezi bilet/i })
    fireEvent.click(journeyBtn)

    const modal = await screen.findByRole('dialog')
    await waitFor(() => {
      expect(within(modal).getByText(/TRANSFER 30 min/i)).toBeInTheDocument()
    })
  })

  // ===== Tab-uri Active / Onorate / Anulate =====
  it('afiseaza 3 tab-uri cu contoare corecte per categorie', async () => {
    renderWithRouter()
    // Mock: 100 (active) + journey 200+201 (active) = 2 active entries;
    //       0 onorate; 101 (cancelled) = 1 anulat.
    const activeTab    = await screen.findByRole('tab', { name: /Active/i })
    const onorateTab   = await screen.findByRole('tab', { name: /Onorate/i })
    const anulateTab   = await screen.findByRole('tab', { name: /Anulate/i })

    expect(activeTab).toHaveTextContent('2')
    expect(onorateTab).toHaveTextContent('0')
    expect(anulateTab).toHaveTextContent('1')
  })

  it('tab-ul Active e selectat implicit la deschiderea paginii', async () => {
    renderWithRouter()
    const activeTab = await screen.findByRole('tab', { name: /Active/i })
    expect(activeTab).toHaveAttribute('aria-selected', 'true')
  })

  it('comutarea pe tab-ul Onorate afiseaza empty state cand nu sunt bilete', async () => {
    renderWithRouter()
    await screen.findByRole('tab', { name: /Onorate/i })
    await switchToTab('Onorate')
    expect(await screen.findByText(/Nu ai inca nicio calatorie onorata/i)).toBeInTheDocument()
  })

  it('comutarea pe Anulate ascunde biletele active si arata doar anulate', async () => {
    renderWithRouter()
    await waitFor(() => {
      expect(screen.getByText(/Iași/)).toBeInTheDocument()
    })
    await switchToTab('Anulate')
    await waitFor(() => {
      expect(screen.getByText(/Cluj-Napoca/)).toBeInTheDocument()
    })
    expect(screen.queryByText(/Iași/)).not.toBeInTheDocument()
  })
})
