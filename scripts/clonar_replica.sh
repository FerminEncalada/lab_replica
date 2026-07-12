#!/usr/bin/env bash

set -Eeuo pipefail

REPLICA_NAME="${1:-}"

if [[ "$REPLICA_NAME" != "pg-replica1" && "$REPLICA_NAME" != "pg-replica2" ]]; then
    echo "ERROR: debe indicar pg-replica1 o pg-replica2."
    echo "Ejemplo: /scripts/clonar_replica.sh pg-replica1"
    exit 1
fi

DATA_DIR="/var/lib/postgresql/data"

echo "============================================"
echo "Clonando datos para: $REPLICA_NAME"
echo "Origen: pg-master"
echo "Destino: $DATA_DIR"
echo "============================================"

# Elimina datos de intentos anteriores.
find "$DATA_DIR" \
    -mindepth 1 \
    -maxdepth 1 \
    -exec rm -rf -- {} +

# Prepara permisos para el usuario postgres del contenedor.
chown -R postgres:postgres "$DATA_DIR"

# Contraseña utilizada únicamente por pg_basebackup.
export PGPASSWORD="replpass"

# Obtiene una copia física completa del maestro.
gosu postgres pg_basebackup \
    -h pg-master \
    -p 5432 \
    -D "$DATA_DIR" \
    -U replicator \
    -X stream \
    -P \
    -v \
    -R \
    -w

unset PGPASSWORD

# Archivo de contraseñas utilizado por el proceso WAL Receiver.
cat > "$DATA_DIR/.pgpass" <<'EOF'
pg-master:5432:replication:replicator:replpass
pg-replica1:5432:replication:replicator:replpass
EOF

chmod 600 "$DATA_DIR/.pgpass"
chown postgres:postgres "$DATA_DIR/.pgpass"

# pg_basebackup -R crea postgresql.auto.conf.
# Sustituimos primary_conninfo para identificar cada réplica.
sed -i \
    '/^[[:space:]]*primary_conninfo[[:space:]]*=/d' \
    "$DATA_DIR/postgresql.auto.conf"

printf "%s\n" \
    "primary_conninfo = 'host=pg-master port=5432 user=replicator passfile=/var/lib/postgresql/data/.pgpass application_name=$REPLICA_NAME'" \
    >> "$DATA_DIR/postgresql.auto.conf"

chown postgres:postgres "$DATA_DIR/postgresql.auto.conf"

if [[ ! -f "$DATA_DIR/standby.signal" ]]; then
    echo "ERROR: no se generó standby.signal."
    exit 1
fi

echo
echo "La clonación de $REPLICA_NAME terminó correctamente."
echo "Se encontró standby.signal."
echo "La réplica está preparada para conectarse a pg-master."