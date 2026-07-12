\set ON_ERROR_STOP on

INSERT INTO transacciones (descripcion, monto)
VALUES
    ('Operación después del failover', 300.00);

SELECT
    id,
    descripcion,
    monto,
    fecha
FROM transacciones
ORDER BY id;