-- tests/test_value_quality.sql
-- Unit test for the value_quality macro logic (no source DB needed).
-- Run: duckdb < tests/test_value_quality.sql   (expects all rows PASS)

-- money() is a prerequisite of value_quality; copy it so the test is standalone.
CREATE OR REPLACE MACRO money(s) AS
  try_cast(nullif(regexp_replace(coalesce(s,''), '[^0-9.]', '', 'g'), '') AS DECIMAL(18,2));

CREATE OR REPLACE MACRO cv_intpart(s) AS
  split_part(regexp_replace(coalesce(s,''), '[^0-9.]', '', 'g'), '.', 1);

CREATE OR REPLACE MACRO value_quality(s) AS
  CASE
    WHEN money(s) IS NULL                           THEN 'missing'
    WHEN money(s) < 100                             THEN 'too_small'
    WHEN money(s) > 1e11                            THEN 'junk_magnitude'
    WHEN regexp_matches(coalesce(s,''), '1234567')  THEN 'junk_sequence'
    WHEN money(s) > 1e10                            THEN 'review'
    WHEN regexp_matches(cv_intpart(s), '^1?123456$')
      OR ( length(cv_intpart(s)) >= 6
           AND cv_intpart(s) = repeat(left(cv_intpart(s),1), length(cv_intpart(s))) )
                                                    THEN 'suspect_placeholder'
    ELSE 'clean'
  END;

WITH fixture(raw, expected) AS (
  VALUES
    ('170000012345678', 'junk_magnitude'),       -- 2021_UAD_167291_1
    ('150000157000163', 'junk_magnitude'),       -- 2019_IC_24458_1
    ('12345678',        'junk_sequence'),         -- exact placeholder, 1.23e7
    ('19879212345678',  'junk_magnitude'),        -- 1.98e13, magnitude wins over sequence
    ('15000000000',     'review'),                -- 1.5e10 = 1500 cr
    ('123456',          'suspect_placeholder'),
    ('1123456',         'suspect_placeholder'),
    ('1111111',         'suspect_placeholder'),   -- repeated digit
    ('9123456.78',      'clean'),                 -- contains 123456 but plausible, not exact
    ('500000',          'clean'),
    ('50',              'too_small'),
    ('',                'missing'),
    (NULL,              'missing')
)
SELECT
  raw, expected, value_quality(raw) AS got,
  CASE WHEN value_quality(raw) IS NOT DISTINCT FROM expected THEN 'PASS' ELSE 'FAIL' END AS result
FROM fixture
ORDER BY result, raw;
