export const meta = {
  name: 'ko-sqlguard-redteam',
  description: 'Adversarial red-team of ko-sqlguard: diverse attack lenses find dangerous SQL that escapes BLOCK, each escape independently verified',
  phases: [
    { title: 'Attack', detail: '8 attack lenses generate payloads and run them through the real guard' },
    { title: 'Verify', detail: 'independent skeptic confirms each claimed escape is genuinely dangerous' },
  ],
}

var HARNESS = '/data1/mk04/ko-sqlguard/redteam_harness.py'
var PY = '/data1/mk04/ko-sqlguard/.venv/bin/python'

var COMMON = [
  'You are red-teaming "ko-sqlguard", a parse-only PostgreSQL guardrail (sqlglot 30.10.0).',
  'A test harness is at ' + HARNESS + '. Feed it candidate SQL (one statement per line) like:',
  '',
  "  printf '%s\\n' 'SELECT 1' 'DROP TABLE x' > /tmp/payloads_rt.txt",
  '  ' + PY + ' ' + HARNESS + ' < /tmp/payloads_rt.txt',
  '',
  'It prints, per payload, the guard verdict (PASS / TRANSFORM / BLOCK / EXCEPTION) and violations,',
  'under a read-only policy with allowed_tables = orders (all cols) and customers (id,name,email).',
  '',
  "The guard's CONTRACT: every dangerous query must end in BLOCK. A dangerous escape is a payload",
  'whose verdict is PASS or TRANSFORM (or EXCEPTION) AND that, if executed against PostgreSQL, would:',
  '  - mutate data or schema (INSERT/UPDATE/DELETE/DDL/COPY/writable-CTE),',
  '  - read data outside the allowlist (other tables/schemas/catalogs: pg_catalog, information_schema, secrets),',
  '  - run server-side code or touch filesystem/network (functions, DO, COPY ... PROGRAM, large objects, dblink),',
  '  - cause denial of service (sleep, unbounded work), or',
  '  - execute a second stacked statement.',
  '',
  'IMPORTANT: a benign read of an ALLOWED table that merely got a LIMIT injected is NOT a finding -- that is',
  'correct TRANSFORM behavior. Only report payloads that are genuinely harmful yet escaped BLOCK.',
  '',
  'Test at least 25 distinct PostgreSQL-specific payloads for your lens. Return ONLY the dangerous escapes you',
  'actually observed (verdict != BLOCK in harness output), with the exact SQL string and exact verdict reported.',
  '',
].join('\n')

var LENSES = [
  { key: 'stacked', desc: "LENS: Statement stacking / piggyback / terminators. Smuggle a SECOND executable statement past the multi-statement check: ';' separators, dollar-quoted bodies, nested semicolons, comment-split semicolons (;/**/), leading/trailing ';', empty statements, BEGIN/COMMIT batches." },
  { key: 'comment_case', desc: 'LENS: Comment / whitespace / casing keyword evasion. Mixed case (DrOp), inline comments splitting keywords (DROP/**/TABLE), tabs/newlines/NBSP/vertical-tab whitespace, nested/unterminated comments, -- vs C-style comments to hide a DDL/DML keyword.' },
  { key: 'cte_subquery', desc: 'LENS: Allowlist bypass via subquery / CTE / set ops, and write-via-CTE. Read disallowed tables (secrets, pg_user) through derived tables, CTEs, UNION/INTERSECT/EXCEPT, deep nesting, LATERAL; and data-modifying CTEs (WITH x AS (DELETE/UPDATE/INSERT ... RETURNING)) at various depths.' },
  { key: 'pg_features', desc: 'LENS: PostgreSQL-specific dangerous features. COPY (TO/FROM PROGRAM, STDIN, options), DO blocks, CALL/EXECUTE/PREPARE, lo_import/lo_export, dblink, pg_read_file/pg_ls_dir, SET/RESET/SHOW, VACUUM/ANALYZE, GRANT/REVOKE, CREATE FUNCTION, REFRESH MATERIALIZED VIEW.' },
  { key: 'functions', desc: 'LENS: Dangerous function calls hidden in SELECT. pg_sleep variants, pg_read_file, dblink, lo_import, set_config, pg_terminate_backend, functions in WHERE/HAVING/ORDER BY/LIMIT/CTE/window, schema-qualified (pg_catalog.pg_sleep), quoted names ("pg_sleep"), via aliases.' },
  { key: 'identifiers', desc: 'LENS: Identifier/quoting/schema tricks. Quoted ("orders" vs orders vs "Orders"), schema-qualified (public.orders, pg_catalog.pg_tables, information_schema.tables), unicode/escaped identifiers (U&"..."), case-folding edges, catalog reads, search_path manipulation.' },
  { key: 'write_via_read', desc: 'LENS: Write/lock disguised as read. SELECT ... INTO (TEMP/UNLOGGED), SELECT ... FOR UPDATE/SHARE/NO KEY UPDATE/SKIP LOCKED, RETURNING on hidden DML, MERGE, INSERT ... SELECT, UPDATE ... FROM, CREATE TABLE AS SELECT.' },
  { key: 'parser_confusion', desc: 'LENS: Parser confusion / fail-open. Inputs that sqlglot might throw on (bypassing checks), parse into a benign node hiding a dangerous one, or silently drop. Null bytes, unicode homoglyphs, deep nesting, malformed-but-accepted SQL, trailing garbage after a valid SELECT. Any EXCEPTION verdict is fail-open and is itself a finding.' },
]

