"""
TransitGPT - GTFS Data Ingestion Script
========================================
Before running this script, connect to PostgreSQL as a superuser and run:

    CREATE DATABASE transit_gpt;
    GRANT ALL PRIVILEGES ON DATABASE transit_gpt TO readonly_user;
    \c transit_gpt
    GRANT ALL ON SCHEMA public TO readonly_user;

Then run:  python ingest.py
"""

import os
import csv
import zipfile
import io
import sys
from datetime import datetime
import psycopg2
from psycopg2.extras import execute_values
from dotenv import load_dotenv

load_dotenv()

PG_USER = os.getenv("PG_USER")
PG_PASSWORD = os.getenv("PG_PASSWORD")
PG_PORT = os.getenv("PG_PORT", "5432")
PG_DB = os.getenv("TRANSIT_PG_DB", "transit_gpt")

DATA_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GTFS_DIR = os.path.join(DATA_ROOT, "gtfs")
DATA_SOURCES_CSV = os.path.join(DATA_ROOT, "data_sources.csv")

SCHEMA = """
CREATE TABLE IF NOT EXISTS agencies (
    custom_id     VARCHAR(100),
    agency_id     VARCHAR(200),
    agency_name   VARCHAR(500) NOT NULL,
    agency_url    VARCHAR(1000),
    agency_timezone VARCHAR(100),
    agency_lang   VARCHAR(20),
    agency_phone  VARCHAR(100),
    prov_terr     VARCHAR(5),
    PRIMARY KEY (custom_id, agency_id)
);

CREATE TABLE IF NOT EXISTS routes (
    custom_id        VARCHAR(100),
    route_id         VARCHAR(200),
    agency_id        VARCHAR(200),
    route_short_name VARCHAR(200),
    route_long_name  VARCHAR(1000),
    route_desc       TEXT,
    route_type       INTEGER,
    route_color      VARCHAR(20),
    route_text_color VARCHAR(20),
    PRIMARY KEY (custom_id, route_id)
);

CREATE TABLE IF NOT EXISTS stops (
    custom_id          VARCHAR(100),
    stop_id            VARCHAR(200),
    stop_code          VARCHAR(100),
    stop_name          VARCHAR(1000),
    stop_lat           DOUBLE PRECISION,
    stop_lon           DOUBLE PRECISION,
    location_type      INTEGER,
    parent_station     VARCHAR(200),
    wheelchair_boarding INTEGER,
    PRIMARY KEY (custom_id, stop_id)
);

CREATE TABLE IF NOT EXISTS trips (
    custom_id     VARCHAR(100),
    route_id      VARCHAR(200),
    service_id    VARCHAR(200),
    trip_id       VARCHAR(200),
    trip_headsign VARCHAR(1000),
    direction_id  INTEGER,
    PRIMARY KEY (custom_id, trip_id)
);

CREATE TABLE IF NOT EXISTS calendar (
    custom_id  VARCHAR(100),
    service_id VARCHAR(200),
    monday     BOOLEAN,
    tuesday    BOOLEAN,
    wednesday  BOOLEAN,
    thursday   BOOLEAN,
    friday     BOOLEAN,
    saturday   BOOLEAN,
    sunday     BOOLEAN,
    start_date DATE,
    end_date   DATE,
    PRIMARY KEY (custom_id, service_id)
);
"""


def parse_bool(val):
    return val.strip() == "1" if val and val.strip() else None


def parse_int(val):
    try:
        return int(val.strip()) if val and val.strip() else None
    except (ValueError, AttributeError):
        return None


def parse_float(val):
    try:
        return float(val.strip()) if val and val.strip() else None
    except (ValueError, AttributeError):
        return None


def parse_date(val):
    try:
        return datetime.strptime(val.strip(), "%Y%m%d").date() if val and val.strip() else None
    except (ValueError, AttributeError):
        return None


def read_csv_bytes(data: bytes) -> list:
    text = data.decode("utf-8-sig")
    reader = csv.DictReader(io.StringIO(text))
    return list(reader)


def get_gtfs_files(agency_dir: str) -> dict:
    """Return {filename: bytes} for all .txt files in the agency folder (or zip)."""
    files = {}
    zip_path = os.path.join(agency_dir, "gtfs.zip")
    if os.path.exists(zip_path):
        with zipfile.ZipFile(zip_path) as z:
            for name in z.namelist():
                if name.endswith(".txt"):
                    files[os.path.basename(name)] = z.read(name)
    else:
        for fname in os.listdir(agency_dir):
            if fname.endswith(".txt"):
                with open(os.path.join(agency_dir, fname), "rb") as f:
                    files[fname] = f.read()
    return files


def load_agencies(cur, custom_id, prov_terr, gtfs_files):
    if "agency.txt" not in gtfs_files:
        return 0
    rows = read_csv_bytes(gtfs_files["agency.txt"])
    data = []
    for row in rows:
        agency_id = row.get("agency_id", "").strip() or custom_id
        name = row.get("agency_name", "").strip()
        if not name:
            continue
        data.append((
            custom_id, agency_id, name,
            row.get("agency_url", "").strip(),
            row.get("agency_timezone", "").strip(),
            row.get("agency_lang", "").strip(),
            row.get("agency_phone", "").strip(),
            prov_terr,
        ))
    if data:
        execute_values(cur, """
            INSERT INTO agencies
                (custom_id, agency_id, agency_name, agency_url, agency_timezone, agency_lang, agency_phone, prov_terr)
            VALUES %s ON CONFLICT DO NOTHING
        """, data)
    return len(data)


