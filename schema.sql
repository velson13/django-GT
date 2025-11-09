
-- ===============================
-- Transactions
-- ===============================
CREATE TABLE
    IF NOT EXISTS gtbook_transakcije (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        klijent_id INTEGER NOT NULL REFERENCES gtbook_klijenti (id) ON DELETE CASCADE,
        dokument_id INTEGER REFERENCES gtbook_dokumenti (id) ON DELETE SET NULL,
        tra_tip TEXT NOT NULL CHECK (tra_tip IN ('isplata', 'uplata')),
        iznos NUMERIC NOT NULL,
        tra_datum DATE NOT NULL,
        vrsta TEXT CHECK (vrsta IN ('banka', 'gotovina', 'drugo')),
        napomena TEXT
    );
