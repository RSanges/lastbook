"""Street addresses for address search: derived/geo/addresses.sqlite, from Overture Maps' open address data.

  derived/buildenv/bin/python tools/build_addresses.py [--bbox us | --bbox W,S,E,N] [--release 2026-10-21.0] [--country US | FR]

Overture's address theme gathers official address points (in California from the counties, via OpenAddresses), with
open licences (mostly CDLA-Permissive / public domain; see the 'sources' column). Reads the GeoParquet files straight
from Overture's public S3 bucket with DuckDB, keeping the whole US (default) or a box, and streams them into SQLite.
OpenStreetMap had too few addresses (none at all on many coastal streets).

With --country FR it keeps France instead (the Base Adresse Nationale, via OpenAddresses), with the French spelling
rule 'fr-1', into derived/geo/addresses/FR.sqlite; --bbox us then means the whole of France.
"""
import argparse, re, sqlite3, sys, time
from pathlib import Path

import duckdb

HERE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(HERE))
from engine.address_search import normalize_fr  # noqa: E402  (the index and the search share one spelling rule)
OUT = HERE / 'derived/geo/addresses.sqlite'
WORDS = {'boulevard': 'blvd', 'avenue': 'ave', 'av': 'ave', 'street': 'st', 'drive': 'dr', 'road': 'rd', 'place': 'pl', 'court': 'ct',
         'lane': 'ln', 'terrace': 'ter', 'circle': 'cir', 'highway': 'hwy', 'parkway': 'pkwy', 'square': 'sq', 'north': 'n', 'south': 's',
         'east': 'e', 'west': 'w', 'mount': 'mt', 'saint': 'st'}


def norm(street):
    """'Saint Mary Boulevard' -> 'st mary blvd' (game/serve.py uses the same rules on what people type)."""
    return ' '.join(WORDS.get(w, w) for w in re.sub(r'[^a-z0-9 ]+', ' ', street.lower()).split())


def fr_row(number, street, commune, dataset, postcode, lat, lon):
    """One French Overture row as an index row. The number keeps its written form ('12bis', '12 bis'): the search compares
    it without spaces or case. The state column holds the département, from the dataset name: 'fr/2A/statewide' -> '2A'."""
    match = re.match(r'fr/([^/]+)', dataset)
    return (number.strip(), street.strip(), normalize_fr(street), commune.strip(), match.group(1).upper() if match else '', postcode, lat, lon)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--bbox', default='us', help="'us' for the whole country, or W,S,E,N")
    ap.add_argument('--release', default='2026-10-21.0')
    ap.add_argument('--country', default='US', choices=('US', 'FR'))
    a = ap.parse_args()
    out = OUT if a.country == 'US' else OUT.parent / 'addresses' / 'FR.sqlite'     # a fr-1 index sits with the region indexes
    where = f"country = '{a.country}'"
    if a.bbox != 'us':
        w, s_, e, n = map(float, a.bbox.split(','))
        where += f' AND bbox.xmin BETWEEN {w} AND {e} AND bbox.ymin BETWEEN {s_} AND {n}'
    t0 = time.time()
    c = duckdb.connect()
    c.execute("INSTALL httpfs; LOAD httpfs; INSTALL spatial; LOAD spatial; SET s3_region='us-west-2';")
    levels = ("coalesce(postal_city, address_levels[2].value, ''), coalesce(address_levels[1].value, '')" if a.country == 'US' else
              "coalesce(address_levels[1].value, ''), coalesce(sources[1].dataset, '')")     # France: the commune, and 'fr/75' for its département
    cur = c.execute(f"""
        SELECT number, street, {levels},
               coalesce(left(postcode, 5), ''), round(ST_Y(geometry), 6), round(ST_X(geometry), 6)
        FROM read_parquet('s3://overturemaps-us-west-2/release/{a.release}/theme=addresses/type=address/*', hive_partitioning=1)
        WHERE {where} AND number IS NOT NULL AND street IS NOT NULL""")
    out.parent.mkdir(parents=True, exist_ok=True)
    tmp = out.with_suffix('.tmp')
    tmp.unlink(missing_ok=True)
    db = sqlite3.connect(tmp)
    db.executescript('PRAGMA journal_mode=OFF; PRAGMA synchronous=OFF;'
                     'CREATE TABLE addr(num TEXT, street TEXT, norm TEXT, city TEXT, state TEXT, zip TEXT, lat REAL, lon REAL);'
                     'CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT);')
    total = 0
    while rows := cur.fetchmany(500_000):  # streamed: the whole US is over 100 million rows
        db.executemany('INSERT INTO addr VALUES (?,?,?,?,?,?,?,?)', (fr_row(*row) for row in rows) if a.country == 'FR' else
                       ((num.strip(), st.strip(), norm(st), city.title(), state.upper()[:2], z, la, lo) for num, st, city, state, z, la, lo in rows))
        total += len(rows)
        print(f'{total:,} addresses, {time.time() - t0:.0f}s', flush=True)
    print('indexing', flush=True)
    db.execute('CREATE INDEX addr_norm ON addr(norm, num)')
    if a.country == 'FR':
        db.execute('CREATE INDEX addr_zip ON addr(zip)')     # '75001 Paris' is checked against the postcodes
        db.execute("INSERT INTO meta VALUES ('norm', 'fr-1')")     # searched with the French rules only
    db.executemany('INSERT INTO meta VALUES (?,?)', [('bbox', a.bbox), ('count', str(total)), ('built', time.strftime('%Y-%m-%dT%H:%M:%S')),
                                                    ('source', f'Overture Maps addresses {a.release} (open licences, mostly CDLA-Permissive-2.0)' if a.country == 'US' else
                                                     f'Base Adresse Nationale via Overture Maps addresses {a.release} (Licence Ouverte 2.0)')])
    db.commit(); db.close()
    tmp.replace(out)
    print(f'done: {total:,} addresses in {time.time() - t0:.0f}s', flush=True)


if __name__ == '__main__':
    main()
