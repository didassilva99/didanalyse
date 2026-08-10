from __future__ import annotations

from pathlib import Path
from datetime import datetime, timezone
from collections.abc import Mapping
from zoneinfo import ZoneInfo
import csv
import hashlib
import os
import re
import sqlite3
import tempfile
import urllib.request

BASE_DIR = Path(__file__).resolve().parent
DATA_DIR = BASE_DIR / "data"
FIXTURES_DIR = DATA_DIR / "fixtures"
DB_PATH = DATA_DIR / "apostas.db"
SEASON = "2026/27"


class _CompatRow(Mapping):
    """Linha compatível com sqlite3.Row para o cliente libSQL."""

    def __init__(self, columns, values):
        self._columns = tuple(columns)
        self._values = tuple(values)
        self._index = {name: idx for idx, name in enumerate(self._columns)}

    def __getitem__(self, key):
        if isinstance(key, (int, slice)):
            return self._values[key]
        return self._values[self._index[key]]

    def __iter__(self):
        return iter(self._columns)

    def __len__(self):
        return len(self._columns)

    def keys(self):
        return list(self._columns)


class _LibsqlCursorAdapter:
    def __init__(self, cursor):
        self._cursor = cursor

    @property
    def description(self):
        return self._cursor.description

    @property
    def rowcount(self):
        return self._cursor.rowcount

    @property
    def lastrowid(self):
        return self._cursor.lastrowid

    def _columns(self):
        return [item[0] for item in (self._cursor.description or ())]

    def _convert(self, row):
        if row is None:
            return None
        columns = self._columns()
        return _CompatRow(columns, row) if columns else row

    def fetchone(self):
        return self._convert(self._cursor.fetchone())

    def fetchall(self):
        return [self._convert(row) for row in self._cursor.fetchall()]

    def fetchmany(self, size=None):
        rows = self._cursor.fetchmany(size) if size is not None else self._cursor.fetchmany()
        return [self._convert(row) for row in rows]

    def __iter__(self):
        columns = self._columns()
        while True:
            row = self._cursor.fetchone()
            if row is None:
                break
            yield _CompatRow(columns, row) if columns else row

    def __getattr__(self, name):
        return getattr(self._cursor, name)


class _LibsqlConnectionAdapter:
    """Adapta libSQL à interface já usada pela aplicação SQLite."""

    def __init__(self, connection):
        self._connection = connection
        self._total_changes = 0

    @property
    def total_changes(self):
        return self._total_changes

    def execute(self, sql, parameters=()):
        cursor = self._connection.execute(sql, parameters)
        if getattr(cursor, "rowcount", 0) and cursor.rowcount > 0:
            self._total_changes += cursor.rowcount
        return _LibsqlCursorAdapter(cursor)

    def executemany(self, sql, seq_of_parameters):
        cursor = self._connection.executemany(sql, seq_of_parameters)
        if getattr(cursor, "rowcount", 0) and cursor.rowcount > 0:
            self._total_changes += cursor.rowcount
        return _LibsqlCursorAdapter(cursor)

    def executescript(self, script):
        return self._connection.executescript(script)

    def commit(self):
        return self._connection.commit()

    def rollback(self):
        return self._connection.rollback()

    def sync(self):
        sync_method = getattr(self._connection, "sync", None)
        return sync_method() if sync_method else None

    def close(self):
        return self._connection.close()

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        try:
            if exc_type is None:
                # O site público utiliza um token Turso apenas de leitura.
                # Nesse modo não existe qualquer razão para emitir COMMIT.
                if not public_read_only_mode():
                    self.commit()
            else:
                if not public_read_only_mode():
                    self.rollback()
        finally:
            self.close()
        return False

    def __getattr__(self, name):
        return getattr(self._connection, name)


def _remote_database_credentials():
    url = os.getenv("TURSO_DATABASE_URL") or os.getenv("LIBSQL_URL")
    token = os.getenv("TURSO_AUTH_TOKEN") or os.getenv("LIBSQL_AUTH_TOKEN")

    # No Streamlit Community Cloud, lê também diretamente st.secrets.
    if not (url and token):
        try:
            import streamlit as st
            url = url or st.secrets.get("TURSO_DATABASE_URL", "")
            token = token or st.secrets.get("TURSO_AUTH_TOKEN", "")
        except Exception:
            pass

    return (str(url).strip() if url else "", str(token).strip() if token else "")


def using_remote_database() -> bool:
    url, token = _remote_database_credentials()
    return bool(url and token)


def public_read_only_mode() -> bool:
    value = os.getenv("MATCHLAB_PUBLIC_READ_ONLY", "").strip().lower()
    return value in {"1", "true", "yes", "sim", "on"}


LEAGUES = [
    ("Premier League", "Inglaterra"),
    ("Ligue 1", "França"),
    ("Serie A", "Itália"),
    ("LaLiga", "Espanha"),
    ("Liga Portugal", "Portugal"),
    ("Süper Lig", "Turquia"),
    ("Eredivisie", "Países Baixos"),
    ("Bundesliga", "Alemanha"),
    ("Pro League", "Bélgica"),
    ("Scottish Premiership", "Escócia"),
]

