from __future__ import annotations

import os
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from contextlib import closing
from pathlib import Path
from typing import Any

import psycopg2
from flask import Flask, jsonify, render_template, request
from psycopg2 import sql
from psycopg2.extras import RealDictCursor
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = Path(os.getenv("PROJECT_ROOT", BASE_DIR.parent)).resolve()
load_dotenv(BASE_DIR / ".env")

app = Flask(__name__)
app.config["JSON_SORT_KEYS"] = False

DB_NAME = os.getenv("DB_NAME", "labdb")
DB_USER = os.getenv("DB_USER", "postgres")
DB_PASSWORD = os.getenv("DB_PASSWORD", "adminpass")
DB_HOST = os.getenv("DB_HOST", "127.0.0.1")

NODES: dict[str, dict[str, Any]] = {
    "master": {
        "label": "Maestro",
        "container": "pg-master",
        "service": "pg-master",
        "host": DB_HOST,
        "port": int(os.getenv("MASTER_PORT", "5432")),
    },
    "replica1": {
        "label": "Réplica 1",
        "container": "pg-replica1",
        "service": "pg-replica1",
        "host": DB_HOST,
        "port": int(os.getenv("REPLICA1_PORT", "5433")),
    },
    "replica2": {
        "label": "Réplica 2",
        "container": "pg-replica2",
        "service": "pg-replica2",
        "host": DB_HOST,
        "port": int(os.getenv("REPLICA2_PORT", "5434")),
    },
}


def db_connect(node_key: str, *, autocommit: bool = True):
    node = NODES[node_key]
    connection = psycopg2.connect(
        host=node["host"],
        port=node["port"],
        dbname=DB_NAME,
        user=DB_USER,
        password=DB_PASSWORD,
        connect_timeout=3,
        application_name="postgres_replication_dashboard",
    )
    connection.autocommit = autocommit
    return connection


def run_command(command: list[str], *, timeout: int = 90) -> dict[str, Any]:
    try:
        completed = subprocess.run(
            command,
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
            check=False,
        )
        return {
            "ok": completed.returncode == 0,
            "returncode": completed.returncode,
            "stdout": completed.stdout.strip(),
            "stderr": completed.stderr.strip(),
        }
    except FileNotFoundError:
        return {
            "ok": False,
            "returncode": 127,
            "stdout": "",
            "stderr": f"No se encontró el comando: {command[0]}",
        }
    except subprocess.TimeoutExpired:
        return {
            "ok": False,
            "returncode": 124,
            "stdout": "",
            "stderr": "El comando superó el tiempo máximo de espera.",
        }


def docker_status(container_name: str) -> dict[str, str | None]:
    result = run_command(
        [
            "docker",
            "inspect",
            "--format",
            "{{.State.Status}}|{{if .State.Health}}{{.State.Health.Status}}{{else}}none{{end}}",
            container_name,
        ],
        timeout=8,
    )
    if not result["ok"]:
        return {"status": "not_created", "health": None}

    status, _, health = result["stdout"].partition("|")
    return {
        "status": status or "unknown",
        "health": None if health in {"", "none"} else health,
    }


def table_exists(connection, table_name: str) -> bool:
    with connection.cursor() as cursor:
        cursor.execute("SELECT to_regclass(%s) IS NOT NULL;", (f"public.{table_name}",))
        return bool(cursor.fetchone()[0])


def ensure_schema() -> str | None:
    primary = find_primary()
    if primary is None:
        return None

    with closing(db_connect(primary)) as connection:
        with connection.cursor() as cursor:
            cursor.execute(
                """
                CREATE TABLE IF NOT EXISTS empleados (
                    id BIGSERIAL PRIMARY KEY,
                    nombre VARCHAR(100) NOT NULL,
                    cargo VARCHAR(100) NOT NULL,
                    creado_en TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
                );
                """
            )
    return primary


