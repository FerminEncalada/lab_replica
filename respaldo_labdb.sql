--
-- PostgreSQL database dump
--

\restrict CCOarlzeFiadUnk2Sb93rwcmO6NbyM1TVeRhHUFj6R6cyu4gQFnANKcRL0c2a4P

-- Dumped from database version 14.23 (Debian 14.23-1.pgdg13+1)
-- Dumped by pg_dump version 14.23 (Debian 14.23-1.pgdg13+1)

SET statement_timeout = 0;
SET lock_timeout = 0;
SET idle_in_transaction_session_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SELECT pg_catalog.set_config('search_path', '', false);
SET check_function_bodies = false;
SET xmloption = content;
SET client_min_messages = warning;
SET row_security = off;

SET default_tablespace = '';

SET default_table_access_method = heap;

--
-- Name: transacciones; Type: TABLE; Schema: public; Owner: -
--

CREATE TABLE public.transacciones (
    id bigint NOT NULL,
    descripcion character varying(150) NOT NULL,
    monto numeric(12,2) NOT NULL,
    fecha timestamp with time zone DEFAULT CURRENT_TIMESTAMP NOT NULL,
    CONSTRAINT transacciones_monto_check CHECK ((monto >= (0)::numeric))
);


--
-- Name: transacciones_id_seq; Type: SEQUENCE; Schema: public; Owner: -
--

CREATE SEQUENCE public.transacciones_id_seq
    START WITH 1
    INCREMENT BY 1
    NO MINVALUE
    NO MAXVALUE
    CACHE 1;


--
-- Name: transacciones_id_seq; Type: SEQUENCE OWNED BY; Schema: public; Owner: -
--

ALTER SEQUENCE public.transacciones_id_seq OWNED BY public.transacciones.id;


--
-- Name: transacciones id; Type: DEFAULT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.transacciones ALTER COLUMN id SET DEFAULT nextval('public.transacciones_id_seq'::regclass);


--
-- Data for Name: transacciones; Type: TABLE DATA; Schema: public; Owner: -
--

COPY public.transacciones (id, descripcion, monto, fecha) FROM stdin;
1	Depósito inicial	500.00	2026-07-12 19:06:21.638115+00
2	Transferencia de prueba	125.50	2026-07-12 19:06:21.638115+00
3	Pago de servicio	42.75	2026-07-12 19:06:21.638115+00
34	Operación después del failover	300.00	2026-07-12 19:12:32.39506+00
\.


--
-- Name: transacciones_id_seq; Type: SEQUENCE SET; Schema: public; Owner: -
--

SELECT pg_catalog.setval('public.transacciones_id_seq', 34, true);


--
-- Name: transacciones transacciones_pkey; Type: CONSTRAINT; Schema: public; Owner: -
--

ALTER TABLE ONLY public.transacciones
    ADD CONSTRAINT transacciones_pkey PRIMARY KEY (id);


--
-- PostgreSQL database dump complete
--

\unrestrict CCOarlzeFiadUnk2Sb93rwcmO6NbyM1TVeRhHUFj6R6cyu4gQFnANKcRL0c2a4P