FIXTURE_FILES = {
    "premier_league.csv": "Premier League",
    "ligue_1.csv": "Ligue 1",
    "serie_a.csv": "Serie A",
    "laliga.csv": "LaLiga",
    "liga_portugal.csv": "Liga Portugal",
    "super_lig.csv": "Süper Lig",
    "eredivisie.csv": "Eredivisie",
    "bundesliga.csv": "Bundesliga",
}

# Listas iniciais de árbitros elegíveis/profissionais para 2026/27.
# Em algumas federações o mesmo grupo serve mais do que uma divisão.
# A aplicação permite adicionar ou desativar nomes durante a época.
REFEREES_BY_LEAGUE = {
    "Premier League": [
        "Adam Herczeg", "Andy Madley", "Anthony Taylor", "Ben Toner",
        "Chris Kavanagh", "Craig Pawson", "Darren England", "David Webb",
        "Dean Whitestone", "Farai Hallam", "Gavin Ward", "James Bell",
        "Jarred Gillett", "John Brooks", "Josh Smith", "Lewis Smith",
        "Matt Donohue", "Michael Oliver", "Michael Salisbury", "Peter Bankes",
        "Paul Tierney", "Rob Jones", "Ruebyn Ricardo", "Sam Barrott",
        "Simon Hooper", "Steve Martin", "Stuart Attwell", "Thomas Bramall",
        "Tim Robinson", "Tom Kirk", "Tony Harrington",
    ],
    "Ligue 1": [
        "Abdelatif Kherradji", "Bastien Dechepy", "Benoît Bastien",
        "Clément Turpin", "Eric Wattellier", "Florent Batta",
        "François Letexier", "Gaël Angoula", "Hakim Ben El Hadj",
        "Jérémie Pignard", "Jérôme Brisard", "Marc Bollengier",
        "Mathieu Vernice", "Pierre Gaillouste", "Romain Lissorgue",
        "Ruddy Buquet", "Stéphanie Frappart", "Thomas Léonard",
        "Willy Delajod",
    ],
    "Serie A": [
        "Alberto Santoro", "Andrea Calzavara", "Andrea Colombo",
        "Andrea Zanotti", "Antonio Rapuano", "Claudio Allegretta",
        "Daniele Chiffi", "Daniele Doveri", "Daniele Perenzoni",
        "Davide Massa", "Ermanno Feliciani", "Federico La Penna",
        "Francesco Fourneau", "Gianluca Manganiello", "Giovanni Ayroldi",
        "Giuseppe Collu", "Giuseppe Mucera", "Juan Luca Sacchi",
        "Kevin Bonacina", "Livio Marinelli", "Luca Pairetto",
        "Luca Zufferli", "Marco Di Bello", "Marco Guida",
        "Maria Sole Ferrieri Caputi", "Matteo Marchetti", "Matteo Marcenaro",
        "Maurizio Mariani", "Michael Fabbri", "Niccolò Turrini",
        "Paride Tremolada", "Simone Sozza",
    ],
    "LaLiga": [
        "Alejandro Muñiz Ruiz", "Alejandro Quintero González",
        "César Soto Grado", "Francisco José Hernández Maeso",
        "Guillermo Cuadra Fernández", "Iosu Galech Apezteguía",
        "Isidro Díaz de Mera Escuderos", "Javier Alberola Rojas",
        "Jesús Gil Manzano", "Jorge Figueroa Vázquez",
        "José Luis Guzmán Mansilla", "José Luis Munuera Montero",
        "José María Sánchez Martínez", "Juan Luis Pulido Santana",
        "Mateo Busquets Ferrer", "Miguel Ángel Ortiz Arias",
        "Miguel Sesma Espinosa", "Pablo González Fuertes",
        "Ricardo de Burgos Bengoetxea", "Víctor García Verdura",
    ],
    "Liga Portugal": [
        "André Narciso", "António Nobre", "Bruno Costa",
        "Cláudio Pereira", "David Silva", "Fábio Veríssimo",
        "Gustavo Correia", "Hélder Carvalho", "Hélder Malheiro",
        "Iancu Vasilica", "João Gonçalves", "João Pinheiro",
        "João Pinho", "Luís Godinho", "Manuel Mota", "Miguel Nogueira",
        "Nuno Almeida", "Ricardo Baixinho", "Tiago Martins",
    ],
    "Süper Lig": [
        "Abdullah Buğra Taşkınsoy", "Ali Şansalan", "Alper Akarsu",
        "Arda Kardeşler", "Atilla Karaoğlan", "Cihan Aydın",
        "Direnç Tonusluoğlu", "Emre Kargın", "Halil Umut Meler",
        "Kadir Sağlam", "Mehmet Türkmen", "Muhammet Ali Metoğlu",
        "Oğuzhan Aksu", "Oğuzhan Çakır", "Ozan Ergün",
        "Ümit Öztürk", "Yasin Kol", "Zorbay Küçük",
    ],
    "Eredivisie": [
        "Alex Bos", "Allard Lindhout", "Bas Nijhuis", "Clay Ruperti",
        "Danny Makkelie", "Dennis Higler", "Edwin van de Graaf",
        "Erwin Blank", "Jannick van der Laan", "Jeroen Manschot",
        "Joey Kooij", "Marc Nagtegaal", "Martin van den Kerkhof",
        "Patrick Inia", "Richard Martens", "Sam Dröge",
        "Sander van der Eijk", "Serdar Gözübüyük",
    ],
    "Bundesliga": [
        "Benjamin Brand", "Benjamin Cortus", "Christian Dingert",
        "Daniel Schlager", "Daniel Siebert", "Dr. Felix Brych",
        "Dr. Max Burda", "Florian Badstübner", "Florian Exner",
        "Harm Osmers", "Martin Petersen", "Matthias Jöllenbeck",
        "Richard Hempel", "Robert Hartmann", "Robert Schröder",
        "Robin Braun", "Sascha Stegemann", "Sören Storks",
        "Sven Jablonski", "Timo Gerach", "Tobias Reichel",
        "Tobias Stieler",
    ],
    "Pro League": [
        "Anthony Letellier", "Arthur Denil", "Bert Put", "Bert Verbeke",
        "Bram Van Driessche", "Brent Staessens", "Erik Lambrechts",
        "Jan Boterberg", "Jasper Vergoote", "Jonathan Lardot",
        "Jordy Vermeire", "Kevin Van Damme", "Lawrence Visser",
        "Lothar D'Hondt", "Massimiliano Ledda", "Matonga Simonini",
        "Michiel Allaerts", "Nathan Verboomen", "Nicolas Laforge",
        "Simon Bourdeaud'hui", "Théophile Diskeuve", "Wesli De Cremer",
        "Wim Smet",
    ],
}