def get_node_status(node_key: str) -> dict[str, Any]:
    node = NODES[node_key]
    docker = docker_status(node["container"])
    response: dict[str, Any] = {
        "key": node_key,
        "label": node["label"],
        "container": node["container"],
        "port": node["port"],
        "docker_status": docker["status"],
        "health": docker["health"],
        "db_online": False,
        "role": "desconocido",
        "read_only": None,
        "wal_lsn": None,
        "received_lsn": None,
        "replayed_lsn": None,
        "lag_seconds": None,
        "row_count": None,
        "error": None,
    }

    if docker["status"] != "running":
        response["error"] = "El contenedor no está ejecutándose."
        return response

    try:
        with closing(db_connect(node_key)) as connection:
            with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    """
                    SELECT
                        pg_is_in_recovery() AS in_recovery,
                        current_setting('transaction_read_only') AS transaction_read_only,
                        current_database() AS database_name;
                    """
                )
                base = cursor.fetchone()
                in_recovery = bool(base["in_recovery"])
                response["db_online"] = True
                response["role"] = "replica" if in_recovery else "primary"
                response["read_only"] = base["transaction_read_only"] == "on"

                if in_recovery:
                    cursor.execute(
                        """
                        SELECT
                            pg_last_wal_receive_lsn()::text AS received_lsn,
                            pg_last_wal_replay_lsn()::text AS replayed_lsn,
                            CASE
                                WHEN pg_last_xact_replay_timestamp() IS NULL THEN NULL
                                ELSE ROUND(EXTRACT(EPOCH FROM (
                                    clock_timestamp() - pg_last_xact_replay_timestamp()
                                ))::numeric, 2)
                            END AS lag_seconds;
                        """
                    )
                    wal = cursor.fetchone()
                    response["received_lsn"] = wal["received_lsn"]
                    response["replayed_lsn"] = wal["replayed_lsn"]
                    response["lag_seconds"] = (
                        float(wal["lag_seconds"]) if wal["lag_seconds"] is not None else None
                    )
                else:
                    cursor.execute("SELECT pg_current_wal_lsn()::text AS wal_lsn;")
                    response["wal_lsn"] = cursor.fetchone()["wal_lsn"]

                if table_exists(connection, "empleados"):
                    cursor.execute("SELECT COUNT(*) AS total FROM empleados;")
                    response["row_count"] = int(cursor.fetchone()["total"])
                else:
                    response["row_count"] = 0

    except Exception as exc:  # noqa: BLE001
        response["error"] = str(exc).strip()

    return response


def get_all_statuses() -> dict[str, dict[str, Any]]:
    results: dict[str, dict[str, Any]] = {}
    with ThreadPoolExecutor(max_workers=len(NODES)) as executor:
        futures = {executor.submit(get_node_status, key): key for key in NODES}
        for future in as_completed(futures):
            key = futures[future]
            try:
                results[key] = future.result()
            except Exception as exc:  # noqa: BLE001
                results[key] = {
                    "key": key,
                    "label": NODES[key]["label"],
                    "db_online": False,
                    "role": "desconocido",
                    "error": str(exc),
                }
    return {key: results[key] for key in NODES}


def find_primary(statuses: dict[str, dict[str, Any]] | None = None) -> str | None:
    statuses = statuses or get_all_statuses()
    primary_nodes = [
        key
        for key, status in statuses.items()
        if status.get("db_online") and status.get("role") == "primary"
    ]
    if len(primary_nodes) == 1:
        return primary_nodes[0]
    return None


def get_replication_rows(primary_key: str | None) -> list[dict[str, Any]]:
    if primary_key is None:
        return []

    try:
        with closing(db_connect(primary_key)) as connection:
            with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    """
                    SELECT
                        application_name,
                        COALESCE(client_addr::text, 'local') AS client_addr,
                        state,
                        sync_state,
                        sent_lsn::text,
                        write_lsn::text,
                        flush_lsn::text,
                        replay_lsn::text,
                        COALESCE(
                            pg_wal_lsn_diff(sent_lsn, replay_lsn)::bigint,
                            0
                        ) AS pending_bytes
                    FROM pg_stat_replication
                    ORDER BY application_name;
                    """
                )
                return [dict(row) for row in cursor.fetchall()]
    except Exception:
        return []


def read_employees(node_key: str) -> dict[str, Any]:
    try:
        with closing(db_connect(node_key)) as connection:
            if not table_exists(connection, "empleados"):
                return {"ok": True, "rows": [], "message": "La tabla aún no existe."}
            with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    """
                    SELECT id, nombre, cargo,
                           to_char(creado_en, 'YYYY-MM-DD HH24:MI:SS') AS creado_en
                    FROM empleados
                    ORDER BY id DESC
                    LIMIT 100;
                    """
                )
                return {"ok": True, "rows": [dict(row) for row in cursor.fetchall()]}
    except Exception as exc:  # noqa: BLE001
        return {"ok": False, "rows": [], "message": str(exc).strip()}


@app.get("/")
def index():
    return render_template("index.html", nodes=NODES)


@app.get("/api/status")
def api_status():
    statuses = get_all_statuses()
    primary = find_primary(statuses)
    primary_count = sum(
        1
        for status in statuses.values()
        if status.get("db_online") and status.get("role") == "primary"
    )
    return jsonify(
        {
            "ok": True,
            "primary": primary,
            "split_brain_warning": primary_count > 1,
            "nodes": statuses,
            "replication": get_replication_rows(primary),
        }
    )


