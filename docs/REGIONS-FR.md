# Detailed maps for France: a proposal

This is a proposal for discussion, not a decision. It answers, for France, the questions [MAPS.md](MAPS.md) asks before
coverage can go beyond the United States: which open source replaces each federal list, under what licence, what a
"state" is there, and how addresses are written. It follows the shape of [REGIONS.md](REGIONS.md) and
[REGIONS-DE.md](REGIONS-DE.md) and is meant to feed the same design discussion (issues #23, #25 and #31). The
machine-readable version is [regions-fr-proposed.json](regions-fr-proposed.json).

Nothing here changes the app, the engine or a build. No code reads the JSON, and nothing here ships: builds package
`web/` and `content/` only.

**How things were checked.** Research was done on 17 November 2026, with AI research agents reading the publishers' own
pages and files and running the measurements, and a person reviewing the result. Each fact carries one of five marks:

- **opened**: the dataset, download feed, file or licence page itself was opened and read;
- **search only**: the fact was seen in a search result, but the page itself was not opened;
- **not checked**: the page could not be reached or read; the text says what is missing;
- **measured**: counted or computed from an opened file, feed or service (the boxes, the Overture, OSM and BD TOPO
  counts);
- **tried**: the repository's own address code was run, unchanged, on French examples.

IGN's dataset pages on cartes.gouv.fr are JavaScript applications, so IGN facts come mostly from its download feeds,
metadata records and PDFs. The ISO site refused automated requests, so its entry for France was opened in a browser
during the review, as were IGN's ADMIN EXPRESS page and INSEE's legal notice. IGN's download service refused some
requests (HTTP 429) after several hundred, so a few totals are partial. A figure that is derived or estimated says so.

## Why France is a useful case

Unlike Germany, France has one national mapping agency, IGN, that publishes most layers for the whole country, and one
licence, the Licence Ouverte 2.0, covers most of them: elevation, water, buildings, crop parcels, place names and
boundaries. IGN's press material says its public data have been free under that licence since 1 January 2021 (search
only). The national address base (Base Adresse Nationale, BAN) is already in Overture, 26,052,116 rows for France, so
addresses are the layer closest to the US build. And the five overseas regions, in the Caribbean, South America and the
Indian Ocean, test the rules far from Europe: other hemispheres, tropical crops, separate OSM extracts, and national
datasets that leave out Guyane.

## What a region is

France has 18 administrative regions: 13 in metropolitan France, Corsica included, and five overseas (Guadeloupe,
Martinique, Guyane, La Réunion, Mayotte), each of which is also a single department. The proposal is one map region per
administrative region, 18 in all, the same level as a US state. The list and codes are INSEE's Code officiel
géographique 2026 (`v_region_2026.csv`, opened); IGN's boundary layer carries the same 18 codes (opened). The
metropolitan regions are recent: a law of 16 January 2015 merged 22 of them into 13 on 1 January 2016 (a legal
commentary opened; the law itself search only), so older data still shows former regions such as Alsace. They are also
broad: Île-de-France covers about 12,000 km² and Nouvelle-Aquitaine about 85,000 km² (computed from the polygons). A
finer unit exists: 101 departments (`v_departement_2026.csv`, opened), about 6,300 km² on average.

### Codes

The codes are ISO 3166-2:FR, checked against ISO's Online Browsing Platform (its entry for `FR`, opened in a browser
on 17 November 2026): all 18 are in its list. Debian's `iso-codes` data and the English Wikipedia page (both opened)
agree with it.

- The 12 metropolitan regions other than Corsica have three letters: `FR-IDF` Île-de-France, `FR-ARA`
  Auvergne-Rhône-Alpes, `FR-PAC` Provence-Alpes-Côte d'Azur, and so on. ISO's category is "metropolitan region".
- **Corsica is `FR-20R`**, a "metropolitan collectivity with special status". ISO's change history dates the change
  from `FR-COR` to `FR-20R` to 24 November 2020.
- **The overseas regions use their department numbers**, `FR-971` to `FR-976` (no 975). ISO files `FR-971`, `FR-974`
  and `FR-976` as "overseas departmental collectivity" and `FR-972` and `FR-973` as "overseas unique territorial
  collectivity". Its change history deletes the older forms (`FR-GP`, `FR-MQ`, `FR-GF`, `FR-RE`, `FR-YT`) and the
  category "overseas region" on 25 November 2021; pages found by search still use them. Each overseas region also has
  its own ISO 3166-1 code (`GP`, `MQ`, `GF`, `RE`, `YT`).
