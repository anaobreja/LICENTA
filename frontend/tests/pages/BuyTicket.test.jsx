/**
 * Smoke test pentru BuyTicket.jsx.
 *
 * Verifica:
 * 1. Componenta nu crapa la mount (prinde bugurile `formData`, `from?`, `to?` undefined)
 * 2. Afiseaza formularul de cumparare (stations + date + ticket type)
 * 3. Submit button e disabled cat timp nu e selectat un tren
 */
import { describe, it, expect, beforeEach } from 'vitest'
import { render, screen } from '@testing-library/react'
import { MemoryRouter } from 'react-router-dom'
import BuyTicket from '../../src/pages/BuyTicket.jsx'

beforeEach(() => {
  window.localStorage.setItem('access_token', 'mock-token')
})

function renderWithRouter() {
  return render(
    <MemoryRouter initialEntries={['/tickets/buy']}>
      <BuyTicket />
    </MemoryRouter>
  )
}

describe('BuyTicket', () => {
  it('mounts fara crash (regression: ReferenceError formData/from/to)', () => {
    renderWithRouter()
    // Daca componenta crapa cu ReferenceError la mount, render() ar arunca.
    // Folosim heading-ul (h1) ca selector precis - titlul paginii e unic.
    expect(screen.getByRole('heading', { name: /cumpara bilet/i, level: 1 })).toBeInTheDocument()
  })

  it('afiseaza form-ul de cumparare (combobox-uri statie + date picker)', () => {
    renderWithRouter()
    // Form-ul are 2 combobox-uri: "De la" si "Pana la"
    expect(screen.getByText(/De la/i)).toBeInTheDocument()
    expect(screen.getByText(/Pana la/i)).toBeInTheDocument()
    expect(screen.getByText(/Data calatoriei/i)).toBeInTheDocument()
  })

  it('butonul "Cumpara bilet" e disabled cat timp nu e selectat un tren', () => {
    renderWithRouter()
    const btn = screen.getByRole('button', { name: /cumpara bilet/i })
    expect(btn).toBeDisabled()
  })

  it('link-ul "Biletele mele" navigheaza la /tickets', () => {
    renderWithRouter()
    const link = screen.getByRole('link', { name: /biletele mele/i })
    expect(link).toHaveAttribute('href', '/tickets')
  })
})