REFEREE_SOURCE_NOTES = {
    "Premier League": "Grupo profissional 2026/27 (serve Premier League e Championship)",
    "Ligue 1": "Afectações federais 2026/27",
    "Serie A": "Grupo CAN elegível para Serie A/Serie B",
    "LaLiga": "Plantilla de árbitros de Primera División",
    "Liga Portugal": "Lista inicial de árbitros profissionais; editável",
    "Süper Lig": "Üst Klasman 2026/27",
    "Eredivisie": "Grupo profissional KNVB; editável",
    "Bundesliga": "Quadro Bundesliga 2026/27",
    "Pro League": "Árbitros do futebol profissional belga",
}


BELGIUM_ICS_URL = "https://www.voetbalkrant.com/soccer/calendar/competition/competition_1_nl.ics"

BELGIUM_ALIASES = {
    "Anderlecht": "RSC Anderlecht",
    "RSC Anderlecht": "RSC Anderlecht",
    "Antwerp": "Royal Antwerp FC",
    "Royal Antwerp": "Royal Antwerp FC",
    "Royal Antwerp FC": "Royal Antwerp FC",
    "Beveren": "SK Beveren",
    "SK Beveren": "SK Beveren",
    "Cercle Brugge": "Cercle Brugge",
    "Club Brugge": "Club Brugge",
    "Genk": "KRC Genk",
    "KRC Genk": "KRC Genk",
    "Gent": "KAA Gent",
    "KAA Gent": "KAA Gent",
    "Kortrijk": "KV Kortrijk",
    "KV Kortrijk": "KV Kortrijk",
    "Lommel": "Lommel SK",
    "Lommel SK": "Lommel SK",
    "Mechelen": "KV Mechelen",
    "KV Mechelen": "KV Mechelen",
    "OH Leuven": "OH Leuven",
    "Oud-Heverlee Leuven": "OH Leuven",
    "RAAL La Louvière": "RAAL La Louvière",
    "RAAL La Louviere": "RAAL La Louvière",
    "Sint-Truiden": "STVV",
    "St. Truiden": "STVV",
    "STVV": "STVV",
    "Charleroi": "Sporting Charleroi",
    "Sporting Charleroi": "Sporting Charleroi",
    "Standard": "Standard de Liège",
    "Standard Liege": "Standard de Liège",
    "Standard Liège": "Standard de Liège",
    "Standard de Liège": "Standard de Liège",
    "Union SG": "Royale Union Saint-Gilloise",
    "Union St.-Gilloise": "Royale Union Saint-Gilloise",
    "Union Saint-Gilloise": "Royale Union Saint-Gilloise",
    "Royale Union Saint-Gilloise": "Royale Union Saint-Gilloise",
    "Westerlo": "KVC Westerlo",
    "KVC Westerlo": "KVC Westerlo",
    "Zulte Waregem": "SV Zulte Waregem",
    "SV Zulte Waregem": "SV Zulte Waregem",
}


def get_connection():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    remote_url, auth_token = _remote_database_credentials()

    if remote_url and auth_token:
        try:
            import libsql
        except ImportError as exc:
            raise RuntimeError(
                "A ligação à base Turso requer o pacote 'libsql'. "
                "Instala as dependências do requirements.txt."
            ) from exc

        url_hash = hashlib.sha256(remote_url.encode("utf-8")).hexdigest()[:12]
        replica_path = Path(tempfile.gettempdir()) / f"matchlab_{url_hash}.db"

        def _open_replica():
            return libsql.connect(
                str(replica_path),
                sync_url=remote_url,
                auth_token=auth_token,
                sync_interval=60,
            )

        try:
            raw_connection = _open_replica()
        except Exception as exc:
            # Recupera automaticamente de uma réplica temporária interrompida.
            if "metadata file exists but db file does not" not in str(exc).lower():
                raise
            for candidate in replica_path.parent.glob(replica_path.name + "*"):
                try:
                    candidate.unlink()
                except OSError:
                    pass
            raw_connection = _open_replica()

        connection = _LibsqlConnectionAdapter(raw_connection)
        connection.sync()
        if not public_read_only_mode():
            connection.execute("PRAGMA foreign_keys = ON")
        return connection

    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    return conn


