PostgreSQL Replication Dashboard

Ubicar esta carpeta como:
  ~/lab_replica_postgresql/frontend

Estructura esperada:
  ~/lab_replica_postgresql/docker-compose.yml
  ~/lab_replica_postgresql/scripts/reconfigurar_replica2.sh
  ~/lab_replica_postgresql/frontend/app.py

Ejecución:
  cd ~/lab_replica_postgresql/frontend
  python3 -m venv .venv
  source .venv/bin/activate
  pip install -r requirements.txt
  cp .env.example .env
  python app.py

Abrir:
  http://127.0.0.1:5050
