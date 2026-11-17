"""Read-only address lookup using the state indexes installed with offline maps."""
import math
import re
import sqlite3
import unicodedata
from pathlib import Path

from engine.paths import ro_uri

# Keep normalization compatible with tools/build_addresses.py.
WORDS = {
    'boulevard': 'blvd', 'avenue': 'ave', 'av': 'ave', 'street': 'st',
    'drive': 'dr', 'road': 'rd', 'place': 'pl', 'court': 'ct', 'lane': 'ln',
    'terrace': 'ter', 'circle': 'cir', 'highway': 'hwy', 'parkway': 'pkwy',
    'square': 'sq', 'north': 'n', 'south': 's', 'east': 'e', 'west': 'w',
    'mount': 'mt', 'saint': 'st',
}
STATE_NAMES = (
    'Alabama|Alaska|Arizona|Arkansas|California|Colorado|Connecticut|Delaware|'
    'District of Columbia|Florida|Georgia|Hawaii|Idaho|Illinois|Indiana|Iowa|'
    'Kansas|Kentucky|Louisiana|Maine|Maryland|Massachusetts|Michigan|Minnesota|'
    'Mississippi|Missouri|Montana|Nebraska|Nevada|New Hampshire|New Jersey|'
    'New Mexico|New York|North Carolina|North Dakota|Ohio|Oklahoma|Oregon|'
    'Pennsylvania|Puerto Rico|Rhode Island|South Carolina|South Dakota|'
    'Tennessee|Texas|Utah|Vermont|Virginia|Washington|West Virginia|Wisconsin|Wyoming'
).split('|')
STATE_CODES = 'AL AK AZ AR CA CO CT DE DC FL GA HI ID IL IN IA KS KY LA ME MD MA MI MN MS MO MT NE NV NH NJ NM NY NC ND OH OK OR PA PR RI SC SD TN TX UT VT VA WA WV WI WY'.split()
STATES = dict(zip((name.lower() for name in STATE_NAMES), STATE_CODES))
ONES = 'zero one two three four five six seven eight nine ten eleven twelve thirteen fourteen fifteen sixteen seventeen eighteen nineteen twenty'.split()
ORDINALS = 'zeroth first second third fourth fifth sixth seventh eighth ninth tenth eleventh twelfth thirteenth fourteenth fifteenth sixteenth seventeenth eighteenth nineteenth twentieth'.split()
TO_DIGITS = {word: str(number) for number, word in enumerate(ONES)}
for number, word in enumerate(ORDINALS):
    suffix = 'th' if 10 <= number % 100 <= 20 else {1: 'st', 2: 'nd', 3: 'rd'}.get(number % 10, 'th')
    TO_DIGITS[word] = f'{number}{suffix}'
TO_WORDS = {value: key for key, value in TO_DIGITS.items()}


US_NORM = 'us'        # indexes without a meta 'norm' key: the published US state indexes and the legacy addresses.sqlite
DE_NORM = 'de-1'
FR_NORM = 'fr-1'
_UMLAUTS = str.maketrans({'ä': 'ae', 'ö': 'oe', 'ü': 'ue', 'ß': 'ss'})
# French street types are expanded only as the street's first word ("Av. de l'Opéra"), saints anywhere
_FR_TYPES = {'bd': 'boulevard', 'bld': 'boulevard', 'boul': 'boulevard', 'av': 'avenue', 'ave': 'avenue', 'pl': 'place',
             'imp': 'impasse', 'all': 'allee', 'rte': 'route', 'sq': 'square', 'che': 'chemin', 'chem': 'chemin', 'r': 'rue'}
_FR_SAINTS = {'st': 'saint', 'ste': 'sainte'}
_FR_SUFFIXES = ('bis', 'ter', 'quater', 'quinquies')
_FR_PLAIN = {'de', 'du', 'des', 'la', 'le', 'les', 'l', 'd'}    # after a street type, not enough to name a street


def normalize(text):
    return ' '.join(WORDS.get(word, word) for word in re.sub(r'[^a-z0-9 ]+', ' ', text.lower()).split())


