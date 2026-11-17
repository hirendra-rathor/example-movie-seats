-- Frozen from fresh implementation edaddef6b4f46260ad0694930af343e4f2dafe11.
BEGIN TRANSACTION;
CREATE TABLE claims (
        seat TEXT PRIMARY KEY REFERENCES seats(id),
        reservation_id TEXT NOT NULL REFERENCES reservations(id));
INSERT INTO "claims" VALUES('A3','3c9e856b-271c-491d-8567-b74ae8fc2869');
INSERT INTO "claims" VALUES('A4','3c9e856b-271c-491d-8567-b74ae8fc2869');
CREATE TABLE reservation_seats (
        reservation_id TEXT NOT NULL REFERENCES reservations(id),
        seat TEXT NOT NULL REFERENCES seats(id),
        PRIMARY KEY (reservation_id, seat));
INSERT INTO "reservation_seats" VALUES('3c9e856b-271c-491d-8567-b74ae8fc2869','A3');
INSERT INTO "reservation_seats" VALUES('3c9e856b-271c-491d-8567-b74ae8fc2869','A4');
CREATE TABLE reservations (id TEXT PRIMARY KEY, status TEXT NOT NULL);
INSERT INTO "reservations" VALUES('3c9e856b-271c-491d-8567-b74ae8fc2869','held');
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
PRAGMA user_version=1;
