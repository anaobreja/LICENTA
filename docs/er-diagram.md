# Modelul de Date — Diagrama Entitate-Relație

## Diagramă de ansamblu (4 module)

```mermaid
graph LR
    subgraph M1["Modulul 1 — Identitate și Documente"]
        U[users]
        UNI[universities]
        DOC[source_documents]
        CRED[user_credentials]
        CARD[digital_cards]
    end

    subgraph M2["Modulul 2 — Transport feroviar"]
        OP[railway_operators]
        ST[stations]
        RT[routes]
        TR[trains]
    end

    subgraph M3["Modulul 3 — Bilete și Validări"]
        TK[tickets]
        SUB[subscriptions]
        TE[travel_entitlements]
        QR[qr_tokens]
        VAL[validations]
    end

    subgraph M4["Modulul 4 — Audit"]
        AUD[audit_logs]
    end

    U -- "cumpără" --> TK
    U -- "validează (conductor)" --> VAL
    ST -- "plecare / sosire" --> TK
    TR -- "rulează pe" --> TK
    AUD -- "actor_user_id" --> U
    UNI -. "main_station_id" .-> ST
    U -. "home_station_id" .-> ST

    classDef m1 fill:#e3f2fd,stroke:#1565c0,color:#000;
    classDef m2 fill:#e8f5e9,stroke:#2e7d32,color:#000;
    classDef m3 fill:#fff3e0,stroke:#ef6c00,color:#000;
    classDef m4 fill:#fce4ec,stroke:#ad1457,color:#000;
    class M1 m1;
    class M2 m2;
    class M3 m3;
    class M4 m4;
```

> Schema reală conține **25 de tabele**, distribuite logic în cele 4 module de mai sus. Diagramele detaliate urmează pe module pentru lizibilitate.

---

## Modulul 1 — Identitate și Documente

```mermaid
erDiagram
    universities {
        int university_id PK
        string name
        string short_name
        string city
        string email_domain
        int main_station_id FK
        bool is_active
    }

    university_students {
        int enrollment_id PK
        int university_id FK
        string student_number
        string first_name
        string last_name
        string faculty
        int year_of_study
        string enrollment_status
        datetime enrollment_date
    }

    users {
        int user_id PK
        string first_name
        string last_name
        string email
        string password_hash
        string role
        int university_id FK
        int issuer_id FK
        int home_station_id FK
        bool mfa_enabled
        bool is_active
    }

    digital_identities {
        int identity_id PK
        int user_id FK
        string identity_code
        string status
        datetime expires_at
    }

    auth_methods {
        int method_id PK
        int user_id FK
        string method_type
        string method_value
        bool is_enabled
        datetime last_used_at
    }

    issuers {
        int id PK
        string name
        string issuer_type
        bool is_active
    }

    source_documents {
        int id PK
        int user_id FK
        string document_type
        string document_number_masked
        string status
        string university_name
        int year_of_study
        string ci_number
        string ci_name
        datetime uploaded_at
    }

    document_reviews {
        int id PK
        int document_id FK
        int reviewer_id FK
        string decision
        string notes
        datetime reviewed_at
    }

    user_credentials {
        int id PK
        int user_id FK
        int issuer_id FK
        string credential_type
        string claim_value
        string status
        datetime valid_until
    }

    digital_cards {
        int id PK
        int user_id FK
        int issuer_id FK
        string card_identifier
        string status
        datetime valid_until
    }

    card_presentations {
        int id PK
        int card_id FK
        string token_value
        datetime expires_at
        datetime used_at
        string status
    }

    card_verifications {
        int id PK
        int card_presentation_id FK
        int verifier_user_id FK
        datetime verification_time
        string result
        string notes
    }

    notifications {
        int id PK
        int user_id FK
        string category
        string title
        string message
        bool is_read
        datetime created_at
    }

    universities ||--o{ university_students : "înrolează"
    universities ||--o{ users : "are agenți/studenți"
    users ||--o| digital_identities : "are identitate"
    users ||--o{ auth_methods : "are metode auth"
    users ||--o{ source_documents : "depune"
    users ||--o{ document_reviews : "revizuiește (agent)"
    users ||--o{ user_credentials : "deține"
    users ||--o| digital_cards : "are card"
    users ||--o{ card_verifications : "verifică (conductor)"
    users ||--o{ notifications : "primește"
    users }o--o| issuers : "este afiliat (agent)"
    issuers ||--o{ user_credentials : "emite"
    issuers ||--o{ digital_cards : "emite"
    source_documents ||--o{ document_reviews : "este revizuit"
    digital_cards ||--o{ card_presentations : "generează"
    card_presentations ||--o{ card_verifications : "este scanat"
```

---

## Modulul 2 — Transport feroviar