def normalize_de(text):
    """Scheme 'de-1': 'Müllerstraße' -> 'muellerstr', 'Straße des 17. Juni' -> 'str des 17 juni'.

    German indexes store this in their norm column, so the builder imports it and queries use it unchanged."""
    text = unicodedata.normalize('NFC', text).lower().translate(_UMLAUTS)
    words = re.sub(r'[^a-z0-9 ]+', ' ', text).split()
    return ' '.join(word[:-len('strasse')] + 'str' if word.endswith('strasse') else word for word in words)


def normalize_fr(text):
    """Scheme 'fr-1': "Bd Saint-Germain" -> 'boulevard saint germain', "Rue de l'Église" -> 'rue de l eglise'.

    French indexes store this in their norm column, so the builder imports it and queries use it unchanged."""
    text = unicodedata.normalize('NFKD', text.lower().replace('œ', 'oe').replace('æ', 'ae'))
    text = ''.join(char for char in text if not unicodedata.combining(char))
    words = [_FR_SAINTS.get(word, word) for word in re.sub(r'[^a-z0-9 ]+', ' ', text).split()]
    return ' '.join([_FR_TYPES.get(words[0], words[0]), *words[1:]] if words else words)


def is_address_query(query):
    """A standalone ZIP remains a place query. A number followed by words is an address."""
    return bool(re.match(r'^\s*\d[\w-]*\s+\S', query))


def is_german_address_query(query):
    """Street words, then a house number, then an optional postcode and place ('Unter den Linden 77, 10117 Berlin').

    This form also fits place names such as 'Route 66', so callers search places when no address matches."""
    return _parts_de(query) is not None


def _parts_de(query):
    """(number, street words, postcode, qualifier words) in German order, or None.

    The house number is the last number before an optional postcode and place, so 'Straße des 17. Juni 135' keeps
    its 17 in the street. A single letter after the number is its suffix: '12 a' -> '12A'."""
    tokens = normalize_de(query).split()
    end = len(tokens)
    while end and not re.search(r'\d', tokens[end - 1]):
        end -= 1
    head, qualifier = tokens[:end], tokens[end:]
    postcode = suffix = ''
    if len(head) >= 3 and re.fullmatch(r'\d{5}', head[-1]) and (
            re.fullmatch(r'\d+[a-z]?', head[-2]) or (re.fullmatch(r'[a-z]', head[-2]) and head[-3].isdigit())):
        postcode = head.pop()
    if head and head[-1].isdigit() and not postcode and qualifier and len(qualifier[0]) == 1:
        suffix = qualifier.pop(0)
    elif len(head) >= 2 and re.fullmatch(r'[a-z]', head[-1]) and head[-2].isdigit():
        suffix = head.pop()
    if not head or not re.fullmatch(r'\d+[a-z]?', head[-1]):
        return None
    number = (head.pop() + suffix).upper()
    if not any(re.search(r'[a-z]', word) for word in head):
        return None
    return number, head, postcode, qualifier


def is_german_postcode_query(query, geo_directory):
    """'10117 Berlin': a postcode and a place that an installed German index knows together. That is a place, even
    though it starts with a number like a US address; without a German index the answer is always False."""
    match = re.fullmatch(r'\s*(\d{5})[\s,]+([^\d]+)', query)
    if not match:
        return False
    postcode, qualifier = match.group(1), normalize_de(match.group(2))
    if not qualifier:
        return False
    for path in sorted((Path(geo_directory) / 'addresses').glob('*.sqlite')):
        if _index_info(path)[0] != DE_NORM:
            continue
        try:
            connection = sqlite3.connect(ro_uri(path), uri=True)
            try:
                found = connection.execute('SELECT DISTINCT city, district FROM addr WHERE zip = ?', (postcode,)).fetchall()
            finally:
                connection.close()
        except sqlite3.Error:
            continue
        if any(_place_matches(qualifier, city, district) for city, district in found):
            return True
    return False


