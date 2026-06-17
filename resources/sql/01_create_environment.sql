CREATE CATALOG IF NOT EXISTS dev_lh_nautical;
CREATE CATALOG IF NOT EXISTS prod_lh_nautical;

CREATE SCHEMA IF NOT EXISTS dev_lh_nautical.raw;
CREATE SCHEMA IF NOT EXISTS dev_lh_nautical.bronze;
CREATE SCHEMA IF NOT EXISTS dev_lh_nautical.silver;
CREATE SCHEMA IF NOT EXISTS dev_lh_nautical.gold;

CREATE SCHEMA IF NOT EXISTS prod_lh_nautical.raw;
CREATE SCHEMA IF NOT EXISTS prod_lh_nautical.bronze;
CREATE SCHEMA IF NOT EXISTS prod_lh_nautical.silver;
CREATE SCHEMA IF NOT EXISTS prod_lh_nautical.gold;