- ISO also lists `FR-75C` Paris, `FR-69M` Métropole de Lyon and `FR-6AE` Alsace, which are not regions and need no map.
  Names are shown as INSEE and IGN write them; ISO hyphenates three differently ("Grand-Est", "Pays-de-la-Loire",
  "Provence-Alpes-Côte-d'Azur").

Collision check against the 52 entries of `STATE_CODES` (`engine/address_search.py`), run as a script: a bare `FR` is
not a US code but is the whole country, so hyphenated codes are kept, as in REGIONS-DE.md. No part after the hyphen
collides, since all have three characters and every US code two letters, and `GP`, `MQ`, `GF`, `RE` and `YT` are not in
the list either.

**What the setup code accepts today** (read in `engine/setup/manifest.py` and `engine/setup/install.py`, not run):

- A map `id` only has to match `NAME`, `^[A-Za-z0-9][A-Za-z0-9._-]{0,120}$`, so `FR-IDF`, `FR-20R` and `FR-971` pass,
  hyphen and digits included.
- An address index `id` must be exactly two capital letters (`[A-Z]{2}` in `validate()`); any other value makes the
  whole manifest invalid. `carry_over()` likewise keeps only index files named with two capital letters when a library
  is replaced. So every hyphenated code, French or German, needs these two rules widened before it can have an address
  index.

### Boxes

The boxes were computed from IGN's **ADMIN EXPRESS**, COG variant, edition of 1 January 2026, layer
`ADMINEXPRESS-COG.2026:region`, fetched on 17 November 2026 from IGN's Géoplateforme WFS with this public request:

```
https://data.geopf.fr/wfs/ows?SERVICE=WFS&VERSION=2.0.0&REQUEST=GetFeature&TYPENAMES=ADMINEXPRESS-COG.2026:region&OUTPUTFORMAT=application/json&SRSNAME=EPSG:4326&COUNT=100
```

It returned the 18 regions in WGS 84 (about 88 MB of GeoJSON). Each box is the minimum and maximum of every vertex
(measured), widened by 0.15° and rounded outward to 0.01°, the same margin `map_sets.state` uses for US states. As a
check, the edges match the extreme points on the English Wikipedia page (secondary; no IGN page was found): Lavezzi
(41.33° N), Ouessant (5.13° W), San-Giuliano (9.55° E), and on the mainland Puig de Comanegra and Lauterbourg. The page
gives Bray-Dunes as 51°04′ N against a box edge of 51.09° N, 0.02° apart because its figure is coarse. Overseas extreme
points were not checked.

| Code | INSEE | Name | Box (west, south, east, north) | Box with 0.15° margin |
|---|---|---|---|---|
| `FR-971` | 01 | Guadeloupe | -61.8098, 15.8320, -61.0020, 16.5145 | -61.96, 15.68, -60.85, 16.67 |
| `FR-972` | 02 | Martinique | -61.2290, 14.3886, -60.8097, 14.8787 | -61.38, 14.23, -60.65, 15.03 |
| `FR-973` | 03 | Guyane (French Guiana) | -54.6024, 2.1111, -51.6191, 5.7487 | -54.76, 1.96, -51.46, 5.90 |
| `FR-974` | 04 | La Réunion (Réunion) | 55.2165, -21.3896, 55.8367, -20.8718 | 55.06, -21.54, 55.99, -20.72 |
| `FR-976` | 06 | Mayotte | 45.0183, -13.0054, 45.3000, -12.6366 | 44.86, -13.16, 45.45, -12.48 |
| `FR-IDF` | 11 | Île-de-France | 1.4463, 48.1201, 3.5590, 49.2415 | 1.29, 47.97, 3.71, 49.40 |
| `FR-CVL` | 24 | Centre-Val de Loire | 0.0527, 46.3469, 3.1287, 48.9410 | -0.10, 46.19, 3.28, 49.10 |
| `FR-BFC` | 27 | Bourgogne-Franche-Comté | 2.8449, 46.1561, 7.1434, 48.4001 | 2.69, 46.00, 7.30, 48.56 |
| `FR-NOR` | 28 | Normandie (Normandy) | -1.9550, 48.1799, 1.8029, 50.0722 | -2.11, 48.02, 1.96, 50.23 |
| `FR-HDF` | 32 | Hauts-de-France | 1.3802, 48.8372, 4.2558, 51.0892 | 1.23, 48.68, 4.41, 51.24 |
| `FR-GES` | 44 | Grand Est | 3.3837, 47.4203, 8.2325, 50.1693 | 3.23, 47.27, 8.39, 50.32 |
| `FR-PDL` | 52 | Pays de la Loire | -2.6255, 46.2666, 0.9167, 48.5680 | -2.78, 46.11, 1.07, 48.72 |
| `FR-BRE` | 53 | Bretagne (Brittany) | -5.1413, 47.2779, -1.0156, 48.9008 | -5.30, 47.12, -0.86, 49.06 |
| `FR-NAQ` | 75 | Nouvelle-Aquitaine | -1.7924, 42.7779, 2.6113, 47.1760 | -1.95, 42.62, 2.77, 47.33 |
| `FR-OCC` | 76 | Occitanie | -0.3272, 42.3329, 4.8456, 45.0467 | -0.48, 42.18, 5.00, 45.20 |
| `FR-ARA` | 84 | Auvergne-Rhône-Alpes | 2.0629, 44.1155, 7.1856, 46.8043 | 1.91, 43.96, 7.34, 46.96 |
| `FR-PAC` | 93 | Provence-Alpes-Côte d'Azur | 4.2302, 42.9820, 7.7190, 45.1268 | 4.08, 42.83, 7.87, 45.28 |
| `FR-20R` | 94 | Corse (Corsica) | 8.5347, 41.3336, 9.5600, 43.0276 | 8.38, 41.18, 9.71, 43.18 |

