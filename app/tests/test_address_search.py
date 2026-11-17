"""Offline address lookup must preserve house numbers and geographic qualifiers."""
import importlib.util
import sqlite3
import sys
import tempfile
import types
import unittest
from pathlib import Path
from unittest.mock import MagicMock, patch

from engine.address_search import (_parts_fr, find_addresses, is_address_query, is_french_postcode_query, is_german_address_query,
                                   is_german_postcode_query, normalize, normalize_de, normalize_fr)


class AddressSearchTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.geo = Path(self.temp.name)
        (self.geo / 'addresses').mkdir()
        self.write_state('MI', [
            ('18001', 'W Nine Mile Road', 'Novi', 'MI', '48375', 42.45, -83.47),
            ('18002', 'W Nine Mile Road', 'Novi', 'MI', '48375', 42.46, -83.47),
            ('18001', 'Nine Mile Rd', 'Farmington', 'MI', '48335', 42.47, -83.40),
        ])
        self.write_state('CA', [
            ('18001', 'Nine Mile Road', 'Example', 'CA', '90001', 34.0, -118.0),
            ('23001', 'Maple Avenue', 'Kansas City', 'MO', '64105', 39.0997, -94.5786),
            ('21', 'W 9 ST', 'Example', 'CA', '90001', 34.01, -118.01),
        ])

    def tearDown(self):
        self.temp.cleanup()

    def write_state(self, state, rows):
        db = sqlite3.connect(self.geo / 'addresses' / f'{state}.sqlite')
        try:
            db.execute('CREATE TABLE addr(num TEXT,street TEXT,norm TEXT,city TEXT,state TEXT,zip TEXT,lat REAL,lon REAL)')
            db.execute('CREATE INDEX addr_num_norm ON addr(num,norm)')
            db.executemany('INSERT INTO addr VALUES(?,?,?,?,?,?,?,?)',
                           [(num, street, normalize(street), city, st, z, lat, lon)
                            for num, street, city, st, z, lat, lon in rows])
            db.commit()
        finally:
            db.close()      # the `with` form commits but does not close, and Windows will not remove an open file

    def test_numeric_words_directions_and_qualifiers(self):
        for query in ('18001 9 mile rd Novi MI', '18001 Nine Mile Road Novi Michigan',
                      '18001 nine mile Novi 48375', '18001 W Nine Mile Road, Novi, MI 48375'):
            with self.subTest(query=query):
                result = find_addresses(query, self.geo)
                self.assertEqual(len(result), 1)
                self.assertEqual(result[0]['name'], '18001 W Nine Mile Road')
                self.assertEqual(result[0]['lat'], 42.45)
                self.assertEqual(result[0]['kind'], 'Street address')

    def test_unknown_number_does_not_return_nearby_house(self):
        self.assertEqual(find_addresses('18003 nine mile Novi MI', self.geo), [])

    def test_city_and_zip_do_not_silently_fall_back(self):
        self.assertEqual(find_addresses('18001 nine mile Wrongtown MI', self.geo), [])
        self.assertEqual(find_addresses('18001 nine mile MI 99999', self.geo), [])

    def test_state_uses_only_that_index(self):
        result = find_addresses('18001 nine mile CA', self.geo)
        self.assertEqual(len(result), 1)
        self.assertEqual(result[0]['detail'], 'Example, CA, 90001')

    def test_ordinal_street(self):
        result = find_addresses('21 ninth st Example CA', self.geo)
        self.assertEqual(result[0]['name'], '21 W 9 ST')

    def test_plain_zip_remains_place_query(self):
        self.assertFalse(is_address_query('48375'))
        self.assertFalse(is_address_query('Novi MI'))
        self.assertTrue(is_address_query('18001 nine mile'))

    def test_missing_indexes_and_legacy_database(self):
        empty = self.geo / 'empty'
        self.assertEqual(find_addresses('23001 Maple Ave', empty), [])
        empty.mkdir()
        db = sqlite3.connect(empty / 'addresses.sqlite')
        try:
            db.execute('CREATE TABLE addr(num TEXT,street TEXT,norm TEXT,city TEXT,state TEXT,zip TEXT,lat REAL,lon REAL)')
            db.execute("INSERT INTO addr VALUES('23001','Maple Avenue','maple ave','Kansas City','MO','64105',39.0997,-94.5786)")
            db.commit()
        finally:
            db.close()      # as in write_state: the `with` form does not close, and Windows will not remove an open file
        self.assertEqual(find_addresses('23001 Maple Ave Kansas City MO', empty)[0]['lat'], 39.0997)

    def test_app_route_preserves_address_number(self):
        import server
        with patch.object(server, 'HERE', self.geo.parent), patch.object(server.address_search, 'find_addresses', return_value=[]) as lookup:
            self.assertEqual(server.places('18003 nine mile'), [])
            lookup.assert_called_once_with('18003 nine mile', self.geo.parent / 'derived' / 'geo', limit=8, near=None)


