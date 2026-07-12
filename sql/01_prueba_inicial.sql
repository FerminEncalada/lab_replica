\set ON_ERROR_STOP on

CREATE TABLE IF NOT EXISTS transacciones (
    id BIGSERIAL PRIMARY KEY,
    descripcion VARCHAR(150) NOT NULL,
    monto NUMERIC(12,2) NOT NULL CHECK (monto >= 0),
    fecha TIMESTAMPTZ NOT NULL DEFAULT CURRENT_TIMESTAMP
);

INSERT INTO transacciones (descripcion, monto)
VALUES
    ('Depósito inicial', 500.00),
    ('Transferencia de prueba', 125.50),
    ('Pago de servicio', 42.75);

SELECT
    id,
    descripcion,
    monto,
    fecha
FROM transacciones
ORDER BY id;