INSEE is the region code in the Code officiel géographique, as in the layer's `code_insee` field. Centre-Val de Loire's
west edge is 0.0527° E, so its margin box crosses the Greenwich meridian.

### Oddities

- **Overlaps.** No box wholly contains another region's box, with or without the margin (measured), so there is no case
  like Berlin inside Brandenburg. But many overlap in part: `FR-IDF` overlaps five neighbours (`FR-NOR`, `FR-HDF`,
  `FR-CVL`, `FR-GES`, `FR-BFC`) and `FR-CVL` six, so neighbours' rows spill in at the edges, as for US states.
- **Coast and islands.** The polygons are land, bounded by the coastline: our inference from the computed areas
  (Mayotte 366 km², without its lagoon); IGN's content description (version 4.0, May 2025, opened) does not say where
  the boundary runs at the coast. So the sea lies outside the boxes
  except for the margin. Ouessant and Molène move Brittany's west edge by 0.35° (about 30 km); Les Saintes,
  Marie-Galante and La Désirade widen Guadeloupe's box by 0.17° to 0.36° (measured; island names are our reading).
- **Guyane** has 83,129 km² of land (computed) in a box of about 134,000 km², as large as Bavaria's box in
  REGIONS-DE.md. About 40 % of the box lies in Suriname, Brazil or the ocean, whose rows would fall into a Guyane map.
  The overseas boxes lie in other hemispheres, so no single "France" box can hold them.
- **Not among the 18**: Saint-Martin, Saint-Barthélemy, Saint-Pierre-et-Miquelon, New Caledonia, French Polynesia,
  Wallis and Futuna and the French Southern Territories (opened). Yet Overture puts Saint-Barthélemy and Saint-Martin
  under Guadeloupe's `971` postcodes (measured), and the cadastre folds them into Guadeloupe (opened). Both lie far
  outside Guadeloupe's box: IGN's BD TOPO layer `collectivite_territoriale` puts Saint-Barthélemy at 62.93° to 62.79° W,
  17.87° to 17.97° N and Saint-Martin at 63.15° to 62.97° W, 18.05° to 18.13° N (measured on the WFS), at least 1.2°
  north and 0.8° west of the margin box. A Guadeloupe map would not show their streets.
- **Boundaries in dispute** touch three boxes. Between Guyane and Suriname, the two countries' maps put the border on
  different rivers over about 3,000 km² (French Senate report of June 2025, opened); the `FR-973` box's south-west
  corner lies there, and IGN's polygon follows the French reading. French and Italian maps place the summit of Mont
  Blanc (`FR-ARA`) differently (search only; effect on the box not checked). UN General Assembly resolutions reaffirm
  the Comoros' claim to Mayotte (search only); INSEE and IGN treat it as a French region.

### A first region to build

If one region is built first, Île-de-France is a natural candidate: small and dense. Its box is 1.4463, 48.1201,
3.5590, 49.2415 (1.29, 47.97, 3.71, 49.40 with the margin), about 155 by 125 km or 19,300 km² (computed). Its area is
12,012 km² in a ministry document and an INSEE sheet (search only); our polygon computation gives 12,070 km². INSEE
gives 12,463,100 people on 1 January 2023 (12,463,067 in a table on the same page), in eight departments and 1,266
communes (opened). Its box takes in slices of five neighbours. This is a suggestion, not a promise of work.

## Sources, layer by layer

### Nationwide