```mermaid
erDiagram
    railway_operators {
        int operator_id PK
        string name
        string code
        string country
        string contact_email
        bool is_active
    }

    stations {
        int station_id PK
        string name
        string code
        string city
        decimal latitude
        decimal longitude
        bool is_university_hub
        int student_count
        bool is_active
    }

    routes {
        int route_id PK
        int operator_id FK
        string route_name
        string route_code
        int origin_station_id FK
        int destination_station_id FK
        decimal total_distance_km
        bool is_active
    }

    route_stops {
        int route_stop_id PK
        int route_id FK
        int station_id FK
        int stop_order
        decimal distance_from_origin_km
        datetime arrival_time
        datetime departure_time
    }

    trains {
        int train_id PK
        int operator_id FK
        int route_id FK
        string train_number
        string train_type
        int capacity_seats
        bool is_active
    }

    tariff_brackets {
        int id PK
        string train_category
        int train_class
        int km_from
        int km_to
        decimal price_ron
        datetime valid_from
        datetime valid_until
    }

    users_ref {
        int user_id PK
        string note "(vezi modulul 1)"
    }

    universities_ref {
        int university_id PK
        string note "(vezi modulul 1)"
    }

    railway_operators ||--o{ routes : "operează"
    railway_operators ||--o{ trains : "deține"
    railway_operators ||--o{ stations : "deservește (logic)"
    stations ||--o{ routes : "origine"
    stations ||--o{ routes : "destinație"
    routes ||--o{ route_stops : "are opriri"
    stations ||--o{ route_stops : "este oprire"
    routes ||--o{ trains : "rulează pe"
    stations ||--o{ users_ref : "home_station (FK din users)"
    stations ||--o{ universities_ref : "main_station (FK din universities)"
```

> Notă: `tariff_brackets` nu are FK direct către `trains` — este o tabelă de lookup, joinul se face în aplicație după `train_type → train_category` și distanța în km calculată din `route_stops`.

---

## Modulul 3 — Bilete și Validări

```mermaid
erDiagram
    tickets {
        int ticket_id PK
        int user_id FK
        int train_id FK
        int departure_station_id FK
        int arrival_station_id FK
        datetime travel_date
        string ticket_type
        string ticket_status
        decimal price
        decimal discount_applied
        datetime purchase_time
    }

    subscriptions {
        int subscription_id PK
        int user_id FK
        int operator_id FK
        string subscription_type
        datetime valid_from
        datetime valid_until
        decimal price
        decimal discount_applied
        string status
    }

    travel_entitlements {
        int entitlement_id PK
        int user_id FK
        int ticket_id FK
        int subscription_id FK
        string source_type
        datetime valid_from
        datetime valid_until
        string status
    }

    qr_tokens {
        int qr_token_id PK
        int entitlement_id FK
        string token_value
        string token_hash
        datetime expires_at
        datetime used_at
        string status
    }

    validations {
        int validation_id PK
        int qr_token_id FK
        int conductor_id FK
        int train_id FK
        datetime validation_time
        string validation_result
        string device_id
        string notes
    }

    users_ref {
        int user_id PK
        string note "(vezi modulul 1)"
    }

    trains_ref {
        int train_id PK
        string note "(vezi modulul 2)"
    }

    stations_ref {
        int station_id PK
        string note "(vezi modulul 2)"
    }

    operators_ref {
        int operator_id PK
        string note "(vezi modulul 2)"
    }

    users_ref ||--o{ tickets : "cumpără"
    users_ref ||--o{ subscriptions : "deține"
    users_ref ||--o{ travel_entitlements : "are drept"
    users_ref ||--o{ validations : "conductor"
    trains_ref ||--o{ tickets : "rulează"
    trains_ref ||--o{ validations : "în tren"
    stations_ref ||--o{ tickets : "plecare"
    stations_ref ||--o{ tickets : "sosire"
    operators_ref ||--o{ subscriptions : "emite abonament"
    tickets ||--o| travel_entitlements : "generează"
    subscriptions ||--o| travel_entitlements : "generează"
    travel_entitlements ||--o{ qr_tokens : "produce token-uri"
    qr_tokens ||--o{ validations : "este validat"
```

---

## Modulul 4 — Audit

```mermaid
erDiagram
    audit_logs {
        int audit_log_id PK
        int actor_user_id FK
        string action_type
        string target_table
        int target_id
        datetime action_timestamp
        string ip_address
        string details
    }

    users_ref {
        int user_id PK
        string note "(vezi modulul 1)"
    }

    users_ref ||--o{ audit_logs : "generează acțiuni"
```

---

## Descrierea entităților principale

### Modulul 1 — Identitate

