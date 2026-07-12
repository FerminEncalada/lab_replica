#!/usr/bin/env bash

set -Eeuo pipefail

DATA_DIR="/var/lib/postgresql/data"
AUTO_CONF="$DATA_DIR/postgresql.auto.conf"

if [[ ! -f "$AUTO_CONF" ]]; then
    echo "ERROR: no existe $AUTO_CONF."
    echo "Primero debe clonarse la réplica 2."
    exit 1
fi

echo "Reconfigurando pg-replica2..."
echo "Nuevo servidor principal: pg-replica1"

# Elimina la conexión hacia el maestro original.
sed -i \
    '/^[[:space:]]*primary_conninfo[[:space:]]*=/d' \
    "$AUTO_CONF"

# Elimina una posible configuración anterior del timeline.
sed -i \
    '/^[[:space:]]*recovery_target_timeline[[:space:]]*=/d' \
    "$AUTO_CONF"

# Configura a pg-replica1 como nuevo maestro.
printf "%s\n" \
    "primary_conninfo = 'host=pg-replica1 port=5432 user=replicator passfile=/var/lib/postgresql/data/.pgpass application_name=pg-replica2'" \
    >> "$AUTO_CONF"

printf "%s\n" \
    "recovery_target_timeline = 'latest'" \
    >> "$AUTO_CONF"

# Garantiza que el nodo vuelva a iniciar como standby.
touch "$DATA_DIR/standby.signal"

chown postgres:postgres "$AUTO_CONF"
chown postgres:postgres "$DATA_DIR/standby.signal"

echo "pg-replica2 ahora apunta a pg-replica1."