| Layer (file) | US source today | Proposed for France | Publisher | Licence | Checked |
|---|---|---|---|---|---|
| Terrain (`terrain.sqlite`) | USGS 3DEP, 1 arc-second | **BD ALTI 25 m**, a bare-ground model, one ASCII grid per department, the five overseas regions included | IGN | Licence Ouverte 2.0 | feed and metadata record opened; sizes partly rate-limited |
| Terrain, finer | | RGE ALTI 1 m and 5 m (updates stopped in 2024); MNT LiDAR HD, 0.5 m tiles, still in production | IGN | Licence Ouverte 2.0 | opened |
| Terrain, single source | | Copernicus DEM GLO-30, a surface model | ESA / Airbus | Copernicus WorldDEM-30 licence | licence PDF opened; nine sample tiles answered |
| Water (`water.sqlite`) | NHD | **BD TOPAGE 2026** "Plans d'eau" for lakes, ponds and reservoirs; BD TOPO 3.5 `surface_hydrographique` for marsh, lagoon, mangrove and estuary; BD TOPO alone in Guyane | Sandre / OFB with IGN; IGN | Licence Ouverte 2.0 | records, download headers and BD TOPO content PDF opened |
| River lines (in `national.sqlite` today) | OSM | BD TOPAGE "Tronçons hydrographiques" or BD TOPO `troncon_hydrographique`; OSM as today | Sandre / OFB; IGN; OSM contributors | Licence Ouverte 2.0; ODbL | opened; OSM counts from taginfo |
| Dams | NID | ROE, the national list of obstacles to river flow (not a dam register); BD TOPO `Barrage`; OSM `waterway=dam` | Sandre / OFB; IGN; OSM contributors | Licence Ouverte, version not stated; Licence Ouverte 2.0; ODbL | ROE record opened; counts measured on the WFS |
| Crops (`crops.sqlite`) | USDA Cropland Data Layer | **RPG 2025** "Parcelles", declared farm parcels with a crop code; the OSO land cover raster as the alternative | IGN, from the ASP; Theia / CNES / CESBIO | Licence Ouverte 2.0; OSO stated two ways (see notes) | RPG opened; OSO download not completed |
| Buildings (`buildings.sqlite`) | Microsoft US footprints, OSM heights | **BD TOPO `batiment`**, footprints with a height; cadastre buildings as the fallback; OSM or Overture | IGN; DGFiP through Etalab; OSM contributors; Overture | Licence Ouverte 2.0; ODbL | opened; counts measured on the WFS |
| Places (`places.sqlite`) | GNIS, Census gazetteers, OSM | BD TOPO named places and communes; INSEE COG; ADMIN EXPRESS; La Poste's postcode base; GeoNames; OSM named places | IGN; INSEE; La Poste; GeoNames; OSM contributors | Licence Ouverte 2.0 (INSEE: see licence notes); CC BY 4.0; ODbL | opened; La Poste and INSEE files counted |
| Addresses (`addresses/<code>.sqlite`) | Overture addresses | **Overture addresses**, which carry the BAN for all of France, overseas included; the BAN's own files as the alternative | Overture Maps Foundation, from the BAN through OpenAddresses | Licence Ouverte 2.0 (`etalab-2.0`) | opened; measured |
| Points of interest (`poi` rows) | OSM | OSM, as today; BD TOPO `zone_d_activite_ou_d_interet`, Géo'DAE and FINESS as official cross-checks | OSM contributors; IGN; health agencies | ODbL; Licence Ouverte 2.0 | taginfo and WFS counts; files counted |

### Overseas coverage

Coverage of the five overseas regions differs by dataset (opened unless marked):

| Dataset | Metropolitan France | 971 | 972 | 973 Guyane | 974 | 976 |
|---|---|---|---|---|---|---|
| BD ALTI, RGE ALTI, BD TOPO, ROE, RPG 2025, cadastre, Overture addresses | yes | yes | yes | yes | yes | yes |
| MNT LiDAR HD | planned "by 2026", progress not read | planned | planned | **excluded** | planned | planned |
| Copernicus GLO-30 | sample tiles | sample tile | sample tile | sample tiles | sample tile | sample tile |
| BD TOPAGE 2026, INPE 2023 | yes | yes | yes | **no** (INPE), **not found** (TOPAGE) | yes | yes |
| OSO (crops) | yes, Corsica included | no | no | no | no | no |
| CORINE Land Cover | 2018 | 2012 | 2012 | 2012 | 2012 | 2012 |
| GeoNames postcodes; OSM extracts (Geofabrik) | `FR.zip`; `france-latest.osm.pbf` | own files | own files | own files | own files | own files |