@app.get("/api/employees")
def api_employees():
    ensure_schema()
    data: dict[str, Any] = {}
    with ThreadPoolExecutor(max_workers=len(NODES)) as executor:
        futures = {executor.submit(read_employees, key): key for key in NODES}
        for future in as_completed(futures):
            key = futures[future]
            data[key] = future.result()
    return jsonify({"ok": True, "nodes": {key: data[key] for key in NODES}})


@app.post("/api/employees")
def api_create_employee():
    payload = request.get_json(silent=True) or {}
    nombre = str(payload.get("nombre", "")).strip()
    cargo = str(payload.get("cargo", "")).strip()

    if not nombre or not cargo:
        return jsonify({"ok": False, "message": "Nombre y cargo son obligatorios."}), 400
    if len(nombre) > 100 or len(cargo) > 100:
        return jsonify({"ok": False, "message": "Nombre y cargo admiten hasta 100 caracteres."}), 400

    primary = ensure_schema()
    if primary is None:
        return jsonify(
            {
                "ok": False,
                "message": "No se encontró un único nodo primario disponible.",
            }
        ), 503

    try:
        with closing(db_connect(primary)) as connection:
            with connection.cursor(cursor_factory=RealDictCursor) as cursor:
                cursor.execute(
                    """
                    INSERT INTO empleados (nombre, cargo)
                    VALUES (%s, %s)
                    RETURNING id, nombre, cargo,
                              to_char(creado_en, 'YYYY-MM-DD HH24:MI:SS') AS creado_en;
                    """,
                    (nombre, cargo),
                )
                row = dict(cursor.fetchone())
        return jsonify(
            {
                "ok": True,
                "message": f"Empleado registrado en {NODES[primary]['label']}.",
                "primary": primary,
                "employee": row,
            }
        )
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "message": str(exc).strip()}), 500


@app.post("/api/seed")
def api_seed():
    primary = ensure_schema()
    if primary is None:
        return jsonify({"ok": False, "message": "No hay un primario único disponible."}), 503

    try:
        with closing(db_connect(primary)) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT COUNT(*) FROM empleados;")
                total = int(cursor.fetchone()[0])
                if total > 0:
                    return jsonify(
                        {
                            "ok": True,
                            "message": "La tabla ya contiene datos; no se agregaron duplicados.",
                        }
                    )
                cursor.executemany(
                    "INSERT INTO empleados (nombre, cargo) VALUES (%s, %s);",
                    [
                        ("Ana", "Gerente"),
                        ("Carlos", "Analista"),
                        ("María", "Desarrolladora"),
                        ("José", "Administrador"),
                    ],
                )
        return jsonify({"ok": True, "message": "Datos de ejemplo insertados correctamente."})
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "message": str(exc).strip()}), 500


@app.post("/api/test/<node_key>/<test_type>")
def api_test_node(node_key: str, test_type: str):
    if node_key not in NODES:
        return jsonify({"ok": False, "message": "Nodo no válido."}), 404
    if test_type not in {"read", "write"}:
        return jsonify({"ok": False, "message": "Prueba no válida."}), 400

    try:
        if test_type == "read":
            with closing(db_connect(node_key)) as connection:
                with connection.cursor() as cursor:
                    cursor.execute("SELECT now(), pg_is_in_recovery();")
                    now_value, in_recovery = cursor.fetchone()
            return jsonify(
                {
                    "ok": True,
                    "message": (
                        f"Lectura correcta en {NODES[node_key]['label']}. "
                        f"Rol: {'réplica' if in_recovery else 'primario'}. "
                        f"Hora BD: {now_value}."
                    ),
                }
            )

        ensure_schema()
        connection = db_connect(node_key, autocommit=False)
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL statement_timeout = '5s';")
                cursor.execute(
                    """
                    INSERT INTO empleados (nombre, cargo)
                    VALUES ('PRUEBA_TEMPORAL', 'PRUEBA')
                    RETURNING id;
                    """
                )
                test_id = cursor.fetchone()[0]
            connection.rollback()
            return jsonify(
                {
                    "ok": True,
                    "write_allowed": True,
                    "message": (
                        f"{NODES[node_key]['label']} permite escritura. "
                        f"La fila temporal {test_id} se revirtió y no quedó guardada."
                    ),
                }
            )
        except Exception as exc:  # noqa: BLE001
            connection.rollback()
            return jsonify(
                {
                    "ok": True,
                    "write_allowed": False,
                    "message": (
                        f"{NODES[node_key]['label']} rechazó la escritura, como se espera "
                        f"en una réplica de solo lectura: {str(exc).strip()}"
                    ),
                }
            )
        finally:
            connection.close()

    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "message": str(exc).strip()}), 500