def _columns(conn, table):
    return {row["name"] for row in conn.execute(f"PRAGMA table_info({table})")}


def _add_column(conn, table, name, definition):
    if name not in _columns(conn, table):
        conn.execute(f"ALTER TABLE {table} ADD COLUMN {name} {definition}")


def _ensure_schema(conn):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS leagues (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            country TEXT NOT NULL,
            season TEXT NOT NULL DEFAULT '2026/27'
        );

        CREATE TABLE IF NOT EXISTS teams (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            league_id INTEGER NOT NULL,
            name TEXT NOT NULL,
            UNIQUE(league_id, name),
            FOREIGN KEY (league_id) REFERENCES leagues(id)
        );

        CREATE TABLE IF NOT EXISTS referees (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT NOT NULL UNIQUE,
            active INTEGER NOT NULL DEFAULT 1
        );

        CREATE TABLE IF NOT EXISTS referee_leagues (
            referee_id INTEGER NOT NULL,
            league_id INTEGER NOT NULL,
            season TEXT NOT NULL DEFAULT '2026/27',
            active INTEGER NOT NULL DEFAULT 1,
            source_note TEXT,
            PRIMARY KEY (referee_id, league_id, season),
            FOREIGN KEY (referee_id) REFERENCES referees(id),
            FOREIGN KEY (league_id) REFERENCES leagues(id)
        );

        CREATE TABLE IF NOT EXISTS app_state (
            key TEXT PRIMARY KEY,
            value TEXT
        );

        CREATE TABLE IF NOT EXISTS transfers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            league_id INTEGER NOT NULL,
            team_id INTEGER NOT NULL,
            season TEXT NOT NULL DEFAULT '2026/27',
            direction TEXT NOT NULL CHECK(direction IN ('IN','OUT')),
            player_name TEXT NOT NULL,
            position TEXT,
            counterpart TEXT,
            fee_m REAL,
            movement_type TEXT,
            impact REAL NOT NULL DEFAULT 0,
            manual_importance REAL,
            source_name TEXT,
            source_url TEXT,
            fetched_at TEXT,
            confirmed INTEGER NOT NULL DEFAULT 1,
            UNIQUE(team_id,season,direction,player_name,counterpart),
            FOREIGN KEY (league_id) REFERENCES leagues(id),
            FOREIGN KEY (team_id) REFERENCES teams(id)
        );

        CREATE TABLE IF NOT EXISTS transfer_team_scores (
            team_id INTEGER NOT NULL,
            season TEXT NOT NULL DEFAULT '2026/27',
            arrivals INTEGER NOT NULL DEFAULT 0,
            departures INTEGER NOT NULL DEFAULT 0,
            incoming_value REAL NOT NULL DEFAULT 0,
            outgoing_value REAL NOT NULL DEFAULT 0,
            attack_delta REAL NOT NULL DEFAULT 0,
            midfield_delta REAL NOT NULL DEFAULT 0,
            defence_delta REAL NOT NULL DEFAULT 0,
            goalkeeper_delta REAL NOT NULL DEFAULT 0,
            overall_delta REAL NOT NULL DEFAULT 0,
            manual_override REAL,
            updated_at TEXT,
            PRIMARY KEY(team_id,season),
            FOREIGN KEY (team_id) REFERENCES teams(id)
        );

        CREATE INDEX IF NOT EXISTS ix_transfers_team_season
        ON transfers(team_id, season);

        CREATE TABLE IF NOT EXISTS matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            league_id INTEGER NOT NULL,
            season TEXT NOT NULL DEFAULT '2026/27',
            round_number INTEGER,
            match_date TEXT,
            match_time TEXT,
            home_team_id INTEGER NOT NULL,
            away_team_id INTEGER NOT NULL,
            stadium TEXT,
            status TEXT NOT NULL DEFAULT 'Agendado',
            referee_id INTEGER,
            temperature REAL,
            rain INTEGER DEFAULT 0,
            ht_home_goals INTEGER,
            ht_away_goals INTEGER,
            ft_home_goals INTEGER,
            ft_away_goals INTEGER,
            goal_minutes TEXT,
            sh_home_goals INTEGER,
            sh_away_goals INTEGER,

            fh_home_xg REAL,
            fh_away_xg REAL,
            sh_home_xg REAL,
            sh_away_xg REAL,
            fh_home_shots INTEGER,
            fh_away_shots INTEGER,
            sh_home_shots INTEGER,
            sh_away_shots INTEGER,
            fh_home_shots_on_target INTEGER,
            fh_away_shots_on_target INTEGER,
            sh_home_shots_on_target INTEGER,
            sh_away_shots_on_target INTEGER,
            fh_home_corners INTEGER,
            fh_away_corners INTEGER,
            sh_home_corners INTEGER,
            sh_away_corners INTEGER,
            fh_home_fouls INTEGER,
            fh_away_fouls INTEGER,
            sh_home_fouls INTEGER,
            sh_away_fouls INTEGER,
            fh_home_offsides INTEGER,
            fh_away_offsides INTEGER,
            sh_home_offsides INTEGER,
            sh_away_offsides INTEGER,
            fh_home_yellow INTEGER,
            fh_away_yellow INTEGER,
            sh_home_yellow INTEGER,
            sh_away_yellow INTEGER,
            fh_home_red INTEGER,
            fh_away_red INTEGER,
            sh_home_red INTEGER,
            sh_away_red INTEGER,
            stats_split_confirmed INTEGER NOT NULL DEFAULT 0,

            home_xg REAL,
            away_xg REAL,
            home_shots INTEGER,
            away_shots INTEGER,
            home_shots_on_target INTEGER,
            away_shots_on_target INTEGER,
            home_corners INTEGER,
            away_corners INTEGER,
            home_fouls INTEGER,
            away_fouls INTEGER,
            home_offsides INTEGER,
            away_offsides INTEGER,
            home_yellow INTEGER,
            away_yellow INTEGER,
            home_red INTEGER,
            away_red INTEGER,
            notes TEXT,
            source TEXT,
            source_match_number TEXT,
            sofascore_event_id INTEGER,
            schedule_provisional INTEGER DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (league_id) REFERENCES leagues(id),
            FOREIGN KEY (home_team_id) REFERENCES teams(id),
            FOREIGN KEY (away_team_id) REFERENCES teams(id),
            FOREIGN KEY (referee_id) REFERENCES referees(id)
        );
        """
    )
    # Migração para instalações anteriores.
    for name, definition in [
        ("season", "TEXT NOT NULL DEFAULT '2026/27'"),
        ("source", "TEXT"),
        ("source_match_number", "TEXT"),
        ("sofascore_event_id", "INTEGER"),
        ("schedule_provisional", "INTEGER DEFAULT 1"),
        ("sh_home_goals", "INTEGER"),
        ("sh_away_goals", "INTEGER"),
        ("fh_home_xg", "REAL"),
        ("fh_home_shots", "INTEGER"),
        ("fh_home_shots_on_target", "INTEGER"),
        ("fh_home_corners", "INTEGER"),
        ("fh_home_fouls", "INTEGER"),
        ("fh_home_offsides", "INTEGER"),
        ("fh_home_yellow", "INTEGER"),
        ("fh_home_red", "INTEGER"),
        ("fh_away_xg", "REAL"),
        ("fh_away_shots", "INTEGER"),
        ("fh_away_shots_on_target", "INTEGER"),
        ("fh_away_corners", "INTEGER"),
        ("fh_away_fouls", "INTEGER"),
        ("fh_away_offsides", "INTEGER"),
        ("fh_away_yellow", "INTEGER"),
        ("fh_away_red", "INTEGER"),
        ("sh_home_xg", "REAL"),
        ("sh_home_shots", "INTEGER"),
        ("sh_home_shots_on_target", "INTEGER"),
        ("sh_home_corners", "INTEGER"),
        ("sh_home_fouls", "INTEGER"),
        ("sh_home_offsides", "INTEGER"),
        ("sh_home_yellow", "INTEGER"),
        ("sh_home_red", "INTEGER"),
        ("sh_away_xg", "REAL"),
        ("sh_away_shots", "INTEGER"),
        ("sh_away_shots_on_target", "INTEGER"),
        ("sh_away_corners", "INTEGER"),
        ("sh_away_fouls", "INTEGER"),
        ("sh_away_offsides", "INTEGER"),
        ("sh_away_yellow", "INTEGER"),
        ("sh_away_red", "INTEGER"),
        ("stats_split_confirmed", "INTEGER NOT NULL DEFAULT 0"),
    ]:
        _add_column(conn, "matches", name, definition)

    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_match_sofascore_event
        ON matches(sofascore_event_id) WHERE sofascore_event_id IS NOT NULL
        """
    )

    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS ux_match_fixture
        ON matches(league_id, season, round_number, home_team_id, away_team_id)
        """
    )


def _ensure_leagues(conn):
    conn.executemany(
        "INSERT OR IGNORE INTO leagues(name, country, season) VALUES (?, ?, ?)",
        [(name, country, SEASON) for name, country in LEAGUES],
    )



def _ensure_referees(conn):
    _add_column(conn, "referees", "active", "INTEGER NOT NULL DEFAULT 1")
    league_ids = {row["name"]: row["id"] for row in conn.execute("SELECT id,name FROM leagues")}
    for league_name, names in REFEREES_BY_LEAGUE.items():
        league_id = league_ids.get(league_name)
        if not league_id:
            continue
        note = REFEREE_SOURCE_NOTES.get(league_name, "Lista inicial 2026/27")
        for name in names:
            clean = " ".join(name.strip().split())
            conn.execute(
                "INSERT OR IGNORE INTO referees(name,active) VALUES(?,1)",
                (clean,),
            )
            referee_id = conn.execute(
                "SELECT id FROM referees WHERE name=?", (clean,)
            ).fetchone()["id"]
            conn.execute(
                """
                INSERT OR IGNORE INTO referee_leagues(
                    referee_id,league_id,season,active,source_note
                ) VALUES(?,?,?,1,?)
                """,
                (referee_id, league_id, SEASON, note),
            )


def add_referee_to_league(conn, name, league_id, source_note="Adicionado manualmente"):
    clean = " ".join(str(name).strip().split())
    if not clean:
        return None
    conn.execute("INSERT OR IGNORE INTO referees(name,active) VALUES(?,1)", (clean,))
    referee_id = conn.execute("SELECT id FROM referees WHERE name=?", (clean,)).fetchone()["id"]
    conn.execute(
        """
        INSERT INTO referee_leagues(referee_id,league_id,season,active,source_note)
        VALUES(?,?,?,1,?)
        ON CONFLICT(referee_id,league_id,season)
        DO UPDATE SET active=1,source_note=excluded.source_note
        """,
        (referee_id, league_id, SEASON, source_note),
    )
    return referee_id


def referees_for_league(conn, league_id, include_inactive=False):
    condition = "" if include_inactive else "AND rl.active=1 AND r.active=1"
    return conn.execute(
        f"""
        SELECT r.id,r.name,rl.active,rl.source_note
        FROM referee_leagues rl
        JOIN referees r ON r.id=rl.referee_id
        WHERE rl.league_id=? AND rl.season=? {condition}
        ORDER BY r.name
        """,
        (league_id, SEASON),
    ).fetchall()


def _team_id(conn, league_id, name):
    clean = " ".join(str(name).strip().split())
    conn.execute(
        "INSERT OR IGNORE INTO teams(league_id, name) VALUES (?, ?)",
        (league_id, clean),
    )
    row = conn.execute(
        "SELECT id FROM teams WHERE league_id=? AND name=?",
        (league_id, clean),
    ).fetchone()
    return row["id"]


def _parse_fixture_date(value):
    value = (value or "").strip()
    if not value:
        return "", ""
    for fmt in ("%d/%m/%Y %H:%M", "%Y-%m-%d %H:%M", "%d/%m/%Y"):
        try:
            dt = datetime.strptime(value, fmt)
            return dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M") if "%H" in fmt else ""
        except ValueError:
            pass
    return value, ""


def seed_bundled_fixtures(conn):
    league_ids = {r["name"]: r["id"] for r in conn.execute("SELECT id,name FROM leagues")}
    inserted = 0
    for filename, league_name in FIXTURE_FILES.items():
        path = FIXTURES_DIR / filename
        if not path.exists():
            continue
        league_id = league_ids[league_name]
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            reader = csv.DictReader(handle)
            for row in reader:
                home = (row.get("Home Team") or "").strip()
                away = (row.get("Away Team") or "").strip()
                if not home or not away:
                    continue
                home_id = _team_id(conn, league_id, home)
                away_id = _team_id(conn, league_id, away)
                match_date, match_time = _parse_fixture_date(row.get("Date"))
                before = conn.total_changes
                conn.execute(
                    """
                    INSERT OR IGNORE INTO matches(
                        league_id, season, round_number, match_date, match_time,
                        home_team_id, away_team_id, stadium, status,
                        source, source_match_number, schedule_provisional
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Agendado', ?, ?, 1)
                    """,
                    (
                        league_id, SEASON, int(row.get("Round Number") or 0),
                        match_date, match_time, home_id, away_id,
                        (row.get("Location") or "").strip(),
                        "FixtureDownload", (row.get("Match Number") or "").strip(),
                    ),
                )
                if conn.total_changes > before:
                    inserted += 1
    return inserted


def _unfold_ics(text):
    lines = []
    for raw in text.replace("\r\n", "\n").replace("\r", "\n").split("\n"):
        if raw.startswith((" ", "\t")) and lines:
            lines[-1] += raw[1:]
        else:
            lines.append(raw)
    return lines


def _parse_ics_datetime(line):
    _, value = line.split(":", 1)
    params = line.split(":", 1)[0]
    tzid = None
    m = re.search(r"TZID=([^;:]+)", params)
    if m:
        tzid = m.group(1)
    value = value.strip()
    if len(value) == 8:
        dt = datetime.strptime(value, "%Y%m%d")
        return dt.strftime("%Y-%m-%d"), ""
    if value.endswith("Z"):
        dt = datetime.strptime(value, "%Y%m%dT%H%M%SZ").replace(tzinfo=timezone.utc)
        dt = dt.astimezone(ZoneInfo("Europe/Lisbon"))
    else:
        fmt = "%Y%m%dT%H%M%S" if len(value) >= 15 else "%Y%m%dT%H%M"
        dt = datetime.strptime(value[:15] if fmt.endswith("%S") else value[:13], fmt)
        if tzid:
            try:
                dt = dt.replace(tzinfo=ZoneInfo(tzid)).astimezone(ZoneInfo("Europe/Lisbon"))
            except Exception:
                pass
    return dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M")


def _split_summary(summary):
    clean = summary.replace("\\,", ",").strip()
    for sep in (" - ", " – ", " — ", " vs ", " v "):
        if sep in clean:
            parts = clean.split(sep, 1)
            return parts[0].strip(), parts[1].strip()
    return None, None


def _belgium_name(name):
    name = re.sub(r"\s+", " ", name.strip())
    return BELGIUM_ALIASES.get(name, name)


def fetch_belgium_calendar(conn, force=False):
    league = conn.execute("SELECT id FROM leagues WHERE name='Pro League'").fetchone()
    if not league:
        return 0, "Liga belga não encontrada."
    league_id = league["id"]
    existing = conn.execute(
        "SELECT COUNT(*) AS n FROM matches WHERE league_id=? AND season=?",
        (league_id, SEASON),
    ).fetchone()["n"]
    if existing >= 300 and not force:
        return 0, f"Calendário belga já contém {existing} jogos."

    request = urllib.request.Request(
        BELGIUM_ICS_URL,
        headers={"User-Agent": "Mozilla/5.0 AnaliseApostas/1.0"},
    )
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            text = response.read().decode("utf-8", errors="replace")
    except Exception as exc:
        return 0, f"Não foi possível descarregar a Bélgica: {exc}"

    events = []
    current = None
    for line in _unfold_ics(text):
        if line == "BEGIN:VEVENT":
            current = {}
        elif line == "END:VEVENT" and current is not None:
            events.append(current)
            current = None
        elif current is not None and ":" in line:
            key = line.split(":", 1)[0].split(";", 1)[0]
            if key in {"DTSTART", "SUMMARY", "LOCATION", "UID"}:
                current[key] = line

    parsed = []
    for event in events:
        summary_line = event.get("SUMMARY", "")
        summary = summary_line.split(":", 1)[1] if ":" in summary_line else ""
        home, away = _split_summary(summary)
        if not home or not away or "2026" not in event.get("DTSTART", "") and "2027" not in event.get("DTSTART", ""):
            continue
        try:
            date, time = _parse_ics_datetime(event["DTSTART"])
        except Exception:
            continue
        if not ("2026-08-01" <= date <= "2027-06-30"):
            continue
        location_line = event.get("LOCATION", "")
        location = location_line.split(":", 1)[1].replace("\\,", ",") if ":" in location_line else ""
        parsed.append({
            "date": date, "time": time,
            "home": _belgium_name(home), "away": _belgium_name(away),
            "location": location.strip(),
            "uid": event.get("UID", "").split(":",1)[-1],
        })

    # Ordenação cronológica e agrupamento de 9 jogos por jornada.
    parsed.sort(key=lambda x: (x["date"], x["time"], x["home"], x["away"]))
    if len(parsed) > 306:
        parsed = parsed[:306]
    inserted = 0
    for index, row in enumerate(parsed):
        round_number = index // 9 + 1
        home_id = _team_id(conn, league_id, row["home"])
        away_id = _team_id(conn, league_id, row["away"])
        before = conn.total_changes
        conn.execute(
            """
            INSERT OR IGNORE INTO matches(
                league_id, season, round_number, match_date, match_time,
                home_team_id, away_team_id, stadium, status,
                source, source_match_number, schedule_provisional
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, 'Agendado', ?, ?, 1)
            """,
            (
                league_id, SEASON, round_number, row["date"], row["time"],
                home_id, away_id, row["location"], "Voetbalkrant ICS", row["uid"],
            ),
        )
        if conn.total_changes > before:
            inserted += 1
    conn.commit()
    if not parsed:
        return 0, "O ficheiro belga foi obtido, mas não foi possível interpretar jogos."
    return inserted, f"Bélgica: {len(parsed)} jogos encontrados; {inserted} adicionados."


def auto_fetch_belgium_once():
    with get_connection() as conn:
        attempted = conn.execute("SELECT value FROM app_state WHERE key='belgium_auto_attempted'").fetchone()
        if attempted:
            return 0, "A tentativa automática já foi efetuada."
        conn.execute("INSERT OR REPLACE INTO app_state(key,value) VALUES('belgium_auto_attempted',CURRENT_TIMESTAMP)")
        conn.commit()
        return fetch_belgium_calendar(conn, force=False)




def _ensure_player_schema(conn):
    """Estrutura para estatística individual por jogo e médias da época."""
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS players (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            sofascore_player_id INTEGER UNIQUE,
            team_id INTEGER,
            name TEXT NOT NULL,
            short_name TEXT,
            position TEXT,
            shirt_number INTEGER,
            nationality TEXT,
            active INTEGER NOT NULL DEFAULT 1,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (team_id) REFERENCES teams(id)
        );

        CREATE TABLE IF NOT EXISTS player_match_stats (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            match_id INTEGER NOT NULL,
            player_id INTEGER NOT NULL,
            team_id INTEGER NOT NULL,
            season TEXT NOT NULL DEFAULT '2026/27',
            started INTEGER NOT NULL DEFAULT 0,
            substitute INTEGER NOT NULL DEFAULT 0,
            minutes REAL,
            rating REAL,
            goals REAL DEFAULT 0,
            assists REAL DEFAULT 0,
            xg REAL,
            xa REAL,
            shots REAL,
            shots_on_target REAL,
            key_passes REAL,
            passes_total REAL,
            passes_accurate REAL,
            touches REAL,
            tackles REAL,
            interceptions REAL,
            clearances REAL,
            blocks REAL,
            duels REAL,
            duels_won REAL,
            aerial_duels REAL,
            aerial_duels_won REAL,
            fouls REAL,
            fouled REAL,
            offsides REAL,
            yellow_cards REAL DEFAULT 0,
            red_cards REAL DEFAULT 0,
            saves REAL,
            goals_prevented REAL,
            possession_lost REAL,
            dispossessed REAL,
            stats_json TEXT,
            source TEXT NOT NULL DEFAULT 'SofaScore',
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(match_id, player_id),
            FOREIGN KEY (match_id) REFERENCES matches(id),
            FOREIGN KEY (player_id) REFERENCES players(id),
            FOREIGN KEY (team_id) REFERENCES teams(id)
        );

        CREATE INDEX IF NOT EXISTS ix_player_stats_season
        ON player_match_stats(season, player_id);

        CREATE INDEX IF NOT EXISTS ix_player_stats_team
        ON player_match_stats(team_id, season);
        """
    )