TOPAGE's absence in Guyane rests on the State catalogue's listing and two guessed file names that returned 404 (not
proof); INPE's record says Guyane is "in progress". Only Guyane's Geofabrik extract has the `.gpkg.zip` form that
`tools/build_map.py` reads. Two readings of the extract sizes differ slightly (24.8 and 23.6 MB for Guadeloupe).

Notes:

- **Terrain.** BD ALTI 25 m, derived from RGE ALTI, is the closest to the app's 30 m. 83 of its 104 files total about
  2.6 GB (21 answered HTTP 429), so about 3 GB in all (our estimate). The grids are in Lambert-93 or a local UTM system
  and need reprojecting into the one-degree geographic GeoTIFFs `tools/build_terrain.py` expects. IGN says RGE ALTI
  rests on radar in the Alps, Pyrenees, Cévennes and Corsica, closer to a surface model there, and some overseas
  editions are old (Mayotte 2013, Guadeloupe 2014, Martinique 2015). GLO-30 covers all territories but is a surface
  model, as REGIONS.md says; its tiles are named by their lower-left corner; its completeness was not checked.
- **Water.** TOPAGE 2026 is generated from BD TOPO's water theme of December 2025. Its "Plans d'eau" leave out
  marshes, lagoons, mangroves and harbour, fish and storm basins, hence the pairing with BD TOPO, whose `nature` values
  map onto the US kinds (`Lac`, `Mare`, `Retenue`, `Marais`, `Estuaire` and others). The closest "not for drinking"
  natures are the storm, fish-farm and harbour basins and mine and gravel-pit lakes: the maintainers' choice. TOPAGE
  2019 and 2022 are tagged `fr-lo`, which a search result calls Licence Ouverte 1.0, and are not proposed.
- **Dams.** The ROE held 125,818 obstacles on 17 November 2026, overseas included (measured on its WFS). Joining two
  CSV exports by row order (an assumption) gives 20,054 dams of some sub-type and 17,375 existing dams (derived); only
  5,456 of those carry a drop height, and 93 are 10 m or more. It maps obstacles to fish and sediment, without storage,
  hazard class or owner, so a French dam popup would show fewer facts than the NID one. No national open list of
  classified dams was found, only regional ones with mixed licences in data.gouv.fr search results (Géorisques not
  checked). BD TOPO has 38,154 linear and 402 surface `Barrage` features, weirs and sluices included, and OSM 5,618
  `waterway=dam` in metropolitan France (both measured).
- **Crops.** RPG covers only parcels declared for farm aid, as polygons, so `tools/build_crops.py` would need a
  rasterising step and Lambert-93 instead of its Albers maths. Its 2025 code list (opened) fits today's kinds: orchards
  (group 20, with citrus and small berries), vines (21) and nuts (22); apples and almonds are only sub-codes of "other
  orchard". New kinds to decide: olives, chestnuts, walnuts, truffle oaks, lavender, and overseas bananas, pineapple,
  sugar cane, coffee and cocoa. OSO is a 10 m raster, the shape `build_crops.py` reads, with orchards and vineyards but
  no berries, olives or nuts, latest year 2024. Its download answered HTTP 500 with a quota message (an account is
  likely, not confirmed). GEODES and Theia give Etalab 2.0, its STAC record Apache 2.0, and the pages 23 or 24 classes.
  CORINE's licence and classes on IGN were not checked.
- **Buildings.** IGN's WFS held 51,484,368 buildings on 17 November 2026, 96.7 % with a height (measured), perhaps a few
  weeks ahead of the quarterly file. The whole-France GeoParquet of 15 September 2026 has a 7.39 GB `batiment` file
  whose longitudes run from -63.15 to 55.83, so it holds the overseas regions; GPKG files per region also exist.
  `hauteur` runs from the lowest ground point to the top of the eaves (the roof edge, or the top of the wall under a
  flat roof), not to the ridge (BD TOPO 3.5 content description, July 2026, opened). Cadastre buildings have no height
  but are light (71.5 MB for
  Bouches-du-Rhône). Microsoft's footprints are not needed (CDLA Permissive 2.0 per its README, ODbL per Overture).
- **Places.** INSEE's commune file, the stand-in for US counties, has no coordinates and must be joined to ADMIN EXPRESS
  or BD TOPO points. La Poste's postcode base has 39,192 rows for 6,328 postcodes (measured): a point per commune and
  postcode pair, not a centroid per postcode, so the build needs a rule. La Poste says postcode outlines are not open
  data, so nothing matches the ZCTAs. Department keys `2A` and `2B` must stay text.

## Help points

OSM is the base source, as in the US. Counts from taginfo for Geofabrik's metropolitan France extract, data until
16 November 2026 21:22 UTC, all object types (opened):