phase('Attack')

var ESCAPE_SCHEMA = {
  type: 'object',
  required: ['lens', 'payloads_tested', 'escapes'],
  properties: {
    lens: { type: 'string' },
    payloads_tested: { type: 'integer' },
    escapes: {
      type: 'array',
      items: {
        type: 'object',
        required: ['sql', 'verdict', 'why_dangerous'],
        properties: {
          sql: { type: 'string', description: 'exact payload string fed to the harness' },
          verdict: { type: 'string', description: 'exact verdict reported (PASS/TRANSFORM/EXCEPTION)' },
          why_dangerous: { type: 'string', description: 'what harm executing this would cause in PostgreSQL' },
        },
      },
    },
  },
}

var VERDICT_SCHEMA = {
  type: 'object',
  required: ['sql', 'is_real_escape', 'observed_verdict', 'reasoning'],
  properties: {
    sql: { type: 'string' },
    is_real_escape: { type: 'boolean', description: 'true ONLY if harness verdict != BLOCK AND payload is genuinely dangerous' },
    observed_verdict: { type: 'string', description: 'verdict you observed by re-running the exact payload' },
    reasoning: { type: 'string' },
    suggested_fix: { type: 'string', description: 'how ko-sqlguard should change to block it; empty if not real' },
  },
}

var results = await pipeline(
  LENSES,
  function (lens) {
    var prompt = COMMON + '\n' + lens.desc
    return agent(prompt, { label: 'attack:' + lens.key, phase: 'Attack', schema: ESCAPE_SCHEMA, agentType: 'general-purpose' })
  },
  function (attack) {
    var escapes = (attack && attack.escapes) || []
    if (!escapes.length) return []
    var lensName = (attack && attack.lens) || 'x'
    return parallel(escapes.map(function (e) {
      return function () {
        var vp = [
          'You are an independent skeptic verifying a claimed ko-sqlguard escape. Default to is_real_escape=false unless proven.',
          'Re-run this EXACT payload through the harness and read the verdict yourself. Write the payload to a file with a heredoc or printf so the exact bytes reach the harness, then run:',
          '  ' + PY + ' ' + HARNESS + ' < /tmp/verify_rt.txt',
          '',
          'The payload to verify (exact):',
          e.sql,
          '',
          'Claimed verdict: ' + e.verdict + '. Claimed danger: ' + e.why_dangerous,
          '',
          'It is a REAL escape only if BOTH hold: (1) the harness verdict is NOT BLOCK, and (2) executing the SQL in PostgreSQL would actually cause the claimed harm (mutation, out-of-allowlist read, RCE/file/network, DoS, or a genuine second statement). A benign read of an allowed table with an injected LIMIT is NOT an escape. If the harness BLOCKs it, is_real_escape=false.',
        ].join('\n')
        return agent(vp, { label: 'verify:' + lensName + ':' + String(e.sql).slice(0, 20), phase: 'Verify', schema: VERDICT_SCHEMA, agentType: 'general-purpose' })
          .then(function (v) { return Object.assign({}, v, { lens: lensName, claimed: e }) })
      }
    }))
  }
)

var flat = results.flat().filter(Boolean)
var confirmed = flat.filter(function (v) { return v && v.is_real_escape })

log('Verified ' + flat.length + ' claimed escapes; ' + confirmed.length + ' confirmed real.')

return {
  total_claimed: flat.length,
  confirmed_count: confirmed.length,
  confirmed: confirmed,
  all_verifications: flat,
}