def _ensure_history_schema(conn):
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS team_external_ids (
            team_id INTEGER NOT NULL,
            league_id INTEGER NOT NULL,
            external_team_id INTEGER NOT NULL,
            source TEXT NOT NULL DEFAULT 'SofaScore',
            external_name TEXT,
            PRIMARY KEY (league_id, external_team_id),
            FOREIGN KEY (team_id) REFERENCES teams(id),
            FOREIGN KEY (league_id) REFERENCES leagues(id)
        );

        CREATE TABLE IF NOT EXISTS historical_matches (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            target_league_id INTEGER NOT NULL,
            source_level INTEGER NOT NULL DEFAULT 1,
            source_tournament_id INTEGER,
            source_season_id INTEGER,
            source_event_id INTEGER NOT NULL UNIQUE,
            season TEXT NOT NULL DEFAULT '2025/26',
            round_number INTEGER,
            match_date TEXT,
            match_time TEXT,
            home_team_name TEXT NOT NULL,
            away_team_name TEXT NOT NULL,
            home_external_id INTEGER,
            away_external_id INTEGER,
            home_current_team_id INTEGER,
            away_current_team_id INTEGER,
            referee_name TEXT,
            stadium TEXT,
            ht_home_goals INTEGER,
            ht_away_goals INTEGER,
            sh_home_goals INTEGER,
            sh_away_goals INTEGER,
            ft_home_goals INTEGER,
            ft_away_goals INTEGER,
            goal_minutes TEXT,
            fh_home_xg REAL, fh_away_xg REAL, sh_home_xg REAL, sh_away_xg REAL, home_xg REAL, away_xg REAL,
            fh_home_shots REAL, fh_away_shots REAL, sh_home_shots REAL, sh_away_shots REAL, home_shots REAL, away_shots REAL,
            fh_home_shots_on_target REAL, fh_away_shots_on_target REAL,
            sh_home_shots_on_target REAL, sh_away_shots_on_target REAL,
            home_shots_on_target REAL, away_shots_on_target REAL,
            fh_home_corners REAL, fh_away_corners REAL, sh_home_corners REAL, sh_away_corners REAL, home_corners REAL, away_corners REAL,
            fh_home_fouls REAL, fh_away_fouls REAL, sh_home_fouls REAL, sh_away_fouls REAL, home_fouls REAL, away_fouls REAL,
            fh_home_offsides REAL, fh_away_offsides REAL, sh_home_offsides REAL, sh_away_offsides REAL, home_offsides REAL, away_offsides REAL,
            fh_home_yellow REAL, fh_away_yellow REAL, sh_home_yellow REAL, sh_away_yellow REAL, home_yellow REAL, away_yellow REAL,
            fh_home_red REAL, fh_away_red REAL, sh_home_red REAL, sh_away_red REAL, home_red REAL, away_red REAL,
            stats_split_available INTEGER NOT NULL DEFAULT 0,
            source TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (target_league_id) REFERENCES leagues(id),
            FOREIGN KEY (home_current_team_id) REFERENCES teams(id),
            FOREIGN KEY (away_current_team_id) REFERENCES teams(id)
        );

        CREATE TABLE IF NOT EXISTS historical_imports (
            target_league_id INTEGER NOT NULL,
            season TEXT NOT NULL,
            top_tournament_id INTEGER,
            second_tournament_id INTEGER,
            imported_matches INTEGER NOT NULL DEFAULT 0,
            error_count INTEGER NOT NULL DEFAULT 0,
            last_error TEXT,
            updated_at TEXT DEFAULT CURRENT_TIMESTAMP,
            PRIMARY KEY (target_league_id, season),
            FOREIGN KEY (target_league_id) REFERENCES leagues(id)
        );

        CREATE INDEX IF NOT EXISTS ix_history_league_level
        ON historical_matches(target_league_id, season, source_level);

        CREATE INDEX IF NOT EXISTS ix_history_current_home
        ON historical_matches(home_current_team_id);

        CREATE INDEX IF NOT EXISTS ix_history_current_away
        ON historical_matches(away_current_team_id);
        """
    )

def init_db(try_belgium=False):
    # No site público, a base já foi migrada e o token é apenas de leitura.
    # Apenas validamos a ligação; nenhuma tabela ou dado é alterado.
    if public_read_only_mode() and using_remote_database():
        with get_connection() as conn:
            conn.execute("SELECT 1").fetchone()
        return

    with get_connection() as conn:
        _ensure_schema(conn)
        _ensure_leagues(conn)
        _ensure_history_schema(conn)
        _ensure_player_schema(conn)
        _ensure_referees(conn)
        seed_bundled_fixtures(conn)
        conn.commit()
        try:
            from transfer_data import ensure_transfer_data
            ensure_transfer_data(conn, BASE_DIR, force=False)
        except Exception as exc:
            conn.execute(
                "INSERT INTO app_state(key,value) VALUES('transfers_init_error',?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value",
                (str(exc),),
            )
            conn.commit()
    if try_belgium:
        auto_fetch_belgium_once()


def calendar_counts():
    with get_connection() as conn:
        return conn.execute(
            """
            SELECT l.name, l.country, COUNT(m.id) AS games
            FROM leagues l
            LEFT JOIN matches m ON m.league_id=l.id AND m.season=?
            GROUP BY l.id ORDER BY l.country, l.name
            """, (SEASON,)
        ).fetchall()