| Tag | Count | Notes |
|---|---|---|
| `amenity=pharmacy` | 19,141 | |
| `amenity=fire_station` | 6,124 | mostly drawn as buildings |
| `amenity=police` | 5,979 | |
| `amenity=hospital` | 2,494 | mostly areas |
| `amenity=drinking_water` | 26,740 | |
| `man_made=water_well` | 23,311 | |
| `emergency=water_tank` | 11,396 | firefighting water, not drinking water |
| `emergency=drinking_water` | 0 | the German emergency-well tag is not used in France |
| `emergency=defibrillator` | 28,328 | |
| `emergency=fire_hydrant` | 246,264 | |
| `amenity=shelter` | 47,862 | every kind of shelter, not only emergency ones |

Each overseas region has its own extract and taginfo (data until 16 November 2026, opened); the counts are in the
JSON. Their shelter counts are high (60 to 506); whether these are bus or cyclone shelters was not checked.

French kinds worth a decision:

- **Defibrillators.** A law of 28 June 2018 obliges operators to declare them in a national base. **Géo'DAE**
  (Atlasanté, Licence Ouverte 2.0) is one CSV of 80.7 MB, updated several times a day, with 192,233 records, all with
  coordinates, overseas included (measured): far more than OSM's 28,328 in metropolitan France, though Guadeloupe has
  60 rows against 206 OSM objects. Its status flags (190,999 "in service", 14,341 "awaiting validation", 5,267
  duplicates) overlap and do not add up, so a build must filter on them. `web/map.js` has no such layer today, and it
  fits Lastbook's purpose: the first minutes of a cardiac arrest.
- **Mountain refuges and shelters.** No national open list from the mountain clubs or a ministry was found. BD TOPO
  counts 718 `Refuge` and 1,854 `Abri de montagne` (measured); OSM has 693 alpine and 1,152 wilderness huts.
- **What BD TOPO already holds.** Its `zone_d_activite_ou_d_interet` layer is one official source, with geometry and the
  overseas regions, for 6,710 fire and rescue centres, 3,775 gendarmerie posts, 960 police entries, 2,491 `Hôpital` and
  2,412 `Etablissement hospitalier` (overlap not checked) and 38,574 town halls (WFS counts, measured; the hospital
  sub-totals partly sampled). It could cross-check or replace OSM for the help group. FINESS, the health facilities
  file, has coordinates for 75 % of its active establishments (measured). The Service-Public.gouv.fr directory lists
  3,067 gendarmerie brigades, but its 366 MB archive was not downloaded, so its coordinates were not checked.
- **What has no open national list.** Alert sirens, drinking fountains, gathering points, fire hydrants and overseas
  cyclone shelters exist only in a few local lists or in OSM, and France has no emergency-well scheme like Germany's.
  Whether hydrants (246,264 in OSM, meant for firefighters) justify a layer as water in a long outage is a decision.

## Licence notes and attribution

All proposed licences allow redistribution in a free offline library, including commercial reuse. Only OSM and
Overture's buildings bring share-alike. What each asks:

- **Licence Ouverte 2.0 (Etalab)** (BD ALTI, RGE ALTI, BD TOPO, BD TOPAGE, RPG, ADMIN EXPRESS, cadastre, BAN, Géo'DAE,
  FINESS, La Poste's postcode base). The text (opened) sets one condition: mention the source, at least the licensor's
  name, and the date of the last update of the data reused; a link to the data may do. The credit must not suggest
  endorsement. It is compatible with CC BY, OGL and ODC-BY. **IGN and Sandre fix no sentence** in any record opened:
  IGN's ADMIN EXPRESS page on cartes.gouv.fr names `etalab-2.0` and links the licence text, and the site's terms of use
  give no credit line (both opened in a browser). So any wording is our suggestion, for example "Source : IGN, BD
  TOPO, édition du 15 septembre 2026, Licence Ouverte 2.0". The dates of last update are in the download feeds.
  **INSEE** does fix one: its legal notice (opened in a browser) puts the site's data and files under Licence Ouverte
  2.0 unless stated otherwise, and asks for "Source : Insee" with the date of last update when known.
- **Service-Public.gouv.fr directory.** Licence Ouverte 2.0 plus extra rules: name "Service-Public.gouv.fr / DILA",
  the download URL, the file name and its date (dataset description, opened).
- **Copernicus WorldDEM-30** (GLO-30). The licence PDF was opened this time; its notices are those REGIONS.md quotes,
  and they pass on to everyone who redistributes.
- **ODbL** (OSM, Overture buildings). As for the US map.
- **Overture addresses.** The attribution page credits the national address site, under Licence Ouverte 2.0,
  distributed by OpenAddresses, accessed 15 October 2026, and asks for "Overture Maps Foundation, overturemaps.org".
- **CC BY 4.0** (GeoNames postcodes). Credit GeoNames, with a link to www.geonames.org.

To look at before anything is built: **OSO** is Etalab 2.0 on the GEODES and Theia pages but Apache 2.0 in its STAC
record, to be asked of Theia. **INSEE's commune file** is tagged `fr-lo` on data.gouv.fr, which a search result reads
as Licence Ouverte 1.0; the copy used here came from insee.fr, under the legal notice above. The **ROE** says "Licence
Ouverte Etalab" without a version. **The BAN's open licence date**, 1 January 2020, comes from a news article (Acteurs
publics, opened), a secondary source; IGN's press release could not be read. **Not checked:** Géo'DAE's own wording,
CORINE Land Cover's licence.