def is_french_postcode_query(query, geo_directory):
    """'75001 Paris': a postcode and a commune that an installed French index knows together, so a place, as for German."""
    match = re.fullmatch(r'\s*(\d{5})[\s,]+([^\d]+)', query)
    if not match or not normalize_fr(match.group(2)):
        return False
    for path in sorted((Path(geo_directory) / 'addresses').glob('*.sqlite')):
        if _index_info(path)[0] != FR_NORM:
            continue
        try:
            connection = sqlite3.connect(ro_uri(path), uri=True)
            try:
                found = connection.execute('SELECT DISTINCT city FROM addr WHERE zip = ?', (match.group(1),)).fetchall()
            finally:
                connection.close()
        except sqlite3.Error:
            continue
        if any(normalize_fr(city or '').startswith(normalize_fr(match.group(2))) for city, in found):
            return True
    return False


def _parts_fr(query):
    """[(number, street words, postcode, commune words)] in French order, one entry per reading of the number.

    '12bis', '12 bis' and '12 BIS' are all number '12bis'. A single letter after the number may be its suffix ('3 b') or
    an elided article ("7 l'Orme"), so both readings are returned, the suffix first. A postcode follows the street."""
    tokens = normalize_fr(query).split()
    if len(tokens) < 2 or not re.fullmatch(r'\d+[a-z0-9]*', tokens[0]):      # Paris also has numbers such as '183P55'
        return []
    number, rest = tokens[0], tokens[1:]
    readings = [(number, rest)]
    if number.isdigit() and len(rest) > 1 and rest[0] in _FR_SUFFIXES:
        readings = [(number + rest[0], rest[1:])]
    elif number.isdigit() and len(rest) > 1 and len(rest[0]) == 1:
        readings.insert(0, (number + rest[0], rest[1:]))
    match = re.fullmatch(r'(\d+)(bis|ter|quater)', readings[0][0])
    if match:       # Paris writes 12 bis as 12B: tried after the exact form
        readings.insert(1, (match.group(1) + match.group(2)[0], readings[0][1]))
    parts = []
    for number, words in readings:
        postcode, after = '', []
        for index in range(1, len(words)):
            if re.fullmatch(r'\d{5}', words[index]):
                postcode, words, after = words[index], words[:index], words[index + 1:]
                break
        parts.append((number, words, postcode, after))
    return parts


def _place_matches(qualifier, city, district):
    """The place after a German number may name the city or the Ortsteil, prefix-matched like the US city filter."""
    city, district = city or '', district or ''
    places = (normalize_de(city), normalize_de(district), normalize_de(f'{city} {district}'))
    return any(place.startswith(qualifier) for place in places if place)


_INFO = {}


def _index_info(path):
    """(norm scheme, source line) from an index's meta table, cached until the file changes."""
    try:
        stat = path.stat()
    except OSError:
        return US_NORM, None
    key = (str(path), stat.st_mtime_ns, stat.st_size)
    if key not in _INFO:
        meta = {}
        try:
            connection = sqlite3.connect(ro_uri(path), uri=True)
            try:
                meta = dict(connection.execute("SELECT key,value FROM meta WHERE key IN ('norm','source')").fetchall())
            finally:
                connection.close()
        except sqlite3.Error:
            pass        # no meta table: an index from before norm schemes, so US rules
        _INFO[key] = (meta.get('norm') or US_NORM, meta.get('source'))
    return _INFO[key]


def street_forms(street):
    words = street.split()
    forms = [street, ' '.join(TO_DIGITS.get(word, word) for word in words),
             ' '.join(TO_WORDS.get(word, word) for word in words)]
    forms += [re.sub(r'\b(\d+)(st|nd|rd|th)\b', r'\1', form) for form in forms[:]]
    if words[0] not in ('n', 's', 'e', 'w', 'ne', 'nw', 'se', 'sw'):
        forms += [f'{direction} {form}' for form in forms[:] for direction in ('n', 's', 'e', 'w')]
    return list(dict.fromkeys(forms))