@app.post("/api/nodes/<node_key>/<action>")
def api_node_action(node_key: str, action: str):
    if node_key not in NODES:
        return jsonify({"ok": False, "message": "Nodo no válido."}), 404
    if action not in {"start", "stop", "restart"}:
        return jsonify({"ok": False, "message": "Acción no permitida."}), 400

    node = NODES[node_key]
    if action == "start":
        command = ["docker", "compose", "up", "-d", node["service"]]
    elif action == "stop":
        command = ["docker", "stop", node["container"]]
    else:
        command = ["docker", "restart", node["container"]]

    result = run_command(command)
    if not result["ok"]:
        return jsonify(
            {
                "ok": False,
                "message": result["stderr"] or "No se pudo ejecutar la acción.",
            }
        ), 500

    time.sleep(1)
    return jsonify(
        {
            "ok": True,
            "message": f"Acción '{action}' ejecutada sobre {node['label']}.",
            "output": result["stdout"],
        }
    )


@app.post("/api/nodes/<node_key>/promote")
def api_promote(node_key: str):
    if node_key not in NODES:
        return jsonify({"ok": False, "message": "Nodo no válido."}), 404

    statuses = get_all_statuses()
    target = statuses[node_key]
    if not target.get("db_online"):
        return jsonify({"ok": False, "message": "El nodo no está disponible."}), 409
    if target.get("role") != "replica":
        return jsonify({"ok": False, "message": "El nodo ya es primario o no es una réplica."}), 409

    other_primaries = [
        key
        for key, status in statuses.items()
        if key != node_key and status.get("db_online") and status.get("role") == "primary"
    ]
    if other_primaries:
        labels = ", ".join(NODES[key]["label"] for key in other_primaries)
        return jsonify(
            {
                "ok": False,
                "message": (
                    f"Detén primero el primario activo ({labels}) para evitar split-brain."
                ),
            }
        ), 409

    try:
        with closing(db_connect(node_key)) as connection:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_promote(true, 60);")
                promoted = bool(cursor.fetchone()[0])
        return jsonify(
            {
                "ok": promoted,
                "message": (
                    f"{NODES[node_key]['label']} fue promovida a nuevo primario."
                    if promoted
                    else "PostgreSQL no confirmó la promoción."
                ),
            }
        )
    except Exception as exc:  # noqa: BLE001
        return jsonify({"ok": False, "message": str(exc).strip()}), 500


@app.post("/api/reconnect-replica2")
def api_reconnect_replica2():
    script = PROJECT_ROOT / "scripts" / "reconfigurar_replica2.sh"
    if not script.exists():
        return jsonify(
            {
                "ok": False,
                "message": f"No se encontró el script requerido: {script}",
            }
        ), 404

    statuses = get_all_statuses()
    primary = find_primary(statuses)
    if primary != "replica1":
        return jsonify(
            {
                "ok": False,
                "message": (
                    "Esta acción se usa cuando pg-replica1 es el nuevo primario. "
                    "Actualmente no se detectó esa condición."
                ),
            }
        ), 409

    steps = [
        ["docker", "stop", NODES["replica2"]["container"]],
        [
            "docker",
            "compose",
            "run",
            "--rm",
            "--no-deps",
            "--entrypoint",
            "bash",
            NODES["replica2"]["service"],
            "/scripts/reconfigurar_replica2.sh",
        ],
        ["docker", "start", NODES["replica2"]["container"]],
    ]

    outputs: list[str] = []
    for step in steps:
        result = run_command(step, timeout=120)
        outputs.append(result["stdout"] or result["stderr"])
        if not result["ok"]:
            return jsonify(
                {
                    "ok": False,
                    "message": result["stderr"] or "Falló la reconfiguración.",
                    "output": outputs,
                }
            ), 500

    return jsonify(
        {
            "ok": True,
            "message": "Réplica 2 reconfigurada para seguir a Réplica 1.",
            "output": outputs,
        }
    )


@app.errorhandler(404)
def not_found(_error):
    return jsonify({"ok": False, "message": "Recurso no encontrado."}), 404


if __name__ == "__main__":
    host = os.getenv("APP_HOST", "127.0.0.1")
    port = int(os.getenv("APP_PORT", "5050"))
    debug = os.getenv("FLASK_DEBUG", "false").lower() == "true"
    app.run(host=host, port=port, debug=debug, use_reloader=False)