These notices would belong wherever the map already credits its sources, and in `THIRD_PARTY_NOTICES.md` if that is
where the maintainers keep data licences.

## How addresses are written

- **Order.** Number, street type and name, then postcode and town: "10 rue de Rivoli, 75001 Paris". The number comes
  first, as in the US; the postcode before the town, as in Germany. La Poste's guide (SP8855 volume 2, opened) puts
  number and street on line 4 and postcode and town on line 6 of at most six, in capitals on the last line. It cites the
  AFNOR standard Z10-011, which is paid and was not read.
- **Postcode.** Five digits, with leading zeros (`01000` Bourg-en-Bresse), so it must stay text. The first two digits
  are usually the department, but Corsica keeps `20` for both departments, the overseas regions use `971` to `976`,
  some communes use a neighbouring department's code, and CEDEX codes serve organisations.
- **Street words.** Rue (12,997,645 Overture rows), route, chemin, avenue, impasse, allée, place and boulevard lead;
  regional words such as *strada* (Corsica), *hent* (Breton) and *carrer* (Catalan) occur (measured). La Poste
  abbreviates AV, BD, PL, IMP, ALL, RTE, SQ, ST and STE; its web page and SP8855 disagree on CHEM (chemin) and COUR
  (cours), which only the web page lists.
- **Suffixes, accents, apostrophes.** 7.8 % of numbers carry *bis*, *ter*, *quater* or a letter, fused in Overture
  ("12bis") and in a separate column `rep` in the BAN. 21 % of street names have a non-ASCII letter, and the same word
  comes with and without it: "Allée" in 752,060 rows, "Allee" in 146,333. Straight and curly apostrophes both occur.
- **What the current code does with that** (read in this repository and tried on 17 November 2026, on the functions
  unchanged and on a small index built with `tools/build_addresses.py`'s own query and row transform from Overture rows
  around five towns):
  - `normalize()` and `norm()` keep only `a-z` and `0-9`, so "Église" becomes `glise` and "Opéra" `op ra`. An accented
    query matches accented data, never the unaccented copy of the same word. Accents need folding on both sides.
  - `WORDS` is English; some entries fit (avenue, place, boulevard, saint), but `bd`, `sainte` and `ste` are missing:
    "1 boulevard Saint-Germain" found one address, "1 bd Saint-Germain" none.
  - `is_address_query()` needs a number first, which fits, but it takes "75001 Paris" and "20000 Ajaccio" as addresses
    (house number 20000, street "ajaccio"), and not "Place de l'Hôtel de Ville, 75004 Paris".
  - `_parts()` takes a postcode only as the last word, but in French the town follows it: "10 rue de Rivoli, 75001
    Paris" found nothing, "10 rue de Rivoli" one address. A last word that is a US code becomes a state: "5 rue Victor
    Hugo la" is read as Louisiana.
  - `tools/build_addresses.py` keeps only `country = 'US'`. In Overture release 2026-10-21.0, `postal_city` is empty in
    all 26,052,116 French rows and `address_levels` holds one entry, the commune (measured). So the tool would store an
    empty city and, as the "state", the commune's first two letters: `PA` for Paris, `LY` for Lyon, 351 values, with
    6,894,553 rows (26 %) equal to a real US code. A result would read "PA, 75004", and a town typed in a query would
    filter everything out. The town should come from `address_levels[1]`. The overseas regions are under
    `country = 'FR'`; New Caledonia and French Polynesia have their own codes and no postcodes (measured).
  - A regional split by postcode prefix is close but not exact: 5,170 rows (0.02 %) use a neighbouring department's
    postcode, and `20` and `97` need three digits. Each row's source dataset is named by department (`fr/59`, `fr/2A`,
    `fr/971/statewide`), which gives an exact cut (measured).
  - A fused suffix matches only when typed fused: "9bis Rue Anna Marly" found the address, "9 bis Rue Anna Marly" not.
  - The five-digit rule, `left(postcode, 5)`, fits unchanged: every French row has exactly five digits. The rows
    examined carry an update time of 14 October 2026, about a month behind the BAN, which republishes daily.

