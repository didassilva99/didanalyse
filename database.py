from __future__ import annotations

from pathlib import Path
import sqlite3

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "apostas.db"
SEASON = "2026/27"


def get_connection() -> sqlite3.Connection:
    """Abre a base pública incluída no projeto em modo apenas de leitura."""
    if not DB_PATH.is_file():
        raise RuntimeError(
            "O ficheiro apostas.db não está na raiz do projeto. "
            "Carrega todos os ficheiros do ZIP diretamente no GitHub."
        )

    connection = sqlite3.connect(
        DB_PATH.resolve().as_uri() + "?mode=ro",
        uri=True,
        check_same_thread=False,
    )
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA foreign_keys = ON")
    return connection


def init_db() -> None:
    """Confirma que a base correta está disponível, sem fazer alterações."""
    with get_connection() as connection:
        required = {
            "leagues",
            "teams",
            "matches",
            "historical_matches",
            "transfers",
            "transfer_team_scores",
        }
        existing = {
            str(row[0])
            for row in connection.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        }

        missing = sorted(required - existing)
        if missing:
            raise RuntimeError(
                "A base de dados está incompleta. "
                f"Tabelas em falta: {', '.join(missing)}"
            )

        games = connection.execute(
            "SELECT COUNT(*) FROM matches WHERE season=?",
            (SEASON,),
        ).fetchone()[0]

        competitions = connection.execute(
            "SELECT COUNT(DISTINCT league_id) FROM matches WHERE season=?",
            (SEASON,),
        ).fetchone()[0]

        if int(games or 0) != 2670 or int(competitions or 0) != 8:
            raise RuntimeError(
                "A base carregada não é a versão correta: "
                f"{games} jogos e {competitions} competições."
            )