def _parts(query):
    number, remainder = query.strip().split(None, 1)
    number = number.upper()
    remainder = re.sub(r'[^a-z0-9 ]+', ' ', remainder.lower()).split()
    postcode = ''
    if remainder and re.fullmatch(r'\d{5}', remainder[-1]):
        postcode = remainder.pop()
    state = ''
    for count in (3, 2, 1):
        if len(remainder) <= count:
            continue
        name = ' '.join(remainder[-count:])
        code = STATES.get(name) or (name.upper() if count == 1 and name.upper() in STATE_CODES else '')
        if code:
            state = code
            remainder = remainder[:-count]
            break
    return number, normalize(' '.join(remainder)).split(), state, postcode


def _rank(near):
    def rank(row):
        distance = 0
        if near:
            distance = (row[5] - near[0]) ** 2 + ((row[6] - near[1]) * math.cos(math.radians(near[0]))) ** 2
        return len(row[7]), distance, row[3], row[2], row[1]
    return rank


def find_addresses(query, geo_directory, limit=8, near=None):
    """Return exact house-number matches from installed indexes, never a guessed house.

    A number-first query searches the US-normalized indexes, then the fr-1 ones with French rules; a German-order query
    ('Müllerstr. 12a') searches the indexes whose meta norm is de-1. Each index is only ever searched with its own normalization."""
    if is_address_query(query):
        found = _find_us(query, Path(geo_directory), limit, near)
        return found + _find_fr(query, Path(geo_directory), limit - len(found), near) if len(found) < limit else found
    parts = _parts_de(query)
    if parts is None:
        return []
    return _find_de(parts, Path(geo_directory), limit, near)


def _find_de(parts, geo_directory, limit, near):
    number, words, postcode, qualifier = parts
    street, qualifier = ' '.join(words), ' '.join(qualifier)
    paths = [path for path in sorted((geo_directory / 'addresses').glob('*.sqlite')) if _index_info(path)[0] == DE_NORM]
    conditions = ['num IN (?, ?)', 'norm >= ?', 'norm < ?']
    parameters = [number, number.lower(), street, street + '\uffff']
    if postcode:
        conditions.append('zip = ?')
        parameters.append(postcode)
    sql = ('SELECT num,street,city,state,zip,lat,lon,norm,district FROM addr WHERE '
           + ' AND '.join(conditions) + ' ORDER BY length(norm),norm LIMIT 500')
    rows = []
    for path in paths:
        source = _index_info(path)[1] or 'Overture Maps'
        try:
            connection = sqlite3.connect(ro_uri(path), uri=True)
        except sqlite3.Error:
            continue
        try:
            found = connection.execute(sql, parameters).fetchall()
        except sqlite3.Error:
            continue
        finally:
            connection.close()
        rows.extend((*row, source) for row in found if not qualifier or _place_matches(qualifier, row[2], row[8]))
    results, seen = [], set()
    for num, name, city, state, zip_code, lat, lon, normalized, district, source in sorted(rows, key=_rank(near)):
        key = (num, normalized, lat, lon)
        if key in seen:
            continue
        seen.add(key)
        place = f'{city}-{district}' if district else city
        results.append({
            'name': f'{name} {num}', 'kind': 'Street address',
            'detail': ' '.join(part for part in (zip_code, place) if part),
            'lat': lat, 'lon': lon, 'source': source, 'onMap': True,
        })
        if len(results) == limit:
            break
    return results


