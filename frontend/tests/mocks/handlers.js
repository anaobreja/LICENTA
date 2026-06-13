/**
 * MSW handlers - mock-uiesc API-ul backend pentru testele de UI.
 *
 * Răspunsurile reflectă EXACT structura JSON pe care backend-ul o trimite
 * (vezi backend/tests/integration/test_tickets_contract.py pentru lista
 * cheilor garantate).
 */
import { http, HttpResponse } from 'msw'

// Frontend folosește prefixul /api/ (proxy_server.py îl mapează la backend:8000)
const API = '/api'

export const handlers = [
  // ---- AUTH ----
  http.post(`${API}/auth/login`, async ({ request }) => {
    return HttpResponse.json({
      access_token: 'mock-token-passenger',
      token_type: 'bearer',
      user: {
        user_id: 1,
        email: 'test@example.com',
        first_name: 'Test',
        last_name: 'User',
        role: 'passenger',
      },
    })
  }),

  // ---- DOCUMENTS ----
  http.get(`${API}/documents/me`, () => {
    return HttpResponse.json([
      {
        id: 1,
        document_type: 'student_card',
        document_number_masked: 'ST****1234',
        status: 'pending',
        uploaded_at: '2026-06-01T10:00:00',
        university_name: 'Universitatea Politehnica București (UPB)',
        year_of_study: 2,
        ci_number: 'XZ123456',
        ci_name: 'Test User',
        ci_date_of_birth: '2003-05-25',
        ci_sex: 'M',
        ci_address: 'Str. Test Nr. 1',
        document_image_path: '/uploads/doc1_front.jpg',
        document_image_path_verso: '/uploads/doc1_verso.jpg',
        has_front_image: true,
        has_verso_image: true,
        has_photo: true,
        has_photo_verso: true,
      },
    ])
  }),

  http.get(`${API}/credentials/me`, () => {
    return HttpResponse.json([])
  }),

  http.get(`${API}/users/me`, () => {
    return HttpResponse.json({
      user_id: 1,
      email: 'test@example.com',
      first_name: 'Test',
      last_name: 'User',
      role: 'passenger',
    })
  }),

  http.get(`${API}/users/me/profile`, () => {
    return HttpResponse.json({
      user_id: 1,
      email: 'test@example.com',
      first_name: 'Test',
      last_name: 'User',
      role: 'passenger',
      profile_photo_path: null,
      home_station: null,
    })
  }),

  http.get(`${API}/documents/:id/photo`, () => {
    return new HttpResponse(new Blob(['mock-image']), {
      status: 200,
      headers: { 'Content-Type': 'image/jpeg' },
    })
  }),

  // ---- TICKETS ----
  http.get(`${API}/tickets/my`, () => {
    return HttpResponse.json([
      {
        ticket_id: 100,
        // Data in viitor (vs. data curenta sub 2026-06-10) ca biletul sa fie
        // categorizat 'active' (tab-ul default in MyTickets). Schimbarea a fost
        // facuta cand am introdus tab-urile Active/Onorate/Anulate — un bilet
        // activ cu data trecuta s-ar muta in "Onorate" (lazy expire) si testele
        // de afisare stations/seats/QR nu l-ar mai gasi pe tab-ul implicit.
        train_id: 1668,
        train_number: '1668',
        train_type: 'IR',
        departure_station: 'Iași',
        arrival_station: 'București Nord Gr.A',
        departure_station_id: 1,
        arrival_station_id: 2,
        travel_date: '2026-06-20',
        ticket_type: 'single',
        ticket_status: 'active',
        price: 56.0,
        discount_applied: 0,
        purchase_time: '2026-06-08T20:00:00',
        cancel_refund_amount: null,
        seats: ['V2-15A'],
        passenger_name: null,
        qr_token: 'mock_qr_token_active_100',
        qr_expires_at: '2026-06-21 23:59:59',
        qr_data_url: 'data:image/png;base64,iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mNkYAAAAAYAAjCB0C8AAAAASUVORK5CYII=',
      },
      {
        ticket_id: 101,
        train_id: 538,
        train_number: '538',
        train_type: 'IR',
        departure_station: 'Cluj-Napoca',
        arrival_station: 'Brașov',
        departure_station_id: 3,
        arrival_station_id: 4,
        travel_date: '2026-06-09',
        ticket_type: 'single',
        ticket_status: 'cancelled',
        price: 135.0,
        discount_applied: 0,
        purchase_time: '2026-06-08T19:30:00',
        cancel_refund_amount: 121.5,
        seats: [],
        passenger_name: 'Pop Ion',
        qr_token: null,
        qr_expires_at: null,
        qr_data_url: null,
      
      },
      // ---- Calatorie cu schimbare (2 legs) ----
      // Leg 1: Faurei -> Buzau
      {
        ticket_id: 200,
        train_id: 900,
        train_number: 'R901',
        train_type: 'regio',
        departure_station: 'Faurei',
        arrival_station: 'Buzau',
        departure_station_id: 10,
        arrival_station_id: 11,
        travel_date: '2026-06-15',
        ticket_type: 'single',
        ticket_status: 'active',
        price: 18.0,
        base_price: 18.0,
        discount_applied: 0,
        discounts: [],
        purchase_time: '2026-06-10T09:00:00',
        cancel_refund_amount: null,
        seats: ['V1-12A'],
        passenger_name: null,
        departure_time: '07:00',
        arrival_time: '08:00',
        qr_token: null,
        qr_expires_at: null,
        qr_data_url: null,
        journey_group_id: 'journey-2026-06-15-1',
        leg_index: 0,
        total_legs: 2,
        transfer_minutes: null,
      },
      // Leg 2: Buzau -> Bucuresti Nord
      {
        ticket_id: 201,
        train_id: 901,
        train_number: 'IR1234',
        train_type: 'intercity',
        departure_station: 'Buzau',
        arrival_station: 'Bucuresti Nord Gr.A',
        departure_station_id: 11,
        arrival_station_id: 2,
        travel_date: '2026-06-15',
        ticket_type: 'single',
        ticket_status: 'active',
        price: 45.0,
        base_price: 45.0,
        discount_applied: 0,
        discounts: [],
        purchase_time: '2026-06-10T09:00:30',
        cancel_refund_amount: null,
        seats: ['V2-08B'],
        passenger_name: null,
        departure_time: '08:30',
        arrival_time: '10:15',
        qr_token: null,
        qr_expires_at: null,
        qr_data_url: null,
        journey_group_id: 'journey-2026-06-15-1',
        leg_index: 1,
        total_legs: 2,
        transfer_minutes: 30,
      },
    ])
  }),

  http.get(`${API}/tickets/catalog`, () => {
    return HttpResponse.json([
      {
        train_id: 1668,
        train_number: '1668',
        train_type: 'IR',
        capacity_seats: 280,
        route_id: 1,
        route_name: 'Iași - București Nord',
        operator_name: 'CFR Călători',
        departure_id: 1,
        departure_name: 'Iași',
        departure_code: 'IS',
        arrival_id: 2,
        arrival_name: 'București Nord Gr.A',
        arrival_code: 'BN',
        total_distance_km: 406,
      },
    ])
  }),

  http.get(`${API}/stations/search`, () => {
    return HttpResponse.json([
      { station_id: 1, name: 'Iași', code: 'IS', city: 'Iași' },
      { station_id: 2, name: 'București Nord Gr.A', code: 'BN', city: 'București' },
    ])
  }),

  http.get(`${API}/trains/search`, () => {
    return HttpResponse.json([])
  }),

  http.post(`${API}/tickets/quote`, () => {
    return HttpResponse.json({
      base_price: 56.0,
      discount_percent: 0,
      final_price: 56.0,
      price_per_seat: 56.0,
      total_for_seats: 56.0,
      passenger_count: 1,
      distance_km: 406.0,
      ticket_type: 'single',
      savings: 0,
      is_personal_route: false,
      route_reason: 'Ruta nu corespunde traseului tau personal',
      home_station_id: null,
      university_station_id: null,
    })
  }),

  http.post(`${API}/tickets/buy`, () => {
    return HttpResponse.json({
      ticket_id: 200,
      ticket_type: 'single',
      travel_date: '2026-06-15',
      price: 56.0,
      discount_applied: 0,
      qr_token: 'mock-qr-token',
      qr_expires_at: '2026-06-15T23:59:59Z',
      message: 'Bilet cumparat cu succes.',
      tickets: [
        {
          ticket_id: 200,
          ticket_type: 'single',
          travel_date: '2026-06-15',
          price: 56.0,
          passenger_name: null,
          seat_id: null,
          qr_token: 'mock-qr-token',
          qr_expires_at: '2026-06-15T23:59:59Z',
        },
      ],
      total_price: 56.0,
      count: 1,
    })
  }),

  // ---- SUBSCRIPTIONS ----
  http.get(`${API}/subscriptions/my`, () => {
    return HttpResponse.json([])
  }),

  // ---- NOTIFICATIONS ----
  http.get(`${API}/notifications/me`, () => {
    return HttpResponse.json([])
  }),
]