BERLIN_SOURCE = 'Geoportal Berlin, Adressen Berlin (dl-de/zero-2.0)'
BERLIN = [
    ('77', 'Unter den Linden', '10117', 'Mitte', 52.5170, 13.3888),
    ('12', 'Müllerstraße', '13353', 'Wedding', 52.5480, 13.3600),
    ('12A', 'Müllerstraße', '13353', 'Wedding', 52.5481, 13.3601),
    ('135', 'Straße des 17. Juni', '10623', 'Tiergarten', 52.5130, 13.3270),
    ('25', 'Oranienstraße', '10999', 'Kreuzberg', 52.5010, 13.4190),
    ('5', 'Hauptstraße', '10827', 'Schöneberg', 52.4880, 13.3530),
    ('5', 'Hauptstraße', '12589', 'Rahnsdorf', 52.4400, 13.6900),
    ('77', 'Lindenstraße', '10969', 'Kreuzberg', 52.5030, 13.3980),
]


class GermanAddressSearchTests(unittest.TestCase):
    """Berlin addresses are written street first, number after, and may carry a postcode and an Ortsteil."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.geo = Path(self.temp.name)
        (self.geo / 'addresses').mkdir()
        self.write_berlin(self.geo / 'addresses' / 'DE-BE.sqlite')

    def tearDown(self):
        self.temp.cleanup()

    @staticmethod
    def write_berlin(path, rows=BERLIN, source=BERLIN_SOURCE):
        """The DE-BE index contract: a district column and meta norm 'de-1' with its own source line."""
        db = sqlite3.connect(path)
        try:
            db.execute('CREATE TABLE addr(num TEXT,street TEXT,norm TEXT,city TEXT,state TEXT,zip TEXT,lat REAL,lon REAL,district TEXT)')
            db.execute('CREATE INDEX addr_norm ON addr(norm,num)')
            db.execute('CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT)')
            db.executemany('INSERT INTO addr VALUES(?,?,?,?,?,?,?,?,?)',
                           [(num, street, normalize_de(street), 'Berlin', 'DE-BE', z, lat, lon, district)
                            for num, street, z, district, lat, lon in rows])
            db.executemany('INSERT INTO meta VALUES(?,?)', [('norm', 'de-1'), ('source', source)])
            db.commit()
        finally:
            db.close()      # as in AddressSearchTests.write_state: Windows will not remove an open file

    def write_us_state(self, state, rows, source=None):
        AddressSearchTests.write_state(self, state, rows)
        if source:      # the published US state indexes carry a source line but no norm key
            db = sqlite3.connect(self.geo / 'addresses' / f'{state}.sqlite')
            try:
                db.execute('CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT)')
                db.execute("INSERT INTO meta VALUES('source',?)", (source,))
                db.commit()
            finally:
                db.close()

    def one(self, query):
        result = find_addresses(query, self.geo)
        self.assertEqual(len(result), 1, query)
        return result[0]

    def test_street_then_number_with_optional_postcode_and_city(self):
        """The plain German order, with or without the postcode line, finds the house and names it the German way."""
        for query in ('Unter den Linden 77', 'unter den linden 77, 10117 Berlin', 'Unter den Linden 77 10117'):
            with self.subTest(query=query):
                hit = self.one(query)
                self.assertEqual(hit['name'], 'Unter den Linden 77')
                self.assertEqual(hit['detail'], '10117 Berlin-Mitte')
                self.assertEqual(hit['lat'], 52.5170)
                self.assertEqual(hit['kind'], 'Street address')
                self.assertEqual(hit['source'], BERLIN_SOURCE)     # credit the index's own source, not Overture

    def test_umlaut_sharp_s_and_str_abbreviation_spellings_meet(self):
        """People type ß, ss, ü, ue and 'str.' interchangeably; all must reach house 12A and never plain 12."""
        for query in ('Müllerstr. 12a', 'Müllerstraße 12 a', 'Muellerstrasse 12A', 'MÜLLERSTRASSE 12A, 13353 Berlin'):
            with self.subTest(query=query):
                hit = self.one(query)
                self.assertEqual(hit['name'], 'Müllerstraße 12A')
                self.assertEqual(hit['lat'], 52.5481)

    def test_normalize_de_scheme(self):
        """The builder imports this function, so its output is the stored norm column and must follow scheme de-1."""
        self.assertEqual(normalize_de('Müllerstraße'), 'muellerstr')
        self.assertEqual(normalize_de('Straße des 17. Juni'), 'str des 17 juni')
        self.assertEqual(normalize_de('Karl-Marx-Str.'), 'karl marx str')
        self.assertEqual(normalize_de('Hauptstrasse'), normalize_de('Hauptstraße'))
        self.assertEqual(normalize('18001 W Nine Mile Road'), '18001 w nine mile rd')      # the US scheme is untouched

    def test_number_inside_street_name_is_not_the_house_number(self):
        """'Straße des 17. Juni 135': the house is the last number, the 17 belongs to the street."""
        hit = self.one('Straße des 17. Juni 135')
        self.assertEqual(hit['name'], 'Straße des 17. Juni 135')
        self.assertEqual(find_addresses('Straße des 17. Juni', self.geo), [])

    def test_district_or_city_qualifier_filters_like_the_us_city(self):
        """A trailing Ortsteil or city narrows the street to that place, prefix-matched, and a wrong one finds nothing."""
        self.assertEqual(self.one('Oranienstraße 25 Kreuzberg')['detail'], '10999 Berlin-Kreuzberg')
        self.assertEqual(self.one('Oranienstr 25 kreuz')['lat'], 52.5010)
        self.assertEqual(self.one('Hauptstraße 5 Schöneberg')['detail'], '10827 Berlin-Schöneberg')
        self.assertEqual(self.one('Hauptstraße 5 Berlin-Rahnsdorf')['detail'], '12589 Berlin-Rahnsdorf')
        self.assertEqual(len(find_addresses('Hauptstraße 5 Berlin', self.geo)), 2)
        self.assertEqual(find_addresses('Oranienstraße 25 Spandau', self.geo), [])
        self.assertEqual(find_addresses('Oranienstraße 25, 10117 Berlin', self.geo), [])

    def test_unknown_number_does_not_return_nearby_house(self):
        """Exact house numbers only: 78 must not fall back to 77, and 12B not to 12 or 12A."""
        self.assertEqual(find_addresses('Unter den Linden 78', self.geo), [])
        self.assertEqual(find_addresses('Müllerstraße 12b', self.geo), [])

    def test_postcode_city_and_district_alone_stay_place_queries(self):
        """'10117 Berlin', 'Berlin' and 'Kreuzberg' name places; treating them as addresses would hide the place."""
        for query in ('10117 Berlin', 'Berlin', 'Kreuzberg', '10117'):
            with self.subTest(query=query):
                self.assertFalse(is_german_address_query(query))
                self.assertEqual(find_addresses(query, self.geo), [])
        # '10117 Berlin' is number-first like '18001 nine mile', so places() asks whether a German index knows it
        self.assertTrue(is_address_query('10117 Berlin'))
        self.assertTrue(is_german_postcode_query('10117 Berlin', self.geo))
        self.assertTrue(is_german_postcode_query('10999, Kreuzberg', self.geo))
        self.assertFalse(is_german_postcode_query('18003 nine mile', self.geo))
        self.assertFalse(is_german_postcode_query('10117 Spandau', self.geo))
        self.assertTrue(is_german_address_query('Unter den Linden 77'))

    def test_us_results_unchanged_with_berlin_installed(self):
        """Adding DE-BE must not change a single US answer, including the 'Overture Maps' credit."""
        (self.geo / 'addresses' / 'DE-BE.sqlite').unlink()
        self.write_us_state('MI', [('18001', 'W Nine Mile Road', 'Novi', 'MI', '48375', 42.45, -83.47),
                                   ('77', 'Linden Street', 'Novi', 'MI', '48375', 42.40, -83.40)],
                            source='Overture Maps addresses 2026-10-21.0 (open licences, mostly CDLA-Permissive-2.0)')
        self.write_us_state('CA', [('21', 'W 9 ST', 'Example', 'CA', '90001', 34.01, -118.01)])
        queries = ('18001 nine mile', '18001 W Nine Mile Road, Novi, MI 48375', '77 Linden', '77 Linden St Novi',
                   '21 ninth st Example CA', '18003 nine mile')
        before = [find_addresses(query, self.geo) for query in queries]
        self.assertEqual(before[0][0]['source'], 'Overture Maps')
        self.write_berlin(self.geo / 'addresses' / 'DE-BE.sqlite')
        self.assertEqual([find_addresses(query, self.geo) for query in queries], before)

    def test_delaware_stays_delaware(self):
        """Bare 'DE' is the US state code: a Delaware query must use DE.sqlite only, never the DE-BE index."""
        self.write_us_state('DE', [('77', 'Linden Street', 'Wilmington', 'DE', '19801', 39.74, -75.55)])
        for query in ('77 Linden DE', '77 Linden Delaware'):
            with self.subTest(query=query):
                hit = self.one(query)
                self.assertEqual(hit['detail'], 'Wilmington, DE, 19801')
                self.assertEqual(hit['source'], 'Overture Maps')

    def test_app_route_falls_back_to_places_for_route_66(self):
        """'Route 66' has the German shape and '10117 Berlin' the US one, but both are places: with no such house the
        normal place search answers. An unknown US house stays an empty address answer, as before."""
        import server
        root = self.geo / 'root'
        geo = root / 'derived' / 'geo'
        (geo / 'addresses').mkdir(parents=True)
        self.write_berlin(geo / 'addresses' / 'DE-BE.sqlite')
        places = sqlite3.connect(geo / 'places.sqlite')
        try:
            places.executescript(
                "CREATE TABLE place(id INTEGER PRIMARY KEY, name TEXT, kind TEXT, detail TEXT, lat REAL, lon REAL, rank INTEGER, source TEXT);"
                "CREATE VIRTUAL TABLE place_fts USING fts5(name, detail, content='place', content_rowid='id', tokenize='unicode61');"
                "INSERT INTO place(name,kind,detail,lat,lon,rank,source) VALUES ('Route 66','Locale','Arizona',35.2,-113.9,3,'gnis');"
                "INSERT INTO place(name,kind,detail,lat,lon,rank,source) VALUES ('Berlin','City','Germany',52.52,13.40,1,'test');"
                "INSERT INTO place(name,kind,detail,lat,lon,rank,source) VALUES ('Nine Mile','Locale','Michigan',42.4,-83.4,3,'gnis');"
                "INSERT INTO place_fts(place_fts) VALUES('rebuild');")
            places.commit()
        finally:
            places.close()
        with patch.object(server, 'HERE', root), patch.object(server, 'PLACEDB', geo / 'places.sqlite'), \
                patch.object(server, 'WATERDB', root / 'no-water.sqlite'), patch.object(server, 'home_area', return_value=None):
            self.assertEqual([hit['name'] for hit in server.places('Route 66')], ['Route 66'])
            self.assertEqual([hit['name'] for hit in server.places('10117 Berlin')], ['Berlin'])
            self.assertEqual([hit['name'] for hit in server.places('Kreuzberg')], [])
            self.assertEqual(server.places('18003 nine mile'), [])
            hit, = server.places('Unter den Linden 77')
            self.assertEqual((hit['name'], hit['kind']), ('Unter den Linden 77', 'Street address'))


def load_builder():
    """tools/build_addresses.py without DuckDB, which only its network part needs."""
    spec = importlib.util.spec_from_file_location('build_addresses', Path(__file__).resolve().parents[2] / 'tools' / 'build_addresses.py')
    module = importlib.util.module_from_spec(spec)
    with patch.dict(sys.modules, {'duckdb': types.ModuleType('duckdb')}):
        spec.loader.exec_module(module)
    return module


FR_SOURCE = 'Base Adresse Nationale via Overture Maps addresses 2026-10-21.0 (Licence Ouverte 2.0)'
# (number, street, postcode, commune, dataset, lat, lon). The first nine rows are real Overture 2026-10-21.0 rows, as
# Overture writes them, each the address of a public building checked on an official page: a museum, a ministry, the
# presidential palace, a theatre, a regional government and four town halls. The rest are invented: made-up communes
# 'Exemple' and 'Autreville', postcodes 00000 and 00001, and coordinates at sea, for the cases no public building has.
FRANCE = [
    ('107', 'Rue de Rivoli', '75001', 'Paris 1er Arrondissement', 'fr/75/statewide', 48.863214, 2.333316),
    ('246', 'Boulevard Saint-Germain', '75007', 'Paris 7e Arrondissement', 'fr/75/statewide', 48.857224, 2.324617),
    ('55', 'Rue du Faubourg Saint-Honoré', '75008', 'Paris 8e Arrondissement', 'fr/75/statewide', 48.87063, 2.316931),
    ('2B', 'Avenue Franklin D. Roosevelt', '75008', 'Paris 8e Arrondissement', 'fr/75/statewide', 48.867784, 2.310549),
    ('22', 'Cours Grandval', '20000', 'Ajaccio', 'fr/2A/statewide', 41.91793, 8.73236),
    ('27', 'Avenue Robert Schuman', '59370', 'Mons-en-Barœul', 'fr/59/statewide', 50.642482, 3.110346),
    ('1', 'Place de l’Hotel de Ville', '92600', 'Asnières-sur-Seine', 'fr/92/statewide', 48.910692, 2.288989),
    ('2', "Place De L'Hôtel De Ville", '92400', 'Courbevoie', 'fr/92/statewide', 48.895241, 2.256307),
    ('2', 'Place de l’Hotel de Ville', '78140', 'Vélizy-Villacoublay', 'fr/78/statewide', 48.78274, 2.190937),
    ('3', "Rue de l'Église", '00000', 'Exemple', 'fr/00', 0.1, 0.1),
    ('3bis', "Rue de l'Église", '00000', 'Exemple', 'fr/00', 0.2, 0.2),
    ('3B', "Rue de l'Église", '00000', 'Exemple', 'fr/00', 0.7, 0.7),
    ('3', 'Rue de l’Église', '00001', 'Autreville', 'fr/00', 0.3, 0.3),
    ('1', 'Avenue de la Gare', '00000', 'Exemple', 'fr/00', 0.4, 0.4),
    ('1b', 'Avenue de la Gare', '00000', 'Exemple', 'fr/00', 0.5, 0.5),
    ('5', 'Impasse de la Mairie', '00000', 'Exemple', 'fr/00', 0.6, 0.6),
]


class FrenchAddressSearchTests(unittest.TestCase):
    """French addresses are written number first, then the street, then the postcode before the commune."""

    builder = load_builder()

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.geo = Path(self.temp.name)
        (self.geo / 'addresses').mkdir()
        self.write_france(self.geo / 'addresses' / 'FR.sqlite')

    def tearDown(self):
        self.temp.cleanup()

    def write_france(self, path, rows=FRANCE):
        """The fr-1 index contract, filled through the builder's own row mapping."""
        db = sqlite3.connect(path)
        try:
            db.execute('CREATE TABLE addr(num TEXT,street TEXT,norm TEXT,city TEXT,state TEXT,zip TEXT,lat REAL,lon REAL)')
            db.execute('CREATE INDEX addr_norm ON addr(norm,num)')
            db.execute('CREATE TABLE meta(key TEXT PRIMARY KEY,value TEXT)')
            db.executemany('INSERT INTO addr VALUES(?,?,?,?,?,?,?,?)',
                           [self.builder.fr_row(num, street, commune, dataset, z, lat, lon)
                            for num, street, z, commune, dataset, lat, lon in rows])
            db.executemany('INSERT INTO meta VALUES(?,?)', [('norm', 'fr-1'), ('source', FR_SOURCE)])
            db.commit()
        finally:
            db.close()      # as in AddressSearchTests.write_state: Windows will not remove an open file

    def first(self, query, lat):
        """The right house comes first."""
        result = find_addresses(query, self.geo)
        self.assertTrue(result, query)
        self.assertEqual(result[0]['lat'], lat, query)
        return result[0]

    def test_normalize_fr_scheme(self):
        """The builder imports this function, so its output is the stored norm column and must follow scheme fr-1."""
        self.assertEqual(normalize_fr("Rue de l'Église"), 'rue de l eglise')
        self.assertEqual(normalize_fr('RUE DE L’EGLISE'), 'rue de l eglise')
        self.assertEqual(normalize_fr('Bd. St-Germain'), 'boulevard saint germain')
        self.assertEqual(normalize_fr('Mons-en-Barœul'), 'mons en baroeul')
        self.assertEqual(normalize_fr('Place des États-Unis'), 'place des etats unis')
        self.assertEqual(normalize_fr('R Victor Hugo'), 'rue victor hugo')
        self.assertEqual(normalize_fr('Rue Ave Maria'), 'rue ave maria')        # a type word inside the name stays
        self.assertEqual(normalize_fr('Rue Ste-Anne'), 'rue sainte anne')
        self.assertEqual(normalize("Rue de l'Église"), 'rue de l glise')         # the US scheme is untouched

    def test_postcode_before_commune(self):
        """'10 rue de Rivoli, 75001 Paris' in all its usual spellings, and named the French way."""
        for query in ('107 Rue de Rivoli, 75001 Paris', '107 rue de rivoli 75001 paris', '107 Rue de Rivoli Paris',
                      '107 rue de rivoli 75001', '107 RUE DE RIVOLI, 75001 PARIS', '107 rue de Rivoli Paris 75001'):
            with self.subTest(query=query):
                hit = self.first(query, 48.863214)
                self.assertEqual(hit['name'], '107 Rue de Rivoli')
                self.assertEqual(hit['detail'], '75001 Paris 1er Arrondissement')
                self.assertEqual(hit['kind'], 'Street address')
                self.assertEqual(hit['source'], FR_SOURCE)

    def test_commune_filters_a_shared_street(self):
        """Place de l'Hôtel de Ville 2 exists in Courbevoie and Vélizy: the commune or postcode picks one, a wrong one
        finds nothing. The invented Rue de l'Église 3 exists in both invented communes."""
        self.assertEqual(self.first('2 place de l hotel de ville courbevoie', 48.895241)['detail'], '92400 Courbevoie')
        self.assertEqual(self.first("2 place de l'hotel de ville, 78140 Velizy", 48.78274)['detail'], '78140 Vélizy-Villacoublay')
        self.assertEqual(self.first('2 place de l hotel de ville 92400', 48.895241)['detail'], '92400 Courbevoie')
        self.assertEqual(self.first('3 rue de l eglise autreville', 0.3)['detail'], '00001 Autreville')
        self.assertEqual(len(find_addresses("2 place de l'hôtel de ville", self.geo)), 2)
        self.assertEqual(len(find_addresses('3 rue de l eglise', self.geo)), 2)
        self.assertEqual(find_addresses('2 place de l hotel de ville Marseille', self.geo), [])
        self.assertEqual(find_addresses('2 place de l hotel de ville, 92400 Vélizy-Villacoublay', self.geo), [])

    def test_accents_case_and_apostrophes(self):
        """Accents, capitals and straight, curly or missing apostrophes all reach the same house, on every stored form:
        accented with a straight apostrophe (Courbevoie), unaccented with a curly one (Asnières)."""
        for query in ("2 Place de l'Hôtel de Ville, 92400 Courbevoie", '2 place de l hotel de ville courbevoie',
                      '2 place de l’hôtel de ville Courbevoie', "2 PLACE DE L'HOTEL DE VILLE COURBEVOIE", '2 place de l hôtel de ville 92400'):
            with self.subTest(query=query):
                self.assertEqual(self.first(query, 48.895241)['name'], "2 Place De L'Hôtel De Ville")
        for query in ("1 place de l'hôtel de ville asnieres", '1 Place de l’Hôtel de Ville, 92600 Asnières-sur-Seine'):
            with self.subTest(query=query):
                self.assertEqual(self.first(query, 48.910692)['name'], '1 Place de l’Hotel de Ville')
        for query in ("3 Rue de l'Église, 00000 Exemple", '3 rue de l eglise exemple', '3 rue de l’église Exemple', '3 RUE DE L EGLISE 00000'):
            with self.subTest(query=query):
                self.assertEqual(self.first(query, 0.1)['name'], "3 Rue de l'Église")
        self.assertEqual(self.first('27 avenue robert schuman mons en baroeul', 50.642482)['detail'], '59370 Mons-en-Barœul')

    def test_hyphens(self):
        for query in ('1 place de l hotel de ville asnieres sur seine', '1 Place de l’Hôtel-de-Ville, 92600 Asnières-sur-Seine'):
            with self.subTest(query=query):
                self.first(query, 48.910692)
        self.first('27 avenue robert schuman mons-en-baroeul', 50.642482)
        for query in ('55 rue du faubourg saint honore', '55 Rue du Faubourg-Saint-Honoré, 75008 Paris'):
            with self.subTest(query=query):
                self.first(query, 48.87063)

    def test_abbreviations(self):
        """bd, av, pl, r and st meet boulevard, avenue, place, rue and saint."""
        for query in ('246 boulevard saint-germain', '246 bd saint germain', '246 bd st germain', '246 Bd. St-Germain, 75007 Paris'):
            with self.subTest(query=query):
                self.assertEqual(self.first(query, 48.857224)['name'], '246 Boulevard Saint-Germain')
        for query in ('27 avenue robert schuman', '27 Av. Robert Schuman', '27 ave robert schuman mons en baroeul'):
            with self.subTest(query=query):
                self.first(query, 50.642482)
        self.first('2b av franklin d roosevelt', 48.867784)
        self.first('1 pl de l hotel de ville asnieres', 48.910692)
        self.first('107 r de rivoli 75001 paris', 48.863214)
        self.first('55 rue du faubourg st honore', 48.87063)

    def test_number_suffixes(self):
        """12bis, 12 bis and 12 BIS find the fused row; a plain 12 never returns 12bis, and a missing suffix finds nothing."""
        for query in ('3bis rue de l eglise exemple', "3 bis rue de l'église exemple", "3 BIS Rue de l'Eglise, 00000 Exemple"):
            with self.subTest(query=query):
                self.assertEqual(self.first(query, 0.2)['name'], "3bis Rue de l'Église")
        plain = find_addresses('3 rue de l eglise exemple', self.geo)
        self.assertEqual([hit['name'] for hit in plain], ["3 Rue de l'Église"])
        for query in ('1 b avenue de la gare', '1b Avenue de la Gare, 00000 Exemple', '1 B avenue de la gare exemple'):
            with self.subTest(query=query):
                self.assertEqual(self.first(query, 0.5)['name'], '1b Avenue de la Gare')
        self.assertEqual([hit['lat'] for hit in find_addresses('1 avenue de la gare exemple', self.geo)], [0.4])
        for query in ('2b avenue franklin d roosevelt', '2 B Av. Franklin D. Roosevelt, 75008 Paris'):      # stored as 2B, not 2bis
            with self.subTest(query=query):
                self.assertEqual(self.first(query, 48.867784)['name'], '2B Avenue Franklin D. Roosevelt')
        self.assertEqual(find_addresses('3 ter rue de l eglise exemple', self.geo), [])
        self.assertEqual(find_addresses('2 rue de l eglise exemple', self.geo), [])

    def test_single_letter_is_tried_as_suffix_then_as_elided_article(self):
        """'7 l'orme' may be house 7L or house 7 on L'Orme: both readings are searched, the suffix one first."""
        self.assertEqual([(number, words) for number, words, _, _ in _parts_fr("7 l'Orme")], [('7l', ['orme']), ('7', ['l', 'orme'])])
        self.assertEqual([number for number, *_ in _parts_fr('12 bis rue x')], ['12bis', '12b'])
        self.assertEqual([number for number, *_ in _parts_fr('12b rue x')], ['12b'])      # never the reverse
        self.assertEqual(_parts_fr('10 rue de Rivoli, 75001 Paris'), [('10', ['rue', 'de', 'rivoli'], '75001', ['paris'])])

    def test_bis_also_finds_the_letter_paris_stores(self):
        """Paris writes 2 bis as 2B and 2 ter as 2T: a typed bis also tries the letter, after the exact form."""
        for query in ('2 bis avenue franklin d roosevelt', '2bis avenue franklin d roosevelt', '2 BIS Avenue Franklin D. Roosevelt, 75008 Paris'):
            with self.subTest(query=query):
                self.assertEqual(self.first(query, 48.867784)['name'], '2B Avenue Franklin D. Roosevelt')
        self.assertEqual([hit['lat'] for hit in find_addresses('3 bis rue de l eglise exemple', self.geo)], [0.2, 0.7])
        self.assertEqual([hit['lat'] for hit in find_addresses('3 b rue de l eglise exemple', self.geo)], [0.7])

    def test_street_named_after_a_street_type(self):
        """'Avenue du Square' is all type words and particles, but still a street when a commune follows (found by the
        Paris measurement). The row is invented, with a placeholder commune, as such streets are mostly homes."""
        self.write_france(self.geo / 'addresses' / 'FR-example.sqlite', [('14', 'Avenue du Square', '00000', 'Exemple', 'fr/00', 1.0, 1.0)])
        for query in ('14 avenue du square exemple', '14 Avenue du Square, 00000 Exemple', '14 av du square exemple'):
            with self.subTest(query=query):
                self.first(query, 1.0)
        self.assertEqual(find_addresses('14 avenue exemple', self.geo), [])     # a bare type is still no street
        self.assertEqual([number for number, *_ in _parts_fr('183P55 Avenue de Clichy')], ['183p55'])

    def test_impasse_de_la_is_not_louisiana(self):
        """The US reader takes a final 'la' for the state LA; the French one keeps it in the street."""
        for query in ('5 impasse de la mairie', '5 impasse de la', '5 Impasse de la Mairie, 00000 Exemple',
                      '5 imp de la mairie exemple'):
            with self.subTest(query=query):
                self.assertEqual(self.first(query, 0.6)['name'], '5 Impasse de la Mairie')

    def test_postcode_and_commune_stay_place_queries(self):
        """'75001 Paris' and '20000 Ajaccio' start with a number like an address, but name places a French index knows."""
        for query in ('75001 Paris', '20000 Ajaccio', '75008 paris'):
            with self.subTest(query=query):
                self.assertTrue(is_address_query(query))
                self.assertEqual(find_addresses(query, self.geo), [])
                self.assertTrue(is_french_postcode_query(query, self.geo))
        self.assertTrue(is_french_postcode_query('20000, Ajaccio', self.geo))
        self.assertFalse(is_french_postcode_query('75001 Courbevoie', self.geo))
        self.assertFalse(is_french_postcode_query('18003 nine mile', self.geo))
        self.assertFalse(is_german_postcode_query('75001 Paris', self.geo))
        self.assertFalse(is_french_postcode_query('75001 Paris', self.geo / 'empty'))

    def test_us_and_french_indexes_side_by_side(self):
        """Each index is searched with its own rules only, and each query finds its own country's house."""
        AddressSearchTests.write_state(self, 'MI', [('18001', 'W Nine Mile Road', 'Novi', 'MI', '48375', 42.45, -83.47),
                                                    ('1', 'Saint Mary Avenue', 'Novi', 'MI', '48375', 42.40, -83.40)])
        hit, = find_addresses('18001 W Nine Mile Road, Novi, MI 48375', self.geo)
        self.assertEqual((hit['detail'], hit['source']), ('Novi, MI, 48375', 'Overture Maps'))
        hit, = find_addresses('107 rue de rivoli paris', self.geo)
        self.assertEqual((hit['name'], hit['source']), ('107 Rue de Rivoli', FR_SOURCE))
        hit, = find_addresses('1 st mary ave', self.geo)
        self.assertEqual(hit['detail'], 'Novi, MI, 48375')      # 'st' is saint under both rules, but only the US index holds it
        self.assertEqual([hit['detail'] for hit in find_addresses('2 place de l hotel de ville courbevoie', self.geo)], ['92400 Courbevoie'])

    def test_us_results_unchanged_with_france_installed(self):
        """Adding a fr-1 index must not change a single US answer, nor the legacy file's."""
        (self.geo / 'addresses' / 'FR.sqlite').unlink()
        AddressSearchTests.write_state(self, 'MI', [('18001', 'W Nine Mile Road', 'Novi', 'MI', '48375', 42.45, -83.47),
                                                    ('5', 'Lafayette Street', 'Novi', 'MI', '48375', 42.41, -83.41)])
        AddressSearchTests.write_state(self, 'LA', [('5', 'Impasse Road', 'Example', 'LA', '70112', 29.95, -90.07)])
        queries = ('18001 nine mile', '18001 W Nine Mile Road, Novi, MI 48375', '5 Lafayette', '5 impasse la', '18003 nine mile',
                   '5 lafayette st novi 48375')
        before = [find_addresses(query, self.geo) for query in queries]
        self.assertEqual(before[3][0]['detail'], 'Example, LA, 70112')
        self.write_france(self.geo / 'addresses' / 'FR.sqlite')
        self.assertEqual([find_addresses(query, self.geo) for query in queries], before)
        legacy = self.geo / 'legacy'
        (legacy / 'addresses').mkdir(parents=True)
        db = sqlite3.connect(legacy / 'addresses.sqlite')
        try:
            db.execute('CREATE TABLE addr(num TEXT,street TEXT,norm TEXT,city TEXT,state TEXT,zip TEXT,lat REAL,lon REAL)')
            db.execute("INSERT INTO addr VALUES('23001','Maple Avenue','maple ave','Kansas City','MO','64105',39.0997,-94.5786)")
            db.commit()
        finally:
            db.close()
        self.write_france(legacy / 'addresses' / 'FR.sqlite')
        self.assertEqual(find_addresses('23001 Maple Ave Kansas City MO', legacy)[0]['lat'], 39.0997)    # FR.sqlite is no US index

    def test_app_route_treats_postcode_and_commune_as_a_place(self):
        """'75001 Paris' falls through to the place search; an unknown US house stays an empty address answer.

        The place database is a stand-in that only records being asked, so no file stays open."""
        import server
        root = self.geo / 'root'
        geo = root / 'derived' / 'geo'
        (geo / 'addresses').mkdir(parents=True)
        self.write_france(geo / 'addresses' / 'FR.sqlite')
        for query, place_search in (('75001 Paris', True), ('20000 Ajaccio', True), ('18003 nine mile', False)):
            with self.subTest(query=query):
                placedb = MagicMock()
                placedb.exists.return_value = False
                with patch.object(server, 'HERE', root), patch.object(server, 'PLACEDB', placedb):
                    self.assertEqual(server.places(query), [])
                self.assertEqual(placedb.exists.called, place_search)
        with patch.object(server, 'HERE', root):
            hit, = server.places('107 Rue de Rivoli, 75001 Paris')
        self.assertEqual((hit['name'], hit['kind']), ('107 Rue de Rivoli', 'Street address'))


class FrenchBuilderRowTests(unittest.TestCase):
    """tools/build_addresses.py --country FR maps each Overture row with a pure function."""

    builder = load_builder()

    def test_row_mapping(self):
        row = self.builder.fr_row(' 3bis ', " Rue de l'Église ", 'Exemple', 'fr/92/statewide', '00000', 0.2, 0.2)     # invented
        self.assertEqual(row, ('3bis', "Rue de l'Église", 'rue de l eglise', 'Exemple', '92', '00000', 0.2, 0.2))

    def test_departement_from_dataset(self):
        for dataset, code in (('fr/75/statewide', '75'), ('fr/2A/statewide', '2A'), ('fr/2b', '2B'), ('fr/971/statewide', '971'), ('', '')):
            with self.subTest(dataset=dataset):
                self.assertEqual(self.builder.fr_row('1', 'Rue X', 'Y', dataset, '75001', 0.0, 0.0)[4], code)

    def test_us_norm_untouched(self):
        self.assertEqual(self.builder.norm('Saint Mary Boulevard'), 'st mary blvd')


if __name__ == '__main__':
    unittest.main()