def _find_fr(query, geo_directory, limit, near):
    paths = [path for path in sorted((geo_directory / 'addresses').glob('*.sqlite')) if _index_info(path)[0] == FR_NORM]
    connections, results, seen = [], [], set()
    try:
        for path in paths:
            try:
                connections.append((sqlite3.connect(ro_uri(path), uri=True), _index_info(path)[1] or 'Overture Maps'))
            except sqlite3.Error:
                continue
        for number, words, postcode, after in _parts_fr(query) if connections else []:
            rows = []
            # without a postcode the commune may follow the street: the longest street is tried first, as for the US
            for count in [len(words)] if after else range(len(words), 0, -1):
                street, commune = normalize_fr(' '.join(words[:count])), normalize_fr(' '.join(words[count:] + after))
                if commune and street.split()[0] in _FR_TYPES.values() and all(word in _FR_PLAIN for word in street.split()[1:]):
                    continue        # '10 rue Paris' must not become every number 10 of a street in Paris
                conditions = ["lower(replace(num, ' ', '')) = ?", 'norm >= ?', 'norm < ?']   # '12 bis' is stored as '12bis' or '12 bis'
                parameters = [number, street, street + '\uffff']
                if postcode:
                    conditions.append('zip = ?')
                    parameters.append(postcode)
                if commune:     # filtered in SQL so a national index cannot crowd the commune out of the LIMIT
                    conditions.append('fr_commune(city)')
                sql = ('SELECT num,street,city,state,zip,lat,lon,norm FROM addr WHERE '
                       + ' AND '.join(conditions) + ' ORDER BY length(norm),norm LIMIT 500')
                for connection, source in connections:
                    connection.create_function('fr_commune', 1, lambda city: normalize_fr(city or '').startswith(commune), deterministic=True)
                    try:
                        rows.extend((*row, source) for row in connection.execute(sql, parameters).fetchall())
                    except sqlite3.Error:
                        continue
                if rows:
                    break
            for num, name, city, state, zip_code, lat, lon, normalized, source in sorted(rows, key=_rank(near)):
                key = (num, normalized, lat, lon)
                if key in seen:
                    continue
                seen.add(key)
                results.append({
                    'name': f'{num} {name}', 'kind': 'Street address',
                    'detail': ' '.join(part for part in (zip_code, city) if part),
                    'lat': lat, 'lon': lon, 'source': source, 'onMap': True,
                })
                if len(results) == limit:
                    return results
        return results
    finally:
        for connection, _ in connections:
            connection.close()


def _find_us(query, geo_directory, limit, near):
    number, words, state, postcode = _parts(query)
    if not words:
        return []
    paths = [path for path in sorted((geo_directory / 'addresses').glob('*.sqlite')) if _index_info(path)[0] == US_NORM]
    if state:
        paths = [path for path in paths if path.stem.upper() == state]
    legacy = geo_directory / 'addresses.sqlite'
    if not paths and legacy.is_file():
        paths = [legacy]
    connections = []
    try:
        for path in paths:
            try:
                connections.append(sqlite3.connect(ro_uri(path), uri=True))
            except sqlite3.Error:
                continue
        for count in range(len(words), 0, -1):
            street = ' '.join(words[:count])
            if all(word in set(WORDS.values()) for word in words[:count]):
                continue
            city = ' '.join(words[count:])
            rows = []
            for form in street_forms(street):
                conditions = ['num IN (?, ?)', 'norm >= ?', 'norm < ?']
                parameters = [number, number.lower(), form, form + '\uffff']
                if state:
                    conditions.append('state = ?')
                    parameters.append(state)
                if postcode:
                    conditions.append('zip = ?')
                    parameters.append(postcode)
                if city:
                    conditions.append('lower(city) LIKE ?')
                    parameters.append(city + '%')
                sql = ('SELECT num,street,city,state,zip,lat,lon,norm FROM addr WHERE '
                       + ' AND '.join(conditions) + ' ORDER BY length(norm),norm LIMIT ?')
                for connection in connections:
                    try:
                        rows.extend(connection.execute(sql, [*parameters, limit * 3]).fetchall())
                    except sqlite3.Error:
                        continue
            if rows:
                results, seen = [], set()
                for num, name, city_name, state_code, zip_code, lat, lon, normalized in sorted(rows, key=_rank(near)):
                    key = (num, normalized, lat, lon)
                    if key in seen:
                        continue
                    seen.add(key)
                    results.append({
                        'name': f'{num} {name}', 'kind': 'Street address',
                        'detail': ', '.join(part for part in (city_name, state_code, zip_code) if part),
                        'lat': lat, 'lon': lon, 'source': 'Overture Maps', 'onMap': True,
                    })
                    if len(results) == limit:
                        break
                return results
        return []
    finally:
        for connection in connections:
            connection.close()