## Still undecided

Each of these needs the maintainers' decision before any code changes. The first two are shared with REGIONS.md and
REGIONS-DE.md.

1. **Codes in setup.** Whether `FR-IDF`, `FR-20R` and `FR-971` are acceptable as a manifest `id`, in `map-set.json`
   and in `Lastbook-Map-<id>.zip` (the manifest's own rule lets them through); the two-letter rule for address index
   ids, which no hyphenated code can meet; how setup groups 18 regions, five of them far away; and the current ISO
   forms against the older `FR-COR` and `FR-GP`.
2. **The box rule**, as in REGIONS.md, here from ADMIN EXPRESS land polygons, with the overlaps and Guyane's box.
3. **Region or department.** Eighteen regions, or the 101 departments as a finer unit.
4. **Terrain.** IGN's bare-ground BD ALTI with reprojection, or one surface model (GLO-30) for all.
5. **Crops.** RPG parcels (rasterised, overseas included) or OSO (metropolitan only), and which French crops are kinds.
6. **Dams.** Whether the ROE belongs in a dam layer, and with which filter (existing dams, a minimum height).
7. **Address indexes.** Cut by source dataset or postcode prefix; town from `address_levels[1]`; accent folding and
   French street words on both sides.
8. **New help-point kinds**: defibrillators from Géo'DAE, mountain refuges, and BD TOPO as an official help source.
9. **Territories outside the 18.** Saint-Martin, Saint-Barthélemy and Saint-Pierre-et-Miquelon are in several datasets
   but have no region of their own.
10. **Boundaries in dispute.** Guyane and Suriname, Mont Blanc and Mayotte belong with the question in REGIONS.md.

## What was checked, and what was not

- Opened on 17 November 2026: INSEE's COG 2026 files and Île-de-France pages; IGN's WFS capabilities, download feeds,
  metadata records, BD TOPO and RPG content PDFs and crop code lists, and LiDAR HD records; Sandre's BD TOPAGE and ROE
  records, downloads and nomenclature; the OSO pages on GEODES, STAC and Theia; Copernicus's AWS, ESA and licence pages;
  the Licence Ouverte 2.0 text; in a browser, ISO's Online Browsing Platform entry for France, IGN's ADMIN EXPRESS
  page and the terms of use of cartes.gouv.fr, and INSEE's legal notice; IGN's ADMIN EXPRESS content description;
  `iso-codes` and the
  English Wikipedia pages on ISO 3166-2:FR and extreme points; the
  Senate report on Guyane; legal commentaries on the 2016 and 2018 reforms; La Poste's SP8855 documents, abbreviation
  page and postcode base; the BAN's pages, file listing and two department files; Overture's attribution page and
  address guide; Geofabrik and taginfo; OSM's copyright page; the cadastre, BDNB, Microsoft and GeoNames pages; the
  Géo'DAE, FINESS and Service-Public records; `engine/address_search.py`, `tools/build_addresses.py`,
  `engine/setup/manifest.py` and `engine/setup/install.py`.
- Measured on 17 November 2026: the 18 boxes, island effects and areas; the boxes of Saint-Martin and
  Saint-Barthélemy; the BD TOPO and ROE counts on their WFS; file
  sizes from feeds and download headers; the taginfo counts; the La Poste, INSEE, Géo'DAE and FINESS files; Overture
  release 2026-10-21.0 for France. Tried: the address functions and a small test index, as above.
- Seen only in search results: IGN's 2021 opening; the Île-de-France area of 12,012 km²; the Mont Blanc and Mayotte
  disputes; the 2015 law's text; TOPAGE 2019 and 2022 under Licence Ouverte 1.0; the ROE's weekly update; the LiDAR HD
  portal; FINESS category 620 as pharmacies; regional dam lists and local help-point lists (titles in data.gouv.fr
  search listings).
- Not checked: where ADMIN EXPRESS boundaries run at the coast (not in its content description); LiDAR HD progress;
  GLO-30 completeness; 21 BD ALTI file sizes (rate limit); TOPAGE in Guyane (only "not found"); the OSO download
  (quota); CORINE's licence and classes; Géorisques and any ministry list of classified dams; the Service-Public
  archive; Guyane's extreme points and its border with Brazil; an install with a hyphenated map `id` (the rules were
  read, not run).