#### `users`
Entitate centrală. Roluri posibile: `passenger`, `conductor`, `admin`, `university_agent`.
Câmpul `university_id` leagă studenții și agenții de universitatea lor, iar `home_station_id`
stabilește stația de domiciliu pentru calculul reducerii de 90% (OUG 11/2024).

#### `universities` & `university_students`
Universități partenere și baza locală de studenți înscriși. Agenții universitari văd doar cererile
studenților de la propria universitate. `main_station_id` indică stația centrului universitar.

#### `source_documents`
Cererea de verificare identitate (CI + legitimație). Include date extrase automat prin OCR/MRZ
(`ci_number`, `ci_name`, `ci_date_of_birth`, `ci_sex`, `ci_address`) și statusul fluxului
(`pending` / `approved` / `rejected`).

#### `document_reviews`
Log de aprobări/respingeri ale documentelor de către agenți universitari (audit per decizie).

#### `user_credentials`
Claim-uri verificabile emise după aprobare: `identity_verified`, `student_verified`,
`elev_verified` etc. Au valabilitate limitată (implicit 1 an).

#### `digital_cards`
Cardul digital unic per utilizator, emis după ce există cel puțin o credențială activă.
Relație 1:1 cu `users`.

#### `card_presentations` & `card_verifications`
Token-uri QR efemere (≈120s) generate de pasager pentru a-și prezenta identitatea, respectiv
log-ul scanărilor făcute de conductor (anti-replay).

#### `digital_identities` / `auth_methods` / `issuers` / `notifications`
Entități de suport: identitate conceptuală, metode de autentificare (parolă, TOTP, OTP),
autorități emitente (universități, autoritate feroviară) și notificări in-app.

### Modulul 2 — Transport feroviar

#### `railway_operators`
Operatorii feroviari (ex. CFR Călători, Softrans, Regio Călători). Cheie naturală: `code`.

#### `stations`
Stații feroviare cu coordonate GPS și metadate de tip „hub universitar” (folosite de
endpointurile `/map/*`). `is_university_hub` marchează stațiile principale ale centrelor
universitare.

#### `routes` & `route_stops`
Rute definite prin stația de origine, destinație și un lanț ordonat de opriri intermediare
(`route_stops.stop_order`) cu distanțe kilometrice cumulative — necesare la calculul prețului.

#### `trains`
Trenurile fizice, asociate unui operator și unei rute. Tipul (`regio`, `interregio`, `intercity`,
`express`, `high_speed`) determină categoria tarifară.

#### `tariff_brackets`
Tabelă lookup cu prețuri pe trepte de distanță (aproximează „Tariful 100” CFR). Joinul cu
trenurile se face în aplicație după (categorie, clasă, km).

### Modulul 3 — Bilete și Validări

#### `tickets`
Bilete individuale (`single`, `return`, `group`) cu preț, reducere aplicată și stații de
plecare/sosire. FK-uri către `users`, `trains`, `stations`.

#### `subscriptions`
Abonamente (`monthly`, `semester`, `annual`, `weekly`) emise de un operator, cu interval de
valabilitate și status (`active` / `expired` / `cancelled` / `suspended`).

#### `travel_entitlements`
Tabela unificatoare a drepturilor de călătorie. Un drept provine fie dintr-un `ticket`, fie
dintr-un `subscription`, fie dintr-un `benefit` (CHECK garantează exclusivitate). Permite
generarea uniformă de QR-uri pentru ambele tipuri.

#### `qr_tokens`
Token-uri QR single-use emise pentru un drept de călătorie. Stochează atât `token_value`
(payload semnat) cât și `token_hash` (pentru lookup rapid și anti-replay).

#### `validations`
Log-ul scanărilor făcute de conductor în tren. Reține rezultatul (`valid` / `invalid` /
`expired` / `already_used`), trenul, dispozitivul și conductorul care a scanat.

### Modulul 4 — Audit

#### `audit_logs`
Log cross-cutting pentru acțiuni sensibile: emitere credențiale, aprobare documente,
revocare card, validare bilete etc. Reține actorul (`actor_user_id`), tipul acțiunii, tabela și
ID-ul țintă, IP și un câmp liber `details` (JSON serializat sau text).

---

## Normalizare

Schema respectă **Forma Normală 3 (3NF)**: **25 de tabele organizate în 4 module logice**
(Identitate & Documente, Transport feroviar, Bilete & Validări, Audit), fără dependențe
tranzitive și cu fiecare atribut non-cheie depinzând exclusiv de cheia primară. Relațiile N:M
sunt descompuse prin tabele intermediare (`route_stops`, `travel_entitlements`), iar câmpurile
denormalizate intenționat (ex. `users.university_name`, `source_documents.university_name`)
sunt documentate explicit ca optimizări pentru filtrare fără JOIN.
