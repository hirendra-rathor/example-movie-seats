-- Frozen from fresh implementation 9af1797ea2e4851319dd4ecc26d104b455d3a570.
BEGIN TRANSACTION;
CREATE TABLE claims (
        seat TEXT PRIMARY KEY REFERENCES seats(id),
        reservation_id TEXT NOT NULL REFERENCES reservations(id));
INSERT INTO "claims" VALUES('A3','661c2128-1738-4497-8313-9f0abe3b7687');
INSERT INTO "claims" VALUES('A4','661c2128-1738-4497-8313-9f0abe3b7687');
INSERT INTO "claims" VALUES('B1','4c026e4a-3fff-4434-a89c-9e01128fd883');
INSERT INTO "claims" VALUES('B2','4c026e4a-3fff-4434-a89c-9e01128fd883');
CREATE TABLE requests (
                    request_key TEXT PRIMARY KEY,
                    reservation_id TEXT NOT NULL UNIQUE REFERENCES reservations(id));
INSERT INTO "requests" VALUES('legacy-held','661c2128-1738-4497-8313-9f0abe3b7687');
INSERT INTO "requests" VALUES('legacy-confirmed','4c026e4a-3fff-4434-a89c-9e01128fd883');
INSERT INTO "requests" VALUES('legacy-cancelled','6dbabea1-319e-4bd6-b222-d0b2a21e1891');
CREATE TABLE reservation_seats (
        reservation_id TEXT NOT NULL REFERENCES reservations(id),
        seat TEXT NOT NULL REFERENCES seats(id),
        PRIMARY KEY (reservation_id, seat));
INSERT INTO "reservation_seats" VALUES('661c2128-1738-4497-8313-9f0abe3b7687','A3');
INSERT INTO "reservation_seats" VALUES('661c2128-1738-4497-8313-9f0abe3b7687','A4');
INSERT INTO "reservation_seats" VALUES('4c026e4a-3fff-4434-a89c-9e01128fd883','B1');
INSERT INTO "reservation_seats" VALUES('4c026e4a-3fff-4434-a89c-9e01128fd883','B2');
INSERT INTO "reservation_seats" VALUES('6dbabea1-319e-4bd6-b222-d0b2a21e1891','C1');
INSERT INTO "reservation_seats" VALUES('6dbabea1-319e-4bd6-b222-d0b2a21e1891','C2');
CREATE TABLE reservations (id TEXT PRIMARY KEY, status TEXT NOT NULL);
INSERT INTO "reservations" VALUES('661c2128-1738-4497-8313-9f0abe3b7687','held');
INSERT INTO "reservations" VALUES('4c026e4a-3fff-4434-a89c-9e01128fd883','confirmed');
INSERT INTO "reservations" VALUES('6dbabea1-319e-4bd6-b222-d0b2a21e1891','cancelled');
CREATE TABLE seats (id TEXT PRIMARY KEY);
INSERT INTO "seats" VALUES('A1');
INSERT INTO "seats" VALUES('A2');
INSERT INTO "seats" VALUES('A3');
INSERT INTO "seats" VALUES('A4');
INSERT INTO "seats" VALUES('B1');
INSERT INTO "seats" VALUES('B2');
INSERT INTO "seats" VALUES('B3');
INSERT INTO "seats" VALUES('B4');
INSERT INTO "seats" VALUES('C1');
INSERT INTO "seats" VALUES('C2');
INSERT INTO "seats" VALUES('C3');
INSERT INTO "seats" VALUES('C4');
COMMIT;
PRAGMA user_version=2;
