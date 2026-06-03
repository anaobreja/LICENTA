# Modelul de Date — Diagrama Entitate-Relație

## Diagrama completă

```mermaid
erDiagram
    universities {
        int university_id PK
        string name
        string short_name
        string city
        string email_domain
    }

    users {
        int user_id PK
        string first_name
        string last_name
        string email
        string password_hash
        string role
        int university_id FK
        bool is_active
        string mfa_secret
        bool mfa_enabled
    }

    digital_identities {
        int identity_id PK
        int user_id FK
        string identity_code
        string status
        datetime expires_at
    }

    auth_methods {
        int auth_method_id PK
        int user_id FK
        string method_type
        string secret_value
        bool is_enabled
    }

    source_documents {
        int id PK
        int user_id FK
        string document_type
        string document_number_masked
        string document_image_path
        string status
        string university_name
        int year_of_study
        string ci_number
        string ci_name
        string ci_date_of_birth
        string ci_sex
    }

    document_reviews {
        int id PK
        int document_id FK
        int reviewer_id FK
        string decision
        string notes
        datetime reviewed_at
    }

    issuers {
        int id PK
        string name
        string issuer_type
        bool is_active
    }

    user_credentials {
        int id PK
        int user_id FK
        string credential_type
        string claim_value
        int issuer_id FK
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
    }

    universities ||--o{ users : "are agenti/studenti"
    users ||--o| digital_identities : "are identitate"
    users ||--o{ auth_methods : "are metode auth"
    users ||--o{ source_documents : "depune"
    users ||--o{ user_credentials : "detine"
    users ||--o| digital_cards : "are card"
    users ||--o{ notifications : "primeste"
    source_documents ||--o{ document_reviews : "este revizuit"
    issuers ||--o{ user_credentials : "emite"
    issuers ||--o{ digital_cards : "emite"
    digital_cards ||--o{ card_presentations : "genereaza"
    card_presentations ||--o{ card_verifications : "este verificat"
```

---

## Descrierea entităților principale

### `users`
Entitate centrală. Roluri posibile: `passenger`, `conductor`, `admin`, `university_agent`.
Câmpul `university_id` leagă studenții și agenții de universitatea lor.

### `source_documents`
Stochează cererea de verificare identitate depusă de student. Include:
- datele extrase automat din CI prin OCR MRZ (`ci_number`, `ci_name`, `ci_date_of_birth`, `ci_sex`)
- poza legitimației de student
- universitatea și anul de studiu

### `user_credentials`
Credentialele emise după aprobarea documentelor. Tipuri: `identity_verified`, `student_verified`.
Valabilitate limitată (implicit 1 an).

### `digital_cards`
Cardul digital emis utilizatorului după ce are cel puțin o credentiala activă.
Un utilizator → un singur card activ.

### `card_presentations`
Token-uri QR temporare (120 secunde) generate de pasager pentru prezentare în tren.
Fiecare scanare creează o înregistrare în `card_verifications`.

### `universities`
Universități partenere înregistrate în sistem. Agenții universitari sunt legați de o universitate
și văd doar cererile studenților de la acea universitate.

---

## Normalizare

Schema respectă **Forma Normală 3 (3NF)**:
- Fără dependențe tranzitive
- Fiecare atribut depinde doar de cheia primară
- Relații N:M descompuse prin tabele intermediare