def load_routes(cur, custom_id, gtfs_files):
    if "routes.txt" not in gtfs_files:
        return 0
    rows = read_csv_bytes(gtfs_files["routes.txt"])
    data = []
    for row in rows:
        route_id = row.get("route_id", "").strip()
        if not route_id:
            continue
        data.append((
            custom_id, route_id,
            row.get("agency_id", "").strip() or custom_id,
            row.get("route_short_name", "").strip(),
            row.get("route_long_name", "").strip(),
            row.get("route_desc", "").strip(),
            parse_int(row.get("route_type")),
            row.get("route_color", "").strip(),
            row.get("route_text_color", "").strip(),
        ))
    if data:
        execute_values(cur, """
            INSERT INTO routes
                (custom_id, route_id, agency_id, route_short_name, route_long_name, route_desc, route_type, route_color, route_text_color)
            VALUES %s ON CONFLICT DO NOTHING
        """, data)
    return len(data)


def load_stops(cur, custom_id, gtfs_files):
    if "stops.txt" not in gtfs_files:
        return 0
    rows = read_csv_bytes(gtfs_files["stops.txt"])
    data = []
    for row in rows:
        stop_id = row.get("stop_id", "").strip()
        if not stop_id:
            continue
        data.append((
            custom_id, stop_id,
            row.get("stop_code", "").strip(),
            row.get("stop_name", "").strip(),
            parse_float(row.get("stop_lat")),
            parse_float(row.get("stop_lon")),
            parse_int(row.get("location_type")),
            row.get("parent_station", "").strip(),
            parse_int(row.get("wheelchair_boarding")),
        ))
    if data:
        execute_values(cur, """
            INSERT INTO stops
                (custom_id, stop_id, stop_code, stop_name, stop_lat, stop_lon, location_type, parent_station, wheelchair_boarding)
            VALUES %s ON CONFLICT DO NOTHING
        """, data)
    return len(data)


def load_trips(cur, custom_id, gtfs_files):
    if "trips.txt" not in gtfs_files:
        return 0
    rows = read_csv_bytes(gtfs_files["trips.txt"])
    data = []
    for row in rows:
        trip_id = row.get("trip_id", "").strip()
        if not trip_id:
            continue
        data.append((
            custom_id,
            row.get("route_id", "").strip(),
            row.get("service_id", "").strip(),
            trip_id,
            row.get("trip_headsign", "").strip(),
            parse_int(row.get("direction_id")),
        ))
    if data:
        execute_values(cur, """
            INSERT INTO trips (custom_id, route_id, service_id, trip_id, trip_headsign, direction_id)
            VALUES %s ON CONFLICT DO NOTHING
        """, data)
    return len(data)


def load_calendar(cur, custom_id, gtfs_files):
    if "calendar.txt" not in gtfs_files:
        return 0
    rows = read_csv_bytes(gtfs_files["calendar.txt"])
    data = []
    for row in rows:
        service_id = row.get("service_id", "").strip()
        if not service_id:
            continue
        data.append((
            custom_id, service_id,
            parse_bool(row.get("monday")),
            parse_bool(row.get("tuesday")),
            parse_bool(row.get("wednesday")),
            parse_bool(row.get("thursday")),
            parse_bool(row.get("friday")),
            parse_bool(row.get("saturday")),
            parse_bool(row.get("sunday")),
            parse_date(row.get("start_date")),
            parse_date(row.get("end_date")),
        ))
    if data:
        execute_values(cur, """
            INSERT INTO calendar
                (custom_id, service_id, monday, tuesday, wednesday, thursday, friday, saturday, sunday, start_date, end_date)
            VALUES %s ON CONFLICT DO NOTHING
        """, data)
    return len(data)


def main():
    print(f"Connecting to PostgreSQL database '{PG_DB}' as '{PG_USER}'...")
    conn = psycopg2.connect(
        dbname=PG_DB, user=PG_USER, password=PG_PASSWORD,
        host="localhost", port=PG_PORT
    )
    cur = conn.cursor()

    print("Creating schema...")
    cur.execute(SCHEMA)
    conn.commit()

    prov_map = {}
    for enc in ("utf-8-sig", "utf-8", "cp1252", "latin-1"):
        try:
            with open(DATA_SOURCES_CSV, "r", encoding=enc) as f:
                for row in csv.DictReader(f):
                    prov_map[row["custom_id"].strip()] = row["prov_terr"].strip()
            break
        except (UnicodeDecodeError, UnicodeError):
            continue

    agency_dirs = sorted([
        d for d in os.listdir(GTFS_DIR)
        if os.path.isdir(os.path.join(GTFS_DIR, d))
    ])
    total = len(agency_dirs)
    print(f"Loading {total} agencies...\n")

    for i, folder in enumerate(agency_dirs):
        agency_dir = os.path.join(GTFS_DIR, folder)
        custom_id = folder
        prov_terr = prov_map.get(custom_id, "")
        try:
            gtfs_files = get_gtfs_files(agency_dir)
            n_a = load_agencies(cur, custom_id, prov_terr, gtfs_files)
            n_r = load_routes(cur, custom_id, gtfs_files)
            n_s = load_stops(cur, custom_id, gtfs_files)
            n_t = load_trips(cur, custom_id, gtfs_files)
            n_c = load_calendar(cur, custom_id, gtfs_files)
            conn.commit()
            print(f"  [{i+1}/{total}] {custom_id} ({prov_terr}): {n_a} agencies, {n_r} routes, {n_s} stops, {n_t} trips, {n_c} calendar entries")
        except Exception as e:
            conn.rollback()
            print(f"  [{i+1}/{total}] ERROR {custom_id}: {e}", file=sys.stderr)

    cur.close()
    conn.close()
    print("\nIngestion complete!")


if __name__ == "__main__":
    main()
